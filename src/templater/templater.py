import os
import json
from pprint import pprint
from string import Template
from pathlib import Path
from typing import Any, Final


class TemplaterVariable:
    PARAMETER_SPITTER: Final = '___'

    def __init__(
        self,
        name: str,
        value: str | int | float | list[str] | list[int] | list[float],
        disable: bool = False,
    ) -> None:
        self._typelist = [str, int, float]
        self.name = name
        if isinstance(value, list):
            if not value:
                raise ValueError('Empty lists not allowed!')
            vcheck = value[0]
        else:
            vcheck = value
        if type(vcheck) not in self._typelist:
            raise ValueError(f'type is not in {self._typelist}!')
        self.value = value
        self._disable = disable
        # empty str also disables
        if isinstance(self.value, str):
            if not self.value:
                self._disable = True

    @property
    def enable(self):
        self._disable = False

    @property
    def disable(self):
        self._disable = True

    @property
    def value_string(self) -> str:
        # setup parameter, always use last split
        parameter = self.name.split(self.PARAMETER_SPITTER)[-1]

        vstr = ''
        if self._disable:
            vstr = '#'
        vstr += f'{parameter} = '
        if isinstance(self.value, str):
            vstr += f"'{self.value}'"
        else:
            vstr += str(self.value)

        return vstr

    @property
    def substitute(self) -> dict[str, Any]:
        return {self.name: self.value_string}


class Templater:
    SUFFIX_CONFIG_FILES: Final = '.toml'
    POSTFIX_DEFAULT_FILES: Final = 'defaults.json'
    URL_TEMPLATES: Final = f'{os.environ["HOME_AIT"]}/conf/diffpipe/templates'
    URL_TODIR: Final = f'{os.environ["WORKSPACE"]}/train'

    def __init__(
        self,
        name: str,
        _type: str,  # "dataset" or "diffpipe"
        url_templates: str | Path = Path(URL_TEMPLATES),
        variant: str | None = None,
        variants: list[str]
        | None = None,  # if no template is found, maybe a variant exists. first match!
        vars_dict: dict | None = None,
        vars_list: list[TemplaterVariable] | None = None,
        suffix: str = SUFFIX_CONFIG_FILES,
        todir: str | Path = URL_TODIR,
        use_generics: bool = False,
    ) -> None:
        self.suffix = suffix
        self._todir = todir
        self.file_saved: Path | None = None

        # select template
        self.path_templates = Path(url_templates)
        self.name = name
        self.variant = ''
        self._type = _type
        self._use_generics = False
        if variants is None:
            variants = []
        if variant is None:
            variant = ''
        if variant:
            variants.append(variant)
        if not self.filepath_template.exists():
            for variant in variants:
                self.variant = variant
                if self.filepath_template.exists():
                    break
        # use use_generics
        if not self.filepath_template.exists():
            self._use_generics = use_generics
        # template selection not successful
        if not self.filepath_template.exists():
            raise FileNotFoundError(f'No template found: {str(self.filepath_template)}')

        # template selection successful
        print(f'success: using template {self.filepath_template}')
        str_template: str = ''
        with self.filepath_template.open('rt') as f:
            str_template = f.read()
            # print(str_template)
        self._template = Template(str_template)

        defaults = {}
        if self.filepath_defaults.exists():
            print(f'info: using defaults {self.filepath_defaults}')
            with self.filepath_defaults.open('rt') as f:
                defaults = json.load(f)
        else:
            print(f'info: no defaults found for: {self.filepath_defaults}')

        self._substitutes = self._make_substitutes_from_dict(defaults)

        if vars_dict:
            self._substitutes |= self._make_substitutes_from_dict(vars_dict)
        if vars_list:
            self._substitutes |= self._make_substitutes_from_list(vars_list)

        print('using substitutes:')
        pprint(self._substitutes)

    @property
    def filepath_template(self) -> Path:
        if self._use_generics:
            return (self.path_templates / f'{self._type}').with_suffix(self.suffix)
        if self.variant:
            return (self.path_templates / f'{self.name}_{self.variant}_{self._type}').with_suffix(
                self.suffix
            )
        return (self.path_templates / f'{self.name}_{self._type}').with_suffix(self.suffix)

    @property
    def filename(self) -> str:
        return self.filepath_template.name

    @property
    def filepath_defaults(self) -> Path:
        if self._use_generics:
            return self.path_templates / f'{self._type}_{self.POSTFIX_DEFAULT_FILES}'
        if self.variant:
            return (
                self.path_templates
                / f'{self.name}_{self.variant}_{self._type}_{self.POSTFIX_DEFAULT_FILES}'
            )
        return self.path_templates / f'{self.name}_{self._type}_{self.POSTFIX_DEFAULT_FILES}'

    @property
    def todir(self) -> Path:
        return self._todir

    def _make_substitutes_from_dict(self, vars: dict) -> dict[str, Any]:
        ret = {}
        for key, val in vars.items():
            v = TemplaterVariable(key, val)
            ret |= v.substitute
        return ret

    def _make_substitutes_from_list(self, vars: list[TemplaterVariable]) -> dict[str, Any]:
        ret = {}
        for v in vars:
            ret |= v.substitute
        return ret

    @property
    def get_string(self) -> str:
        content = ''
        try:
            content = self._template.safe_substitute(self._substitutes)
        except KeyError:
            pass
        return content

    def save(self, todir: str | Path | None = None, filename: str | None = None) -> Path:
        if filename is None:
            filename = self.filename
        if todir is None:
            todir = self.todir

        todir = Path(todir)
        todir.mkdir(parents=True, exist_ok=True)
        tofile = todir / self.filename
        with tofile.open('wt') as f:
            f.write(self.get_string)

        self.file_saved = tofile
        print(f'saved to {str(self.file_saved)}')

        return self.file_saved
