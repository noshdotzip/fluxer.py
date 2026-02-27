from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from .utils import MISSING


def _normalize_ids(value: Iterable[Any]) -> List[str]:
    ids: List[str] = []
    for item in value:
        if hasattr(item, "id"):
            ids.append(str(getattr(item, "id")))
        else:
            ids.append(str(item))
    return ids


@dataclass
class AllowedMentions:
    everyone: bool | object = MISSING
    users: bool | Iterable[Any] | object = MISSING
    roles: bool | Iterable[Any] | object = MISSING
    replied_user: bool | object = MISSING

    @classmethod
    def none(cls) -> "AllowedMentions":
        return cls(everyone=False, users=False, roles=False, replied_user=False)

    @classmethod
    def all(cls) -> "AllowedMentions":
        return cls(everyone=True, users=True, roles=True, replied_user=True)

    def merge(self, other: Optional["AllowedMentions"]) -> "AllowedMentions":
        if other is None:
            return self
        return AllowedMentions(
            everyone=other.everyone if other.everyone is not MISSING else self.everyone,
            users=other.users if other.users is not MISSING else self.users,
            roles=other.roles if other.roles is not MISSING else self.roles,
            replied_user=other.replied_user
            if other.replied_user is not MISSING
            else self.replied_user,
        )

    def to_dict(self) -> dict:
        payload: dict = {}
        parse: List[str] = []
        explicit_parse = False

        if self.everyone is True:
            parse.append("everyone")
            explicit_parse = True
        elif self.everyone is False:
            explicit_parse = True
        if self.users is True:
            parse.append("users")
            explicit_parse = True
        elif self.users is not MISSING and self.users is not False:
            payload["users"] = _normalize_ids(self.users)
            explicit_parse = True
        elif self.users is False:
            explicit_parse = True
        if self.roles is True:
            parse.append("roles")
            explicit_parse = True
        elif self.roles is not MISSING and self.roles is not False:
            payload["roles"] = _normalize_ids(self.roles)
            explicit_parse = True
        elif self.roles is False:
            explicit_parse = True

        if explicit_parse:
            payload["parse"] = parse

        if self.replied_user is not MISSING:
            payload["replied_user"] = bool(self.replied_user)

        return payload
