from __future__ import annotations


class Object:
    __slots__ = ("id",)

    def __init__(self, *, id: int | str) -> None:
        self.id = str(id)

    def __int__(self) -> int:
        return int(self.id)

    def __repr__(self) -> str:
        return f"<Object id={self.id}>"

