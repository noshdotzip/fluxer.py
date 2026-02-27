from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Snowflake(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError


class Messageable(ABC):
    @abstractmethod
    async def send(self, content: str | None = None, **kwargs: Any):
        raise NotImplementedError


class User(Snowflake, ABC):
    @property
    @abstractmethod
    def bot(self) -> bool:
        raise NotImplementedError

