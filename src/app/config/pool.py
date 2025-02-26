from pathlib import Path

import pandas as pd


class Pool:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.df: pd.DataFrame