import json
from string import Template
from pathlib import Path
from typing import Any, Final


class TemplaterVariable:
    def __init__(
        self, name: str, value: str | int | list[int] | list[str], disable: bool = False
    ) -> None:
        self._typelist = [int, str]
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

    @property
    def enable(self):
        self._disable = False

    @property
    def disable(self):
        self._disable = True

    @property
    def value_string(self) -> str:
        vstr = ''
        if self._disable:
            vstr = '#'
        vstr += f'{self.name} = '
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

    def __init__(
        self,
        name: str,
        url_templates: str | Path,
        vars_dict: dict | None = None,
        vars_list: list[TemplaterVariable] | None = None,
    ) -> None:
        self.name = name

        url_templates = Path(url_templates)
        file_template = (url_templates / f'{self.name}_template').with_suffix(
            self.SUFFIX_CONFIG_FILES
        )

        str_template: str = ''
        with file_template.open('rt') as f:
            str_template = f.read()
            # print(str_template)
        self._template = Template(str_template)

        defaults = {}
        file_defaults = url_templates / f'{self.name}_defaults.json'
        if file_defaults.exists():
            with file_defaults.open('rt') as f:
                defaults = json.load(f)
        self._substitutes = self._make_substitutes_from_dict(defaults)

        if vars_dict:
            self._substitutes |= self._make_substitutes_from_dict(vars_dict)
        if vars_list:
            self._substitutes |= self._make_substitutes_from_list(vars_list)

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

    def save(self, todir: str | Path) -> None:
        todir = Path(todir)
        todir.mkdir(parents=True, exist_ok=True)
        tofile = (todir / self.name).with_suffix(self.SUFFIX_CONFIG_FILES)
        with tofile.open('wt') as f:
            f.write(self.get_string)
