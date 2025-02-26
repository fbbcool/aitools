from typing import TypedDict


class Captions(TypedDict):
    train: list[str]
    trigger: list[str]
    wd14: list[str]
    joy: list[str]
    blip: list[str]

