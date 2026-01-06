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
        _type: str,  # "dataset" or "diffpipe"
        name: str,
        url_templates: str | Path = Path(URL_TEMPLATES),
        variant: str | None = None,
        vars_dict: dict | None = None,
        vars_list: list[TemplaterVariable] | None = None,
        suffix: str = SUFFIX_CONFIG_FILES,
        todir: str | Path = URL_TODIR,
        verbose: bool = False,
    ) -> None:
        self._type = _type
        self.name = name
        self.variant = variant
        self.path_templates = Path(url_templates)
        self.suffix = suffix
        self._todir = todir
        self.file_saved: Path | None = None
        self.verbose = verbose

        # select template
        str_template: str = ''
        file_template = self.filepath_template
        if file_template is None:
            raise FileNotFoundError('no template found!')
        with file_template.open('rt') as f:
            str_template = f.read()
            # print(str_template)
        self._template = Template(str_template)
        print(f'using template: {file_template}')

        defaults = self._make_cascading_defaults()

        self._substitutes = self._make_substitutes_from_dict(defaults)

        if vars_dict:
            self._substitutes |= self._make_substitutes_from_dict(vars_dict)
        if vars_list:
            self._substitutes |= self._make_substitutes_from_list(vars_list)

        if self.verbose:
            print('using substitutes:')
            pprint(self._substitutes)

    def _load_json(self, filepath: Path) -> dict:
        if not filepath.exists():
            return {}
        if not filepath.is_file():
            return {}
        with filepath.open('rt') as f:
            return json.load(f)

    def _make_cascading_defaults(self) -> dict:
        defaults = {}

        files = [
            self.path_templates / f'{self._type}_{self.POSTFIX_DEFAULT_FILES}',
            self.path_templates / f'{self._type}_{self.name}_{self.POSTFIX_DEFAULT_FILES}',
            self.path_templates
            / f'{self._type}_{self.name}_{self.variant}_{self.POSTFIX_DEFAULT_FILES}',
        ]
        for file in files:
            data = self._load_json(file)
            if data:
                defaults |= data
                print(f'using defaults: {file}')

        return defaults

    @property
    def filepath_template(self) -> Path | None:
        files = [
            (self.path_templates / f'{self._type}_{self.name}_{self.variant}').with_suffix(
                self.suffix
            ),
            (self.path_templates / f'{self._type}_{self.name}').with_suffix(self.suffix),
            (self.path_templates / f'{self._type}').with_suffix(self.suffix),
        ]
        for file in files:
            print(f'looking for: {file}')
            if file.exists():
                return file
        return None

    @property
    def filename(self) -> str:
        file = self.filepath_template
        if file is not None:
            return file.name
        else:
            return ''

    @property
    def todir(self) -> Path:
        return Path(self._todir)

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
