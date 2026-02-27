from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence, TypeVar
from urllib.parse import urlencode


class _MissingSentinel:
    __slots__ = ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Any = _MissingSentinel()

T = TypeVar("T")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def find(predicate: Callable[[T], bool], iterable: Iterable[T]) -> Optional[T]:
    for element in iterable:
        if predicate(element):
            return element
    return None


def get(iterable: Iterable[T], /, **attrs: Any) -> Optional[T]:
    for element in iterable:
        matched = True
        for attr, value in attrs.items():
            actual = element.get(attr) if isinstance(element, dict) else getattr(element, attr, MISSING)
            if actual is MISSING or actual != value:
                matched = False
                break
        if matched:
            return element
    return None


DISCORD_EPOCH = 1420070400000


def snowflake_time(snowflake: int | str) -> Optional[datetime]:
    try:
        value = int(snowflake)
    except (TypeError, ValueError):
        return None
    timestamp = (value >> 22) + DISCORD_EPOCH
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)


def time_snowflake(dt: datetime, *, high: bool = False) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    timestamp = int(dt.timestamp() * 1000)
    snowflake = (timestamp - DISCORD_EPOCH) << 22
    if high:
        snowflake |= (1 << 22) - 1
    return snowflake


def oauth_url(
    client_id: int | str,
    *,
    permissions: Optional[Any] = None,
    scopes: Optional[Sequence[str]] = None,
    guild: Optional[Any] = None,
    redirect_uri: Optional[str] = None,
    disable_guild_select: bool = False,
    state: Optional[str] = None,
    authorize_url: str = "https://fluxer.app/oauth2/authorize",
) -> str:
    params = {"client_id": str(client_id)}
    if permissions is not None:
        if hasattr(permissions, "value"):
            params["permissions"] = str(int(permissions.value))
        else:
            params["permissions"] = str(int(permissions))
    if scopes:
        params["scope"] = " ".join(scopes)
    if guild is not None:
        params["guild_id"] = str(getattr(guild, "id", guild))
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    if disable_guild_select:
        params["disable_guild_select"] = "true"
    if state:
        params["state"] = state
    return f"{authorize_url}?{urlencode(params)}"


def maybe_coroutine(func: Callable[..., Any], /, *args: Any, **kwargs: Any):
    result = func(*args, **kwargs)
    if hasattr(result, "__await__"):
        return result
    return result


def as_chunks(sequence: Sequence[T], *, size: int) -> Iterator[list[T]]:
    if size <= 0:
        raise ValueError("size must be > 0")
    chunk: list[T] = []
    for item in sequence:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
