import os
import shutil
from pathlib import Path
from typing import Any, Final

SUFFIX_IMG: Final = ['png', 'webp', 'jpg', 'jpeg', 'gif']
SUFFIX_VID: Final = ['mov', 'mp4']


def suffix_img() -> list[str]:
    postfixes = SUFFIX_IMG
    ret = postfixes.copy()
    ret += [pf.capitalize() for pf in postfixes]
    ret += [pf.upper() for pf in postfixes]
    return [f'.{pf}' for pf in ret]


def suffix_vid() -> list[str]:
    postfixes = SUFFIX_VID
    ret = postfixes.copy()
    ret += [pf.capitalize() for pf in postfixes]
    ret += [pf.upper() for pf in postfixes]
    return [f'.{pf}' for pf in ret]


def is_img_or_vid(url: Any) -> bool:
    """True if url:str|Path is an image or video, otherwise False"""
    if not (isinstance(url, str) or isinstance(url, Path)):
        return False
    return is_img(url) or is_vid(url)


def is_img(url: str | Path) -> bool:
    url = Path(url)
    if not url.exists():
        return False
    elif url.is_dir():
        return False
    if url.suffix in suffix_img():
        return True
    return False


def is_vid(url: str | Path) -> bool:
    url = Path(url)
    if not url.exists():
        return False
    elif url.is_dir():
        return False
    elif url.suffix in suffix_vid():
        return True
    return False


def is_dotfile(url: str | Path) -> bool:
    url = Path(url)
    if not url.exists():
        return False
    elif url.is_dir():
        return False
    elif url.stem[0] == '.':
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


def imgs_and_vids_from_url(url: str | Path) -> list[Path]:
    urls = [Path(f.path) for f in os.scandir(url) if is_img_or_vid(f.path)]
    return urls


def imgs_from_url(url: str | Path) -> list[Path]:
    urls = [Path(f.path) for f in os.scandir(url) if is_img(f.path)]
    return urls


def dotfiles_from_url(url: str | Path) -> list[Path]:
    urls = [Path(f.path) for f in os.scandir(url) if is_dotfile(f.path)]
    return urls


def img_latest_from_url(url: str | Path) -> Path | None:
    urls_img = imgs_from_url(url)
    if urls_img:
        return max(urls_img, key=lambda x: x.stat().st_ctime)
    else:
        return None


def url_move_to_new_parent(
    url_src: str | Path,
    to_parent: str | Path,
    new_name: str | None = None,
    delete_src=False,
    exist_ok=False,
) -> None:
    """
    Moves an url to a new parent and optionally renames it.

    The url suffix is preserved.
    The parent must exist.
    """
    url_src = Path(url_src)
    url_parent = Path(to_parent)
    if not url_src.exists():
        return
    if not is_dir(url_parent):
        return

    if new_name is None:
        new_name = url_src.stem

    url_to = (url_parent / new_name).with_suffix(url_src.suffix)

    if not exist_ok and url_to.exists():
        return

    shutil.copy2(str(url_src), str(url_to))

    if not url_to.exists():
        return

    if delete_src:
        os.remove(str(url_src))


def url_clean(url: str | Path) -> None:
    """
    cleans up a dir given by a url by removing its content files (vids,imgs,etc) and all dotfiles
    """
    if not is_dir(url):
        return
    for file in imgs_and_vids_from_url(url):
        file.unlink(missing_ok=True)
    for file in dotfiles_from_url(url):
        file.unlink(missing_ok=True)
    return
