from __future__ import annotations

import random
from typing import Tuple


class Colour:
    __slots__ = ("value",)

    def __init__(self, value: int = 0) -> None:
        self.value = int(value) & 0xFFFFFF

    def __repr__(self) -> str:
        return f"<Colour value={self.value:#06x}>"

    def __int__(self) -> int:
        return int(self.value)

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> "Colour":
        return cls((r << 16) | (g << 8) | b)

    def to_rgb(self) -> Tuple[int, int, int]:
        return (self.value >> 16 & 0xFF, self.value >> 8 & 0xFF, self.value & 0xFF)

    @classmethod
    def random(cls) -> "Colour":
        return cls(random.randint(0, 0xFFFFFF))


Color = Colour

