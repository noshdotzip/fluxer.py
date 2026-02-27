from __future__ import annotations

from typing import Dict


INTENT_BITS: Dict[str, int] = {
    "guilds": 1 << 0,
    "members": 1 << 1,
    "bans": 1 << 2,
    "emojis_and_stickers": 1 << 3,
    "integrations": 1 << 4,
    "webhooks": 1 << 5,
    "invites": 1 << 6,
    "voice_states": 1 << 7,
    "presences": 1 << 8,
    "guild_messages": 1 << 9,
    "guild_reactions": 1 << 10,
    "guild_typing": 1 << 11,
    "direct_messages": 1 << 12,
    "direct_reactions": 1 << 13,
    "direct_typing": 1 << 14,
    "message_content": 1 << 15,
    "guild_scheduled_events": 1 << 16,
    "auto_moderation_configuration": 1 << 20,
    "auto_moderation_execution": 1 << 21,
}


def _all_intents_value() -> int:
    value = 0
    for bit in INTENT_BITS.values():
        value |= bit
    return value


_ALL_INTENTS = _all_intents_value()


class Intents:
    __slots__ = ("value",)

    def __init__(self, value: int = 0, **kwargs: bool) -> None:
        object.__setattr__(self, "value", int(value))
        if kwargs:
            self.update(**kwargs)

    def __repr__(self) -> str:
        return f"<Intents value={self.value}>"

    def __int__(self) -> int:
        return int(self.value)

    def __getattr__(self, name: str) -> bool:
        if name in INTENT_BITS:
            return bool(self.value & INTENT_BITS[name])
        raise AttributeError(name)

    def __setattr__(self, name: str, value: bool) -> None:
        if name in INTENT_BITS:
            self._set(name, value)
            return
        object.__setattr__(self, name, value)

    def _set(self, name: str, enabled: bool) -> None:
        bit = INTENT_BITS.get(name)
        if bit is None:
            raise AttributeError(name)
        if enabled:
            object.__setattr__(self, "value", int(self.value) | bit)
        else:
            object.__setattr__(self, "value", int(self.value) & ~bit)

    def update(self, **kwargs: bool) -> None:
        for name, enabled in kwargs.items():
            if name not in INTENT_BITS:
                raise AttributeError(name)
            self._set(name, bool(enabled))

    @classmethod
    def none(cls) -> "Intents":
        return cls(0)

    @classmethod
    def from_value(cls, value: int) -> "Intents":
        return cls(value)

    @classmethod
    def all(cls) -> "Intents":
        return cls(_ALL_INTENTS)

    @classmethod
    def default(cls) -> "Intents":
        intents = cls.all()
        intents.members = False
        intents.presences = False
        intents.message_content = False
        return intents

    @property
    def messages(self) -> bool:
        return self.guild_messages and self.direct_messages

    @messages.setter
    def messages(self, value: bool) -> None:
        self.guild_messages = value
        self.direct_messages = value

    @property
    def reactions(self) -> bool:
        return self.guild_reactions and self.direct_reactions

    @reactions.setter
    def reactions(self, value: bool) -> None:
        self.guild_reactions = value
        self.direct_reactions = value

    @property
    def typing(self) -> bool:
        return self.guild_typing and self.direct_typing

    @typing.setter
    def typing(self, value: bool) -> None:
        self.guild_typing = value
        self.direct_typing = value
