from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, Tuple


PERMISSIONS: Dict[str, int] = {
    "create_instant_invite": 1 << 0,
    "kick_members": 1 << 1,
    "ban_members": 1 << 2,
    "administrator": 1 << 3,
    "manage_channels": 1 << 4,
    "manage_guild": 1 << 5,
    "add_reactions": 1 << 6,
    "view_audit_log": 1 << 7,
    "priority_speaker": 1 << 8,
    "stream": 1 << 9,
    "view_channel": 1 << 10,
    "send_messages": 1 << 11,
    "send_tts_messages": 1 << 12,
    "manage_messages": 1 << 13,
    "embed_links": 1 << 14,
    "attach_files": 1 << 15,
    "read_message_history": 1 << 16,
    "mention_everyone": 1 << 17,
    "use_external_emojis": 1 << 18,
    "view_guild_insights": 1 << 19,
    "connect": 1 << 20,
    "speak": 1 << 21,
    "mute_members": 1 << 22,
    "deafen_members": 1 << 23,
    "move_members": 1 << 24,
    "use_vad": 1 << 25,
    "change_nickname": 1 << 26,
    "manage_nicknames": 1 << 27,
    "manage_roles": 1 << 28,
    "manage_webhooks": 1 << 29,
    "manage_guild_expressions": 1 << 30,
    "use_application_commands": 1 << 31,
    "request_to_speak": 1 << 32,
    "manage_events": 1 << 33,
    "manage_threads": 1 << 34,
    "create_public_threads": 1 << 35,
    "create_private_threads": 1 << 36,
    "use_external_stickers": 1 << 37,
    "send_messages_in_threads": 1 << 38,
    "use_embedded_activities": 1 << 39,
    "moderate_members": 1 << 40,
    "view_creator_monetization_analytics": 1 << 41,
    "use_soundboard": 1 << 42,
    "use_external_sounds": 1 << 45,
    "send_voice_messages": 1 << 46,
}


def _all_permissions_value() -> int:
    value = 0
    for bit in PERMISSIONS.values():
        value |= bit
    return value


_ALL_PERMISSIONS = _all_permissions_value()


class Permissions:
    __slots__ = ("value",)

    def __init__(self, value: int = 0, **kwargs: bool) -> None:
        object.__setattr__(self, "value", int(value))
        if kwargs:
            self.update(**kwargs)

    def __repr__(self) -> str:
        return f"<Permissions value={self.value}>"

    def __iter__(self) -> Iterator[Tuple[str, bool]]:
        for name in PERMISSIONS:
            yield name, getattr(self, name)

    def __int__(self) -> int:
        return int(self.value)

    def __getattr__(self, name: str) -> bool:
        if name in PERMISSIONS:
            return bool(self.value & PERMISSIONS[name])
        raise AttributeError(name)

    def __setattr__(self, name: str, value: bool) -> None:
        if name in PERMISSIONS:
            self._set(name, value)
            return
        object.__setattr__(self, name, value)

    def _set(self, name: str, enabled: bool) -> None:
        bit = PERMISSIONS.get(name)
        if bit is None:
            raise AttributeError(name)
        if enabled:
            object.__setattr__(self, "value", int(self.value) | bit)
        else:
            object.__setattr__(self, "value", int(self.value) & ~bit)

    def update(self, **kwargs: bool) -> None:
        for name, enabled in kwargs.items():
            if name not in PERMISSIONS:
                raise AttributeError(name)
            self._set(name, bool(enabled))

    def is_subset(self, other: "Permissions") -> bool:
        return int(self.value) & int(other.value) == int(self.value)

    def is_superset(self, other: "Permissions") -> bool:
        return int(other.value) & int(self.value) == int(other.value)

    @classmethod
    def none(cls) -> "Permissions":
        return cls(0)

    @classmethod
    def from_value(cls, value: int) -> "Permissions":
        return cls(value)

    @classmethod
    def all(cls) -> "Permissions":
        return cls(_ALL_PERMISSIONS)


@dataclass
class PermissionOverwrite:
    allow: Permissions
    deny: Permissions

    def __init__(self, **kwargs: bool | None) -> None:
        object.__setattr__(self, "allow", Permissions.none())
        object.__setattr__(self, "deny", Permissions.none())
        for name, value in kwargs.items():
            self._set(name, value)

    def _set(self, name: str, value: bool | None) -> None:
        if name not in PERMISSIONS:
            raise AttributeError(name)
        if value is None:
            self.allow._set(name, False)
            self.deny._set(name, False)
        elif value:
            self.allow._set(name, True)
            self.deny._set(name, False)
        else:
            self.allow._set(name, False)
            self.deny._set(name, True)

    def pair(self) -> Tuple[Permissions, Permissions]:
        return self.allow, self.deny

    def is_empty(self) -> bool:
        return int(self.allow.value) == 0 and int(self.deny.value) == 0

    def update(self, **kwargs: bool | None) -> None:
        for name, value in kwargs.items():
            self._set(name, value)

    def to_dict(self) -> Dict[str, int]:
        return {"allow": int(self.allow.value), "deny": int(self.deny.value)}

    @classmethod
    def from_pair(cls, allow: Permissions, deny: Permissions) -> "PermissionOverwrite":
        overwrite = cls()
        object.__setattr__(overwrite, "allow", Permissions(int(allow.value)))
        object.__setattr__(overwrite, "deny", Permissions(int(deny.value)))
        return overwrite
