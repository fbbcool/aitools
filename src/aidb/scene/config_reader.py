import os
from pathlib import Path
from typing import Any, Final, Literal, Optional

import yaml


class ConfigReader:
    SECTION_DB: Final = 'mongodb'
    SECTION_URL: Final = 'url'
    SECTION_SIZE: Final = 'size'
    CONFIG_DEFAULT: Final = 'prod'

    def __init__(
        self,
        config: Literal['test', 'prod', 'default'] = 'default',
        verbose: int = 1,
        make_urls: bool = True,
    ) -> None:
        self.config = config
        if self.config == 'default':
            self.config = self.CONFIG_DEFAULT
        self._url_config = Path(os.environ['CONF_AIT']) / 'aidb' / f'dbc_scenes_{self.config}.yaml'
        self._verbose = verbose

        self._load_config_from_yaml()

        if make_urls:
            self.root.mkdir(parents=True, exist_ok=True)
            self.thumbs_url.mkdir(parents=True, exist_ok=True)
            self.train_url.mkdir(parents=True, exist_ok=True)

    def _load_config_from_yaml(self) -> None:
        """
        Loads configuration settings from a YAML file.
        Updates private members for MongoDB connection and thumbnail settings.
        """
        if not self._url_config.exists():
            raise FileNotFoundError(f"Configuration file '{str(self._url_config)}' not found!")

        with self._url_config.open('r') as f:
            data = yaml.safe_load(f)

        if data and isinstance(data, dict):
            self._data = data
            self._log(f'Successfully loaded config [{self._url_config}].', level='info')
        else:
            raise ValueError('Unable to load yaml!')

    def get_param(self, section: str, param: str) -> Optional[Any]:
        data_section = self._data.get(section, None)
        if data_section is None:
            return None
        value = data_section.get(param, None)
        if value is None:
            return None
        return value

    def get_param_protected(self, section: str, param: str) -> Any:
        val = self.get_param(section, param)
        if val is None:
            raise ValueError(f'{section}:{param} is None!')
        return val

    @property
    def host(self) -> str:
        return self.get_param_protected(self.SECTION_DB, 'host')

    @property
    def port(self) -> int:
        return self.get_param_protected(self.SECTION_DB, 'port')

    @property
    def db_name(self) -> str:
        return self.get_param_protected(self.SECTION_DB, 'name')

    @property
    def root(self) -> Path:
        return Path(self.get_param_protected(self.SECTION_URL, 'root'))

    @property
    def thumbs_size(self) -> int:
        return self.get_param_protected(self.SECTION_SIZE, 'thumbnail')

    @property
    def thumbs_url(self) -> Path:
        return self.root / self.get_param_protected(self.SECTION_URL, 'thumbnail')

    @property
    def train_size(self) -> int:
        return self.get_param_protected(self.SECTION_SIZE, 'train')

    @property
    def train_url(self) -> Path:
        return self.root / f'{self.get_param_protected(self.SECTION_URL, "train")}'

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[config:{level}] {msg}')
