import copy
from collections import UserList
from typing import Generator, Iterable

import pandas as pd


class Selection(UserList):
    def __init__(self, df: pd.DataFrame, iterable: Iterable = []):
        super().__init__(self._is_int(item) for item in iterable)
        self.df = df

    def __copy__(self):
        result = Selection(self.df)
        result.data = self.data
        return result

    def __setitem__(self, index, item):
        self.data[index] = self._is_int(item)

    def __iadd__(self, other):
        if isinstance(other, type(self)):
            self.data += other.data
            self.unique
        else:
            raise TypeError(f"Selection expected, got {type(other).__name__}")
        return self

    def __add__(self, other):
        if isinstance(other, type(self)):
            ret = copy(self)
            ret += other
            return ret
        else:
            raise TypeError(f"Selection expected, got {type(other).__name__}")

    def __isub__(self, other) -> None:
        if isinstance(other, type(self)):
            self.data = list(set(self) - set(other))
        else:
            raise TypeError(f"Selection expected, got {type(other).__name__}")
        return self

    def _is_int(self, value):
        if isinstance(value, int):
            return value
        raise TypeError(f"integer value expected, got {type(value).__name__}")

    @property
    def clone_empty(self):
        return Selection(self.df)

    def set(self, values: Iterable) -> None:
        self.clear()
        self.extend(values)

    @property
    def all(self):
        self.set(self.df.index.to_list())

    @property
    def rows(self) -> Generator[tuple[int, pd.Series], None, None]:
        for idx, row in self.df.loc[self].iterrows():
            yield idx, row

    @property
    def get(self) -> pd.DataFrame:
        return self.df.loc[self]

    def insert(self, index, item):
        self.data.insert(index, self._is_int(item))

    def append(self, item):
        self.data.append(self._is_int(item))

    def extend(self, other):
        if isinstance(other, type(self)):
            self.data.extend(other)
        else:
            self.data.extend(self._is_int(item) for item in other)

    @property
    def unique(self) -> None:
        self.set(list(set(self)))

    @property
    def uniquesort(self) -> None:
        self.unique
        self.sort()
