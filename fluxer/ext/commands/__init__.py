from __future__ import annotations

import asyncio
import importlib
import inspect
import re
import shlex
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ...client import Client
from ...models import Guild, Member, Message, Role, TextChannel, User
from ...permissions import PERMISSIONS


CommandFunc = Callable[..., Awaitable[Any]]
CheckFunc = Callable[["Context"], Awaitable[bool] | bool]


class CommandError(Exception):
    pass


class CommandNotFound(CommandError):
    pass


class CheckFailure(CommandError):
    pass


class NoPrivateMessage(CheckFailure):
    pass


class MissingPermissions(CheckFailure):
    def __init__(self, missing: List[str]) -> None:
        super().__init__(f"Missing permissions: {', '.join(missing)}")
        self.missing_perms = missing


class BotMissingPermissions(CheckFailure):
    def __init__(self, missing: List[str]) -> None:
        super().__init__(f"Bot missing permissions: {', '.join(missing)}")
        self.missing_perms = missing


class NotOwner(CheckFailure):
    pass


class MissingRole(CheckFailure):
    def __init__(self, role: str) -> None:
        super().__init__(f"Missing role: {role}")
        self.missing_role = role


class MissingAnyRole(CheckFailure):
    def __init__(self, roles: List[str]) -> None:
        super().__init__(f"Missing any role: {', '.join(roles)}")
        self.missing_roles = roles


class BotMissingRole(CheckFailure):
    def __init__(self, role: str) -> None:
        super().__init__(f"Bot missing role: {role}")
        self.missing_role = role


class BotMissingAnyRole(CheckFailure):
    def __init__(self, roles: List[str]) -> None:
        super().__init__(f"Bot missing any role: {', '.join(roles)}")
        self.missing_roles = roles


class UserInputError(CommandError):
    pass


class BadArgument(UserInputError):
    pass


class MissingRequiredArgument(UserInputError):
    def __init__(self, param: inspect.Parameter) -> None:
        super().__init__(f"Missing required argument: {param.name}")
        self.param = param


class ConversionError(CommandError):
    def __init__(self, converter: Any, argument: str, original: Exception) -> None:
        super().__init__(str(original))
        self.converter = converter
        self.argument = argument
        self.original = original


class CommandOnCooldown(CommandError):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"Command is on cooldown. Retry after {retry_after:.2f}s")
        self.retry_after = retry_after


class CommandInvokeError(CommandError):
    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


class CommandRegistrationError(CommandError):
    pass


class MaxConcurrencyReached(CommandError):
    pass


class ExtensionError(CommandError):
    pass


class ExtensionAlreadyLoaded(ExtensionError):
    pass


class ExtensionNotFound(ExtensionError):
    pass


class ExtensionFailed(ExtensionError):
    pass


class NoEntryPointError(ExtensionError):
    pass


class BucketType(Enum):
    DEFAULT = "default"
    USER = "user"
    GUILD = "guild"
    CHANNEL = "channel"
    MEMBER = "member"


@dataclass
class Cooldown:
    rate: int
    per: float
    tokens: int = 0
    window: float = 0.0

    def __post_init__(self) -> None:
        self.tokens = self.rate

    def copy(self) -> "Cooldown":
        return Cooldown(rate=self.rate, per=self.per)

    def update_rate_limit(self, current: float) -> Optional[float]:
        if current > self.window + self.per:
            self.tokens = self.rate
            self.window = current

        if self.tokens <= 0:
            return self.window + self.per - current

        self.tokens -= 1
        return None


class CooldownMapping:
    def __init__(self, cooldown: Cooldown, bucket_type: BucketType) -> None:
        self._cooldown = cooldown
        self._bucket_type = bucket_type
        self._cache: Dict[Any, Cooldown] = {}

    def _get_bucket_key(self, message: Message) -> Any:
        if self._bucket_type == BucketType.USER:
            return message.author.id if message.author else "0"
        if self._bucket_type == BucketType.CHANNEL:
            return message.channel_id
        if self._bucket_type == BucketType.GUILD:
            return message.guild_id or "0"
        if self._bucket_type == BucketType.MEMBER:
            return (message.guild_id or "0", message.author.id if message.author else "0")
        return 0

    def get_bucket(self, message: Message) -> Cooldown:
        key = self._get_bucket_key(message)
        bucket = self._cache.get(key)
        if bucket is None:
            bucket = self._cooldown.copy()
            self._cache[key] = bucket
        return bucket

    def update_rate_limit(self, message: Message) -> Optional[float]:
        bucket = self.get_bucket(message)
        return bucket.update_rate_limit(time.monotonic())


class MaxConcurrency:
    def __init__(self, number: int, per: BucketType, *, wait: bool = False) -> None:
        if number <= 0:
            raise ValueError("number must be > 0")
        self.number = number
        self.per = per
        self.wait = wait
        self._semaphores: Dict[Any, asyncio.Semaphore] = {}

    def _get_bucket_key(self, message: Message) -> Any:
        if self.per == BucketType.USER:
            return message.author.id if message.author else "0"
        if self.per == BucketType.CHANNEL:
            return message.channel_id
        if self.per == BucketType.GUILD:
            return message.guild_id or "0"
        if self.per == BucketType.MEMBER:
            return (message.guild_id or "0", message.author.id if message.author else "0")
        return 0

    def _get_semaphore(self, message: Message) -> asyncio.Semaphore:
        key = self._get_bucket_key(message)
        sem = self._semaphores.get(key)
        if sem is None:
            sem = asyncio.Semaphore(self.number)
            self._semaphores[key] = sem
        return sem

    async def acquire(self, message: Message) -> bool:
        sem = self._get_semaphore(message)
        if self.wait:
            await sem.acquire()
            return True
        if sem.locked() and getattr(sem, "_value", 0) <= 0:
            return False
        await sem.acquire()
        return True

    def release(self, message: Message) -> None:
        sem = self._get_semaphore(message)
        sem.release()


def _ensure_checks(container: Any) -> List[CheckFunc]:
    checks = getattr(container, "__commands_checks__", None)
    if checks is None:
        checks = []
        setattr(container, "__commands_checks__", checks)
    return checks


def check(predicate: CheckFunc):
    def decorator(func: Any) -> Any:
        checks = _ensure_checks(func)
        checks.append(predicate)
        return func

    return decorator


def cooldown(rate: int, per: float, type: BucketType = BucketType.DEFAULT):
    def decorator(func: Any) -> Any:
        setattr(func, "__commands_cooldown__", CooldownMapping(Cooldown(rate, per), type))
        return func

    return decorator


def max_concurrency(number: int, *, per: BucketType = BucketType.DEFAULT, wait: bool = False):
    def decorator(func: Any) -> Any:
        setattr(func, "__commands_max_concurrency__", MaxConcurrency(number, per, wait=wait))
        return func

    return decorator


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _bot_user_id(bot: Any) -> Optional[str]:
    user = getattr(bot, "user", None)
    if isinstance(user, dict):
        return str(user.get("id")) if user.get("id") is not None else None
    if user and hasattr(user, "id"):
        return str(getattr(user, "id"))
    return None


def _permission_value(data: Dict[str, Any]) -> Optional[int]:
    for key in ("permissions", "permissions_new", "permissions_value"):
        value = data.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


async def _get_member_permissions(ctx: "Context", *, me: bool) -> Optional[int]:
    if not ctx.guild_id:
        return None

    if me:
        user_id = _bot_user_id(ctx.bot)
        if user_id is None:
            return None
    else:
        user_id = ctx.author.id if ctx.author else None

    if not user_id:
        return None

    member_payload = ctx.message.raw.get("member") if ctx.message else None
    if member_payload:
        perms = _permission_value(member_payload)
        if perms is not None:
            return perms

    try:
        data = await ctx.bot.api.guilds.get_guild_member_by_user_id(
            guild_id=ctx.guild_id,
            user_id=str(user_id),
        )
    except Exception:
        return None

    if isinstance(data, dict):
        return _permission_value(data)

    return None


def _missing_perms(required: Dict[str, bool], current: int) -> List[str]:
    if current & PERMISSIONS.get("administrator", 0):
        return []

    missing = []
    for name, enabled in required.items():
        if not enabled:
            continue
        bit = PERMISSIONS.get(name)
        if bit is None:
            missing.append(name)
        elif not (current & bit):
            missing.append(name)
    return missing


def guild_only():
    async def predicate(ctx: "Context") -> bool:
        if not ctx.guild_id:
            raise NoPrivateMessage()
        return True

    return check(predicate)


def dm_only():
    async def predicate(ctx: "Context") -> bool:
        if ctx.guild_id:
            raise CheckFailure("This command can only be used in DMs")
        return True

    return check(predicate)


def is_owner():
    async def predicate(ctx: "Context") -> bool:
        if await ctx.bot.is_owner(ctx.author):
            return True
        raise NotOwner()

    return check(predicate)


def has_permissions(**perms: bool):
    async def predicate(ctx: "Context") -> bool:
        if not ctx.guild_id:
            raise NoPrivateMessage()
        value = await _get_member_permissions(ctx, me=False)
        if value is None:
            raise MissingPermissions(list(perms.keys()))
        missing = _missing_perms(perms, value)
        if missing:
            raise MissingPermissions(missing)
        return True

    return check(predicate)


def bot_has_permissions(**perms: bool):
    async def predicate(ctx: "Context") -> bool:
        if not ctx.guild_id:
            raise NoPrivateMessage()
        value = await _get_member_permissions(ctx, me=True)
        if value is None:
            raise BotMissingPermissions(list(perms.keys()))
        missing = _missing_perms(perms, value)
        if missing:
            raise BotMissingPermissions(missing)
        return True

    return check(predicate)


def has_guild_permissions(**perms: bool):
    return has_permissions(**perms)


def bot_has_guild_permissions(**perms: bool):
    return bot_has_permissions(**perms)


def is_admin():
    return has_permissions(administrator=True)


def check_any(*checks: CheckFunc):
    async def predicate(ctx: "Context") -> bool:
        errors: List[Exception] = []
        for check in checks:
            try:
                result = await _maybe_await(check(ctx))
            except Exception as exc:
                errors.append(exc)
                continue
            if result:
                return True
        if errors:
            raise CheckFailure(str(errors[0]))
        raise CheckFailure()

    return check(predicate)


async def _get_member_role_ids(ctx: "Context", *, me: bool) -> Optional[List[str]]:
    if not ctx.guild_id:
        return None
    user_id = None
    if me:
        user_id = _bot_user_id(ctx.bot)
    else:
        if ctx.author:
            user_id = ctx.author.id
    if not user_id:
        return None

    member_payload = ctx.message.raw.get("member") if ctx.message else None
    if member_payload and isinstance(member_payload.get("roles"), list):
        return [str(r) for r in member_payload.get("roles")]

    try:
        data = await ctx.bot.api.guilds.get_guild_member_by_user_id(
            guild_id=ctx.guild_id,
            user_id=str(user_id),
        )
    except Exception:
        return None

    roles = None
    if isinstance(data, dict):
        roles = data.get("roles")
    if isinstance(roles, list):
        return [str(r) for r in roles]
    return None


def _extract_role_id(value: Any) -> Optional[str]:
    if isinstance(value, Role):
        return value.id
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        ids = _extract_ids(value)
        if ids:
            return ids[-1]
    return None


async def _resolve_role_ids(ctx: "Context", roles: Sequence[Any]) -> List[str]:
    if not ctx.guild_id:
        return []
    data = await ctx.bot.api.guilds.list_guild_roles(guild_id=ctx.guild_id)
    role_list = [Role.from_dict(item) for item in data]
    resolved: List[str] = []
    for role in roles:
        role_id = _extract_role_id(role)
        if role_id:
            resolved.append(role_id)
            continue
        name = str(role).lower()
        for entry in role_list:
            if entry.name and entry.name.lower() == name:
                resolved.append(entry.id)
                break
    return resolved


def has_role(item: Any):
    async def predicate(ctx: "Context") -> bool:
        if not ctx.guild_id:
            raise NoPrivateMessage()
        member_roles = await _get_member_role_ids(ctx, me=False)
        if not member_roles:
            raise MissingRole(str(item))
        required = await _resolve_role_ids(ctx, [item])
        if not required:
            raise MissingRole(str(item))
        if any(role_id in member_roles for role_id in required):
            return True
        raise MissingRole(str(item))

    return check(predicate)


def has_any_role(*items: Any):
    async def predicate(ctx: "Context") -> bool:
        if not ctx.guild_id:
            raise NoPrivateMessage()
        member_roles = await _get_member_role_ids(ctx, me=False)
        if not member_roles:
            raise MissingAnyRole([str(item) for item in items])
        required = await _resolve_role_ids(ctx, items)
        if not required:
            raise MissingAnyRole([str(item) for item in items])
        if any(role_id in member_roles for role_id in required):
            return True
        raise MissingAnyRole([str(item) for item in items])

    return check(predicate)


def bot_has_role(item: Any):
    async def predicate(ctx: "Context") -> bool:
        if not ctx.guild_id:
            raise NoPrivateMessage()
        member_roles = await _get_member_role_ids(ctx, me=True)
        if not member_roles:
            raise BotMissingRole(str(item))
        required = await _resolve_role_ids(ctx, [item])
        if not required:
            raise BotMissingRole(str(item))
        if any(role_id in member_roles for role_id in required):
            return True
        raise BotMissingRole(str(item))

    return check(predicate)


def bot_has_any_role(*items: Any):
    async def predicate(ctx: "Context") -> bool:
        if not ctx.guild_id:
            raise NoPrivateMessage()
        member_roles = await _get_member_role_ids(ctx, me=True)
        if not member_roles:
            raise BotMissingAnyRole([str(item) for item in items])
        required = await _resolve_role_ids(ctx, items)
        if not required:
            raise BotMissingAnyRole([str(item) for item in items])
        if any(role_id in member_roles for role_id in required):
            return True
        raise BotMissingAnyRole([str(item) for item in items])

    return check(predicate)


def when_mentioned(bot: "Bot", message: Message) -> List[str]:
    bot_id = _bot_user_id(bot)
    if not bot_id:
        return []
    return [f"<@{bot_id}> ", f"<@!{bot_id}> "]


def when_mentioned_or(*prefixes: str):
    async def inner(bot: "Bot", message: Message) -> List[str]:
        base = when_mentioned(bot, message)
        return base + list(prefixes)

    return inner


class Converter:
    async def convert(self, ctx: "Context", argument: str) -> Any:
        raise NotImplementedError


_ID_RE = re.compile(r"(\\d{10,})")


def _extract_ids(argument: str) -> List[str]:
    return _ID_RE.findall(argument)


class UserConverter(Converter):
    async def convert(self, ctx: "Context", argument: str) -> User:
        ids = _extract_ids(argument)
        if not ids:
            raise BadArgument("User ID must be numeric")
        data = await ctx.bot.api.users.get_user_by_id(user_id=ids[-1])
        return User.from_dict(data, client=ctx.bot)


class MemberConverter(Converter):
    async def convert(self, ctx: "Context", argument: str) -> Member:
        if not ctx.guild_id:
            raise BadArgument("This command can only be used in a guild")
        ids = _extract_ids(argument)
        if not ids:
            raise BadArgument("Member ID must be numeric")
        data = await ctx.bot.api.guilds.get_guild_member_by_user_id(
            guild_id=ctx.guild_id,
            user_id=ids[-1],
        )
        return Member.from_dict(data, ctx.guild_id, client=ctx.bot)


class GuildConverter(Converter):
    async def convert(self, ctx: "Context", argument: str) -> Guild:
        ids = _extract_ids(argument)
        if not ids:
            raise BadArgument("Guild ID must be numeric")
        data = await ctx.bot.api.guilds.get_guild_information(guild_id=ids[-1])
        return Guild.from_dict(data, client=ctx.bot)


class TextChannelConverter(Converter):
    async def convert(self, ctx: "Context", argument: str) -> TextChannel:
        ids = _extract_ids(argument)
        if not ids:
            raise BadArgument("Channel ID must be numeric")
        data = await ctx.bot.api.channels.fetch_a_channel(channel_id=ids[-1])
        return TextChannel(ctx.bot, data)


class ChannelConverter(TextChannelConverter):
    pass


class RoleConverter(Converter):
    async def convert(self, ctx: "Context", argument: str) -> Role:
        if not ctx.guild_id:
            raise BadArgument("This command can only be used in a guild")
        roles = await ctx.bot.api.guilds.list_guild_roles(guild_id=ctx.guild_id)
        roles_list = [Role.from_dict(item, guild_id=ctx.guild_id, client=ctx.bot) for item in roles]
        ids = _extract_ids(argument)
        if ids:
            role_id = ids[-1]
            for role in roles_list:
                if role.id == role_id:
                    return role
        lowered = argument.lower()
        for role in roles_list:
            if role.name and role.name.lower() == lowered:
                return role
        raise BadArgument("Role not found")


class MessageConverter(Converter):
    async def convert(self, ctx: "Context", argument: str) -> Message:
        ids = _extract_ids(argument)
        if len(ids) >= 2:
            channel_id = ids[-2]
            message_id = ids[-1]
        elif len(ids) == 1:
            if not ctx.channel_id:
                raise BadArgument("Message ID provided without channel context")
            channel_id = ctx.channel_id
            message_id = ids[0]
        else:
            raise BadArgument("Message ID must be numeric")

        data = await ctx.bot.api.channels.fetch_a_message(
            channel_id=channel_id,
            message_id=message_id,
        )
        return Message(ctx.bot, data)


async def _convert_arg(ctx: "Context", param: inspect.Parameter, argument: str) -> Any:
    annotation = param.annotation
    if annotation is inspect._empty:
        return argument

    if annotation is str:
        return argument
    if annotation is int:
        return int(argument)
    if annotation is float:
        return float(argument)
    if annotation is bool:
        lowered = argument.lower()
        if lowered in ("true", "yes", "y", "on", "1"):
            return True
        if lowered in ("false", "no", "n", "off", "0"):
            return False
        raise BadArgument("Invalid boolean value")

    if annotation is User:
        return await UserConverter().convert(ctx, argument)
    if annotation is Member:
        return await MemberConverter().convert(ctx, argument)
    if annotation is Guild:
        return await GuildConverter().convert(ctx, argument)
    if annotation is TextChannel:
        return await TextChannelConverter().convert(ctx, argument)
    if annotation is Role:
        return await RoleConverter().convert(ctx, argument)
    if annotation is Message:
        return await MessageConverter().convert(ctx, argument)

    if isinstance(annotation, type) and issubclass(annotation, Converter):
        return await annotation().convert(ctx, argument)
    if isinstance(annotation, Converter):
        return await annotation.convert(ctx, argument)

    if callable(annotation):
        try:
            value = annotation(argument)
        except Exception as exc:
            raise BadArgument(str(exc)) from exc
        return value

    return argument


@dataclass
class Context:
    bot: "Bot"
    message: Message
    prefix: str
    invoked_with: str
    args: List[str]
    command: Optional["Command"] = None

    @property
    def author(self):
        return self.message.author

    @property
    def channel(self):
        return self.message.channel

    @property
    def channel_id(self):
        return self.message.channel_id

    @property
    def guild_id(self):
        return self.message.guild_id

    @property
    def guild(self):
        if self.guild_id:
            return self.bot.get_guild(self.guild_id)
        return None

    @property
    def clean_prefix(self) -> str:
        return self.prefix

    @property
    def valid(self) -> bool:
        return self.command is not None

    async def send(self, content: Optional[str] = None, **kwargs: Any):
        return await self.channel.send(content, **kwargs)

    async def reply(self, content: Optional[str] = None, **kwargs: Any):
        return await self.message.reply(content or "", **kwargs)

    async def typing(self) -> None:
        await self.channel.typing()

    async def send_help(self, command: Optional[Any] = None) -> None:
        help_command = self.bot.help_command
        if help_command is None:
            return
        if command is None:
            if self.command is None:
                await help_command.command_callback(self, command=None)
                return
            command = self.command.qualified_name
        elif isinstance(command, Command):
            command = command.qualified_name
        await help_command.command_callback(self, command=str(command))

    async def invoke(self, command: Optional["Command"] = None, *args: Any, **kwargs: Any) -> Any:
        target = command or self.command
        if target is None:
            raise CommandNotFound()
        return await target.callback(self, *args, **kwargs)

    async def reinvoke(self) -> None:
        await self.bot.invoke(self)


class Command:
    def __init__(
        self,
        func: CommandFunc,
        *,
        name: Optional[str] = None,
        aliases: Optional[Sequence[str]] = None,
        help: Optional[str] = None,
        brief: Optional[str] = None,
        usage: Optional[str] = None,
        hidden: bool = False,
    ) -> None:
        self.callback = func
        self.name = name or func.__name__
        self.aliases = list(aliases or [])
        self.help = help or (func.__doc__ or "")
        self.brief = brief
        self.usage = usage
        self.hidden = hidden
        self.checks = list(getattr(func, "__commands_checks__", []))
        self.cooldown = getattr(func, "__commands_cooldown__", None)
        self.max_concurrency = getattr(func, "__commands_max_concurrency__", None)
        self.error_handler: Optional[Callable[[Context, CommandError], Awaitable[None]]] = None
        self.cog = getattr(func, "__commands_cog__", None)
        self.parent: Optional[Group] = None
        self._before_invoke: Optional[Callable[[Context], Awaitable[None]]] = None
        self._after_invoke: Optional[Callable[[Context], Awaitable[None]]] = None

    @property
    def qualified_name(self) -> str:
        if self.parent:
            return f"{self.parent.qualified_name} {self.name}"
        return self.name

    @property
    def short_doc(self) -> str:
        if self.brief:
            return self.brief
        if self.help:
            return self.help.splitlines()[0]
        return ""

    @property
    def signature(self) -> str:
        sig = inspect.signature(self.callback)
        params = list(sig.parameters.values())[1:]
        parts = []
        for param in params:
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                parts.append(f"[{param.name}...]")
            elif param.default is inspect._empty:
                parts.append(f"<{param.name}>")
            else:
                parts.append(f"[{param.name}={param.default}]")
        return " ".join(parts)

    def copy(self) -> "Command":
        cmd = Command(
            self.callback,
            name=self.name,
            aliases=self.aliases,
            help=self.help,
            brief=self.brief,
            usage=self.usage,
            hidden=self.hidden,
        )
        cmd.checks = list(self.checks)
        cmd.cooldown = self.cooldown
        cmd.max_concurrency = self.max_concurrency
        cmd.error_handler = self.error_handler
        cmd.cog = self.cog
        cmd.parent = self.parent
        cmd._before_invoke = self._before_invoke
        cmd._after_invoke = self._after_invoke
        return cmd

    def error(self, coro: Callable[[Context, CommandError], Awaitable[None]]):
        self.error_handler = coro
        return coro

    def before_invoke(self, coro: Callable[[Context], Awaitable[None]]):
        self._before_invoke = coro
        return coro

    def after_invoke(self, coro: Callable[[Context], Awaitable[None]]):
        self._after_invoke = coro
        return coro

    def reset_cooldown(self, ctx: Context) -> None:
        if self.cooldown:
            bucket = self.cooldown.get_bucket(ctx.message)
            bucket.tokens = bucket.rate
            bucket.window = 0.0

    def is_on_cooldown(self, ctx: Context) -> bool:
        if not self.cooldown:
            return False
        bucket = self.cooldown.get_bucket(ctx.message)
        if bucket.tokens > 0:
            return False
        return time.monotonic() < bucket.window + bucket.per

    def get_cooldown_retry_after(self, ctx: Context) -> float:
        if not self.cooldown:
            return 0.0
        bucket = self.cooldown.get_bucket(ctx.message)
        return max(0.0, bucket.window + bucket.per - time.monotonic())

    async def can_run(self, ctx: Context) -> None:
        for check in self.checks:
            result = await _maybe_await(check(ctx))
            if not result:
                raise CheckFailure()

        if self.cooldown:
            retry_after = self.cooldown.update_rate_limit(ctx.message)
            if retry_after:
                raise CommandOnCooldown(retry_after)

        if self.max_concurrency:
            ok = await self.max_concurrency.acquire(ctx.message)
            if not ok:
                raise MaxConcurrencyReached()
            setattr(ctx, "_max_concurrency_acquired", True)

    async def invoke(self, ctx: Context) -> Any:
        sig = inspect.signature(self.callback)
        params = list(sig.parameters.values())
        if not params:
            return await self.callback()

        args = ctx.args
        converted: List[Any] = []
        arg_index = 0
        for param in params[1:]:
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                remaining = args[arg_index:]
                if param.annotation is not inspect._empty:
                    for value in remaining:
                        converted.append(await _convert_arg(ctx, param, value))
                else:
                    converted.extend(remaining)
                arg_index = len(args)
                break

            if arg_index >= len(args):
                if param.default is inspect._empty:
                    raise MissingRequiredArgument(param)
                converted.append(param.default)
                continue

            try:
                converted.append(await _convert_arg(ctx, param, args[arg_index]))
            except CommandError:
                raise
            except Exception as exc:
                raise ConversionError(param.annotation, args[arg_index], exc) from exc
            arg_index += 1

        return await self.callback(ctx, *converted)


class GroupMixin:
    def __init__(self, *, case_insensitive: bool = True) -> None:
        self.case_insensitive = case_insensitive
        self._commands: Dict[str, Command] = {}

    @property
    def commands(self) -> Dict[str, Command]:
        return self._commands

    @property
    def all_commands(self) -> Dict[str, Command]:
        return self._commands

    def walk_commands(self) -> Iterable[Command]:
        seen = set()
        for cmd in self._commands.values():
            if id(cmd) in seen:
                continue
            seen.add(id(cmd))
            yield cmd
            if isinstance(cmd, Group):
                yield from cmd.walk_commands()

    def add_command(self, command: Command) -> None:
        if isinstance(command, Group):
            command.case_insensitive = self.case_insensitive
        key = command.name.lower() if self.case_insensitive else command.name
        existing = self._commands.get(key)
        if existing and existing is not command:
            raise CommandRegistrationError(command.name)
        self._commands[key] = command
        for alias in command.aliases:
            alias_key = alias.lower() if self.case_insensitive else alias
            existing_alias = self._commands.get(alias_key)
            if existing_alias and existing_alias is not command:
                raise CommandRegistrationError(alias)
            self._commands[alias_key] = command

    def remove_command(self, name: str) -> Optional[Command]:
        key = name.lower() if self.case_insensitive else name
        return self._commands.pop(key, None)

    def get_command(self, name: str) -> Optional[Command]:
        if not name:
            return None
        parts = name.split()
        if not parts:
            return None
        key = parts[0].lower() if self.case_insensitive else parts[0]
        cmd = self._commands.get(key)
        if not cmd:
            return None
        for part in parts[1:]:
            if not isinstance(cmd, Group):
                return None
            cmd = cmd.get_command(part)
            if cmd is None:
                return None
        return cmd

    def command(
        self,
        name: Optional[str] = None,
        *,
        aliases: Optional[Sequence[str]] = None,
        help: Optional[str] = None,
        brief: Optional[str] = None,
        usage: Optional[str] = None,
        hidden: bool = False,
    ):
        def decorator(func: CommandFunc) -> Command:
            cmd = Command(
                func,
                name=name,
                aliases=aliases,
                help=help,
                brief=brief,
                usage=usage,
                hidden=hidden,
            )
            self.add_command(cmd)
            return cmd

        return decorator

    def group(
        self,
        name: Optional[str] = None,
        *,
        aliases: Optional[Sequence[str]] = None,
        help: Optional[str] = None,
        brief: Optional[str] = None,
        usage: Optional[str] = None,
        hidden: bool = False,
        invoke_without_command: bool = False,
    ):
        def decorator(func: CommandFunc) -> Group:
            grp = Group(
                func,
                name=name,
                aliases=aliases,
                help=help,
                brief=brief,
                usage=usage,
                hidden=hidden,
                invoke_without_command=invoke_without_command,
                case_insensitive=self.case_insensitive,
            )
            self.add_command(grp)
            return grp

        return decorator


class Group(Command, GroupMixin):
    def __init__(
        self,
        func: CommandFunc,
        *,
        name: Optional[str] = None,
        aliases: Optional[Sequence[str]] = None,
        help: Optional[str] = None,
        brief: Optional[str] = None,
        usage: Optional[str] = None,
        hidden: bool = False,
        invoke_without_command: bool = False,
        case_insensitive: bool = True,
    ) -> None:
        Command.__init__(
            self,
            func,
            name=name,
            aliases=aliases,
            help=help,
            brief=brief,
            usage=usage,
            hidden=hidden,
        )
        GroupMixin.__init__(self, case_insensitive=case_insensitive)
        self.invoke_without_command = invoke_without_command

    def copy(self) -> "Group":
        grp = Group(
            self.callback,
            name=self.name,
            aliases=self.aliases,
            help=self.help,
            brief=self.brief,
            usage=self.usage,
            hidden=self.hidden,
            invoke_without_command=self.invoke_without_command,
            case_insensitive=self.case_insensitive,
        )
        grp.checks = list(self.checks)
        grp.cooldown = self.cooldown
        grp.max_concurrency = self.max_concurrency
        grp.error_handler = self.error_handler
        grp.cog = self.cog
        grp.parent = self.parent
        grp._before_invoke = self._before_invoke
        grp._after_invoke = self._after_invoke
        for cmd in self.commands.values():
            if id(cmd) in {id(c) for c in grp.commands.values()}:
                continue
            grp.add_command(cmd.copy())
        return grp

    def resolve_subcommand(self, ctx: Context) -> Context:
        if not ctx.args:
            return ctx
        name = ctx.args[0]
        sub = self.get_command(name)
        if not sub:
            return ctx
        return Context(
            bot=ctx.bot,
            message=ctx.message,
            prefix=ctx.prefix,
            invoked_with=name,
            args=ctx.args[1:],
            command=sub,
        )


class Cog:
    @classmethod
    def listener(cls, name: Optional[str] = None):
        def decorator(func: Callable[..., Awaitable[None]]):
            setattr(func, "__commands_listener__", name or func.__name__)
            return func

        return decorator

    def get_commands(self) -> List[Command]:
        commands: List[Command] = []
        for _, value in inspect.getmembers(self):
            if isinstance(value, Command):
                cmd = value.copy()
                _bind_command_to_cog(cmd, self)
                commands.append(cmd)
        return commands

    def get_listeners(self) -> List[Tuple[str, Callable[..., Awaitable[None]]]]:
        listeners: List[Tuple[str, Callable[..., Awaitable[None]]]] = []
        for _, value in inspect.getmembers(self):
            listener_name = getattr(value, "__commands_listener__", None)
            if listener_name:
                listeners.append((listener_name, value))
        return listeners

    async def cog_before_invoke(self, ctx: "Context") -> None:
        return None

    async def cog_after_invoke(self, ctx: "Context") -> None:
        return None


class HelpCommand:
    def __init__(self, *, command_attrs: Optional[Dict[str, Any]] = None) -> None:
        self.command_attrs = command_attrs or {}
        self.context: Optional[Context] = None

    def copy(self) -> "HelpCommand":
        return HelpCommand(command_attrs=dict(self.command_attrs))

    async def prepare_help_command(self, ctx: Context, command: Optional[str]) -> None:
        self.context = ctx

    def _format_commands(self, mixin: GroupMixin) -> List[str]:
        if not self.context:
            return []
        prefix = self.context.clean_prefix
        lines: List[str] = ["Commands:"]

        def walk(current: GroupMixin, indent: int, chain: List[str]) -> None:
            seen = set()
            items = list(current.commands.values())
            items.sort(key=lambda c: c.name)
            for cmd in items:
                if id(cmd) in seen:
                    continue
                seen.add(id(cmd))
                if cmd.hidden:
                    continue
                qualified = " ".join(chain + [cmd.name])
                signature = cmd.signature
                summary = cmd.brief or cmd.help or ""
                usage = f"{prefix}{qualified}"
                if signature:
                    usage = f"{usage} {signature}"
                line = f"{'  ' * indent}{usage}"
                if summary:
                    line = f"{line} - {summary}"
                lines.append(line.rstrip())
                if isinstance(cmd, Group):
                    walk(cmd, indent + 1, chain + [cmd.name])

        walk(mixin, 0, [])
        return lines

    async def send_bot_help(self, mapping: Dict[str, Command]) -> None:
        if not self.context:
            return
        lines = self._format_commands(self.context.bot)
        await self.context.send("\n".join(lines))

    async def send_command_help(self, command: Command) -> None:
        if not self.context:
            return
        usage = command.usage or command.qualified_name
        lines = [f"Usage: {self.context.clean_prefix}{usage}"]
        if command.help:
            lines.append(command.help)
        if isinstance(command, Group):
            if command.commands:
                subcommands = [cmd.name for cmd in command.commands.values()]
                unique = sorted(set(subcommands))
                lines.append("Subcommands: " + ", ".join(unique))
        await self.context.send("\n".join(lines))

    async def command_callback(self, ctx: Context, command: Optional[str] = None) -> None:
        await self.prepare_help_command(ctx, command)
        if command is None:
            await self.send_bot_help(ctx.bot.commands)
            return
        cmd = ctx.bot.get_command(command)
        if cmd is None:
            await ctx.send(f"Command not found: {command}")
            return
        await self.send_command_help(cmd)


class DefaultHelpCommand(HelpCommand):
    pass


def _bind_command_to_cog(command: Command, cog: Cog) -> None:
    callback = command.callback
    if hasattr(callback, "__get__"):
        command.callback = callback.__get__(cog, cog.__class__)
    command.cog = cog
    if isinstance(command, Group):
        seen = set()
        for sub in command.commands.values():
            if id(sub) in seen:
                continue
            seen.add(id(sub))
            _bind_command_to_cog(sub, cog)


class Bot(Client, GroupMixin):
    def __init__(
        self,
        command_prefix: str | Callable[["Bot", Message], Any] = "!",
        *,
        case_insensitive: bool = True,
        help_command: Optional[HelpCommand] = DefaultHelpCommand(),
        owner_id: Optional[str | int] = None,
        owner_ids: Optional[Iterable[str | int]] = None,
        **kwargs: Any,
    ) -> None:
        Client.__init__(self, **kwargs)
        GroupMixin.__init__(self, case_insensitive=case_insensitive)
        self.command_prefix = command_prefix
        self.help_command = help_command
        self._checks: List[CheckFunc] = []
        self._check_once: List[CheckFunc] = []
        self._cogs: Dict[str, Cog] = {}
        self._cog_commands: Dict[str, List[str]] = {}
        self._cog_listeners: Dict[str, List[Tuple[str, Callable[..., Awaitable[None]]]]] = {}
        self._before_invoke: Optional[Callable[[Context], Awaitable[None]]] = None
        self._after_invoke: Optional[Callable[[Context], Awaitable[None]]] = None
        self.extensions: Dict[str, Any] = {}
        self.owner_ids: set[str] = set()
        if owner_id is not None:
            self.owner_ids.add(str(owner_id))
        if owner_ids:
            self.owner_ids.update(str(item) for item in owner_ids)
        if self.help_command is not None:
            self._add_help_command(self.help_command)

    def _add_help_command(self, help_command: HelpCommand) -> None:
        help_command = help_command.copy()
        command = Command(
            help_command.command_callback,
            name="help",
            aliases=["commands"],
            help="Show help",
        )
        self.add_command(command)

    def before_invoke(self, coro: Callable[[Context], Awaitable[None]]):
        self._before_invoke = coro
        return coro

    def after_invoke(self, coro: Callable[[Context], Awaitable[None]]):
        self._after_invoke = coro
        return coro

    async def is_owner(self, user: Optional[User]) -> bool:
        if not user or not user.id:
            return False
        return str(user.id) in self.owner_ids

    def add_cog(self, cog: Cog, *, name: Optional[str] = None) -> None:
        cog_name = name or cog.__class__.__name__
        self._cogs[cog_name] = cog
        commands = cog.get_commands()
        self._cog_commands[cog_name] = []
        for cmd in commands:
            self.add_command(cmd)
            self._cog_commands[cog_name].append(cmd.name)
        listeners = cog.get_listeners()
        self._cog_listeners[cog_name] = listeners
        for event_name, listener in listeners:
            self.add_listener(listener, event_name)

    def remove_cog(self, name: str) -> None:
        self._cogs.pop(name, None)
        for cmd_name in self._cog_commands.pop(name, []):
            self.remove_command(cmd_name)
        for event_name, listener in self._cog_listeners.pop(name, []):
            if event_name in self._listeners and self._listeners[event_name] == listener:
                self._listeners.pop(event_name, None)

    def get_cog(self, name: str) -> Optional[Cog]:
        return self._cogs.get(name)

    @property
    def cogs(self) -> Dict[str, Cog]:
        return dict(self._cogs)

    def load_extension(self, name: str) -> None:
        if name in self.extensions:
            raise ExtensionAlreadyLoaded(name)
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            raise ExtensionFailed(name) from exc
        if not hasattr(module, "setup"):
            raise NoEntryPointError(name)
        try:
            module.setup(self)
        except Exception as exc:
            raise ExtensionFailed(name) from exc
        self.extensions[name] = module

    def unload_extension(self, name: str) -> None:
        module = self.extensions.get(name)
        if not module:
            raise ExtensionNotFound(name)
        if hasattr(module, "teardown"):
            module.teardown(self)
        self.extensions.pop(name, None)

    def reload_extension(self, name: str) -> None:
        if name not in self.extensions:
            raise ExtensionNotFound(name)
        self.unload_extension(name)
        self.load_extension(name)

    def add_check(self, func: CheckFunc, *, call_once: bool = False) -> None:
        if call_once:
            self._check_once.append(func)
        else:
            self._checks.append(func)

    def remove_check(self, func: CheckFunc, *, call_once: bool = False) -> None:
        checks = self._check_once if call_once else self._checks
        if func in checks:
            checks.remove(func)

    async def _run_checks(self, ctx: Context, *, call_once: bool = False) -> None:
        checks = self._check_once if call_once else self._checks
        for check in checks:
            result = await _maybe_await(check(ctx))
            if not result:
                raise CheckFailure()

    async def _dispatch(self, name: str, *args: Any) -> None:
        if name == "on_message" and args:
            await self.process_commands(args[0])
        await super()._dispatch(name, *args)

    async def get_prefix(self, message: Message) -> List[str]:
        prefix = self.command_prefix
        if callable(prefix):
            value = prefix(self, message)
            if inspect.isawaitable(value):
                value = await value
        else:
            value = prefix
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            return list(value)
        raise ValueError("Invalid command_prefix")

    async def process_commands(self, message: Message) -> None:
        if message.author and message.author.bot:
            return
        ctx = await self.get_context(message)
        if not ctx.valid:
            return
        await self.invoke(ctx)

    async def get_context(self, message: Message) -> Context:
        prefix = ""
        invoked_with = ""
        args: List[str] = []
        command: Optional[Command] = None

        if message.content:
            prefixes = await self.get_prefix(message)
            content = message.content
            invoked_prefix = None
            for p in prefixes:
                if content.startswith(p):
                    invoked_prefix = p
                    break

            if invoked_prefix is not None:
                raw = content[len(invoked_prefix):].strip()
                if raw:
                    parts = shlex.split(raw)
                    if parts:
                        invoked_with = parts[0]
                        args = parts[1:]
                        command = self.get_command(invoked_with)
                        prefix = invoked_prefix

        return Context(
            bot=self,
            message=message,
            prefix=prefix,
            invoked_with=invoked_with,
            args=args,
            command=command,
        )

    async def invoke(self, ctx: Context) -> None:
        cmd = ctx.command
        if cmd is None:
            await self._dispatch("on_command_error", ctx, CommandNotFound())
            return

        if isinstance(cmd, Group):
            sub_ctx = cmd.resolve_subcommand(ctx)
            if sub_ctx.command is not cmd:
                if cmd.invoke_without_command:
                    ok = await self._invoke_command(ctx, cmd)
                    if not ok:
                        return
                ctx = sub_ctx
                cmd = ctx.command

        await self._invoke_command(ctx, cmd)

    async def _invoke_command(self, ctx: Context, cmd: Command) -> bool:
        try:
            await self._run_checks(ctx, call_once=True)
            await self._run_checks(ctx, call_once=False)
            await cmd.can_run(ctx)
            await self._dispatch("on_command", ctx)
            await self._call_before_hooks(ctx, cmd)
            await cmd.invoke(ctx)
            await self._call_after_hooks(ctx, cmd)
            await self._dispatch("on_command_completion", ctx)
            return True
        except CommandError as exc:
            await self._handle_command_error(ctx, cmd, exc)
        except Exception as exc:
            await self._handle_command_error(ctx, cmd, CommandInvokeError(exc))
        finally:
            if getattr(ctx, "_max_concurrency_acquired", False) and cmd.max_concurrency:
                cmd.max_concurrency.release(ctx.message)
                setattr(ctx, "_max_concurrency_acquired", False)
        return False

    async def _call_before_hooks(self, ctx: Context, cmd: Command) -> None:
        if self._before_invoke:
            await _maybe_await(self._before_invoke(ctx))
        if cmd.cog:
            await _maybe_await(cmd.cog.cog_before_invoke(ctx))
        if cmd._before_invoke:
            await _maybe_await(cmd._before_invoke(ctx))

    async def _call_after_hooks(self, ctx: Context, cmd: Command) -> None:
        if cmd._after_invoke:
            await _maybe_await(cmd._after_invoke(ctx))
        if cmd.cog:
            await _maybe_await(cmd.cog.cog_after_invoke(ctx))
        if self._after_invoke:
            await _maybe_await(self._after_invoke(ctx))

    async def _handle_command_error(self, ctx: Context, cmd: Command, error: CommandError) -> None:
        handled = False
        if cmd.error_handler:
            await cmd.error_handler(ctx, error)
            handled = True
        elif cmd.cog and hasattr(cmd.cog, "cog_command_error"):
            handler = getattr(cmd.cog, "cog_command_error")
            await _maybe_await(handler(ctx, error))
            handled = True

        if not handled:
            await self._dispatch("on_command_error", ctx, error)


# Module-level decorators for parity with discord.py

def command(
    name: Optional[str] = None,
    *,
    aliases: Optional[Sequence[str]] = None,
    help: Optional[str] = None,
    brief: Optional[str] = None,
    usage: Optional[str] = None,
    hidden: bool = False,
):
    def decorator(func: CommandFunc) -> Command:
        return Command(
            func,
            name=name,
            aliases=aliases,
            help=help,
            brief=brief,
            usage=usage,
            hidden=hidden,
        )

    return decorator


def group(
    name: Optional[str] = None,
    *,
    aliases: Optional[Sequence[str]] = None,
    help: Optional[str] = None,
    brief: Optional[str] = None,
    usage: Optional[str] = None,
    hidden: bool = False,
    invoke_without_command: bool = False,
):
    def decorator(func: CommandFunc) -> Group:
        return Group(
            func,
            name=name,
            aliases=aliases,
            help=help,
            brief=brief,
            usage=usage,
            hidden=hidden,
            invoke_without_command=invoke_without_command,
        )

    return decorator


__all__ = [
    "Bot",
    "Context",
    "Command",
    "Group",
    "GroupMixin",
    "Cog",
    "HelpCommand",
    "DefaultHelpCommand",
    "CommandError",
    "CommandNotFound",
    "CheckFailure",
    "NoPrivateMessage",
    "MissingPermissions",
    "BotMissingPermissions",
    "NotOwner",
    "MissingRole",
    "MissingAnyRole",
    "BotMissingRole",
    "BotMissingAnyRole",
    "UserInputError",
    "BadArgument",
    "MissingRequiredArgument",
    "ConversionError",
    "CommandOnCooldown",
    "CommandInvokeError",
    "CommandRegistrationError",
    "MaxConcurrencyReached",
    "ExtensionError",
    "ExtensionAlreadyLoaded",
    "ExtensionNotFound",
    "ExtensionFailed",
    "NoEntryPointError",
    "BucketType",
    "Cooldown",
    "CooldownMapping",
    "MaxConcurrency",
    "Converter",
    "UserConverter",
    "MemberConverter",
    "GuildConverter",
    "TextChannelConverter",
    "ChannelConverter",
    "RoleConverter",
    "MessageConverter",
    "check",
    "check_any",
    "cooldown",
    "max_concurrency",
    "guild_only",
    "dm_only",
    "is_owner",
    "has_permissions",
    "bot_has_permissions",
    "has_guild_permissions",
    "bot_has_guild_permissions",
    "is_admin",
    "has_role",
    "has_any_role",
    "bot_has_role",
    "bot_has_any_role",
    "when_mentioned",
    "when_mentioned_or",
    "command",
    "group",
]
