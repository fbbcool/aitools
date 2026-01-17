import os
import shutil
from pathlib import Path
from typing import Final

POSTFIX_IMG: Final = ['.png', '.PNG']
POSTFIX_VID: Final = ['.mov', '.mp4']


def is_img_or_vid(url: str | Path) -> bool:
    return is_img(url) or is_vid(url)


def is_img(url: str | Path) -> bool:
    url = Path(url)
    if not url.exists():
        return False
    elif url.is_dir():
        return False
    elif url.suffix in POSTFIX_IMG:
        return True
    return False


def is_vid(url: str | Path) -> bool:
    url = Path(url)
    if not url.exists():
        return False
    elif url.is_dir():
        return False
    elif url.suffix in POSTFIX_VID:
        return True
    return False


def is_dir(url: str | Path) -> bool:
    url = Path(url)
    if not url.exists():
        return False
    elif url.is_dir():
        return True
    return False


def subdirs(url: str | Path) -> list[Path]:
    url = str(url)
    fu = [Path(f.path) for f in os.scandir(url) if f.is_dir()]
    return fu


def subdir_max(url: str | Path) -> tuple[int, Path] | None:
    dirs = subdirs(url)
    if not dirs:
        return None

    max = -1
    max_dir = None
    for dir in dirs:
        try:
            val = int(dir.stem)
        except ValueError:
            continue
        if val > max:
            max = val
            max_dir = dir
    if max_dir is None:
        return None
    return max, max_dir


def subdir_inc(url: str | Path) -> Path:
    url = Path(url)
    max = subdir_max(url)
    if max is None:
        new = 0
    else:
        new = max[0] + 1
    return url / f'{new:04d}'


def urls_to_dir(_urls: list[str] | list[Path] | str | Path, to_dir: str | Path) -> None:
    if not isinstance(_urls, list):
        urls = [_urls]
    else:
        urls = _urls
    to_dir = Path(to_dir)
    to_dir.mkdir(parents=True, exist_ok=True)

    for from_url in urls:
        from_url = Path(from_url)
        if not from_url.exists():
            continue
        to_url = to_dir / from_url.name
        shutil.move(str(from_url), str(to_url))


def imgs_from_url(url: str | Path) -> list[Path]:
    img_urls = [Path(f.path) for f in os.scandir(url) if is_img_or_vid(f.path)]
    return img_urls
