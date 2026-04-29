from pathlib import Path
import json

from .files import is_file


def read_json(url: Path) -> dict:
    if not is_file(url):
        raise ValueError(f'{url} is not a file!')
    data = {}
    with url.open('r') as f:
        data = json.load(f)
    return data


def json_write(url: Path, data: dict, force: bool = False) -> None:
    if url.exists() and not force:
        raise ValueError(f'{url} exists and force option is not set!')
    if not url.parent.exists():
        raise ValueError(f'{url.parent} is not a valid directory!')
    with url.open('w') as f:
        json.dump(data, f)
