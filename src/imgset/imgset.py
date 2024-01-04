import os
from pathlib import Path
from typing import Final

class ImgSet:
    TEST_PATH_CRAWL : Final = "test/imgs"
    def __init__(self, dir: str) -> None:
        self.path_crawl = dir

    def _initialze(self):
        paths = []
        dirs = [dir[0] for dir in os.walk(self.path_crawl)]
        for dir in dirs:
            path = Path(dir)
            paths += list(set(path.glob("*.jpg")))
