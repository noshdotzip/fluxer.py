import asyncio
import inspect
import logging
import platform
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Optional

from .api import API
from .allowed_mentions import AllowedMentions
from .errors import FluxerError, HTTPException, LoginFailure
from .gateway import Gateway
from .http import RESTClient
from .intents import Intents
from .models import (
    Call,
    Emoji,
    Guild,
    Invite,
    Member,
    Message,
    Presence,
    ReadState,
    RawMessageDelete,
    Reaction,
    Role,
    Sticker,
    TextChannel,
    User,
    VoiceState,
    Webhook,
    channel_from_data,
)
from .rest import REST


EventHandler = Callable[..., Awaitable[None]]
LOGGER = logging.getLogger("fluxer")


class Client:
    def __init__(
        self,
        *,
        intents: Optional[Intents] = None,
        token: Optional[str] = None,
        base_url: str = "https://api.fluxer.app",
        api_version: str = "1",
        token_prefix: str = "Bot ",
        allowed_mentions: Optional[AllowedMentions] = None,
    ) -> None:
        self.intents = intents or Intents.none()
        self.token = token
        self._os = platform.system().lower()
        self.allowed_mentions = allowed_mentions

        self.http = RESTClient(
            token=token,
            base_url=base_url,
            api_version=api_version,
            token_prefix=token_prefix,
        )
        self.api = API(self)
        self.rest = REST(self)
        self.gateway = Gateway(self)

        self._listeners: Dict[str, EventHandler] = {}
        self.user: Optional[User] = None
        self._user_raw: Optional[dict] = None
        self._message_cache: "OrderedDict[str, Message]" = OrderedDict()
        self._message_cache_max = 1000
        self._channel_cache: Dict[str, TextChannel] = {}
        self._guild_cache: Dict[str, Guild] = {}
        self._waiters: Dict[str, list[tuple[asyncio.Future, Optional[Callable[..., Any]]]]] = {}

    def event(self, coro: EventHandler) -> EventHandler:
        self._listeners[coro.__name__] = coro
        return coro

    def listen(self, name: Optional[str] = None):
        def decorator(coro: EventHandler) -> EventHandler:
            self.add_listener(coro, name=name)
            return coro

        return decorator

    def add_listener(self, coro: EventHandler, name: Optional[str] = None) -> None:
        self._listeners[name or coro.__name__] = coro

    def remove_listener(self, name: str) -> None:
        self._listeners.pop(name, None)

    def __getattr__(self, item: str):
        # Allow direct access to API groups: client.admin.*, client.oauth2.*, etc.
        if "api" in self.__dict__:
            groups = self.api.list_groups(include_aliases=True)
            if item in groups:
                return groups[item]
        raise AttributeError(item)

    def _set_user(self, user_payload: Any) -> None:
        self._user_raw = user_payload
        if isinstance(user_payload, dict):
            self.user = User.from_dict(user_payload, client=self)
        else:
            self.user = None

    def _cache_message(self, message: Message) -> None:
        if not message or not message.id:
            return
        self._message_cache[message.id] = message
        self._message_cache.move_to_end(message.id)
        while len(self._message_cache) > self._message_cache_max:
            self._message_cache.popitem(last=False)

    def _pop_message(self, message_id: Optional[str]) -> Optional[Message]:
        if not message_id:
            return None
        return self._message_cache.pop(message_id, None)

    def _get_message(self, message_id: Optional[str]) -> Optional[Message]:
        if not message_id:
            return None
        return self._message_cache.get(message_id)

    def _cache_channel(self, channel: TextChannel) -> None:
        if channel and channel.id:
            self._channel_cache[str(channel.id)] = channel

    def _cache_guild(self, guild: Guild) -> None:
        if guild and guild.id:
            self._guild_cache[str(guild.id)] = guild

    async def _dispatch_gateway_event(self, event_name: str, data: Any) -> None:
        handlers = {
            "READY": self._handle_ready,
            "RESUMED": self._handle_resumed,
            "MESSAGE_CREATE": self._handle_message_create,
            "MESSAGE_UPDATE": self._handle_message_update,
            "MESSAGE_DELETE": self._handle_message_delete,
            "MESSAGE_DELETE_BULK": self._handle_message_delete_bulk,
            "MESSAGE_REACTION_ADD": self._handle_reaction_event,
            "MESSAGE_REACTION_REMOVE": self._handle_reaction_event,
            "MESSAGE_REACTION_REMOVE_ALL": self._handle_reaction_event,
            "MESSAGE_REACTION_REMOVE_EMOJI": self._handle_reaction_event,
            "CHANNEL_CREATE": self._handle_channel_event,
            "CHANNEL_UPDATE": self._handle_channel_event,
            "CHANNEL_DELETE": self._handle_channel_event,
            "GUILD_CREATE": self._handle_guild_event,
            "GUILD_UPDATE": self._handle_guild_event,
            "GUILD_DELETE": self._handle_guild_event,
            "GUILD_MEMBER_ADD": self._handle_member_event,
            "GUILD_MEMBER_UPDATE": self._handle_member_event,
            "GUILD_MEMBER_REMOVE": self._handle_member_event,
            "GUILD_ROLE_CREATE": self._handle_role_event,
            "GUILD_ROLE_UPDATE": self._handle_role_event,
            "GUILD_ROLE_DELETE": self._handle_role_event,
            "GUILD_EMOJIS_UPDATE": self._handle_emoji_event,
            "GUILD_STICKERS_UPDATE": self._handle_sticker_event,
            "INVITE_CREATE": self._handle_invite_event,
            "INVITE_DELETE": self._handle_invite_event,
            "PRESENCE_UPDATE": self._handle_presence_event,
            "VOICE_STATE_UPDATE": self._handle_voice_state_event,
            "VOICE_SERVER_UPDATE": self._handle_voice_server_event,
            "CALL_CREATE": self._handle_call_event,
            "CALL_UPDATE": self._handle_call_event,
            "CALL_DELETE": self._handle_call_event,
            "TYPING_START": self._handle_typing_event,
            "WEBHOOKS_UPDATE": self._handle_webhooks_update,
            "RELATIONSHIP_ADD": self._handle_relationship_event,
            "RELATIONSHIP_UPDATE": self._handle_relationship_event,
            "RELATIONSHIP_REMOVE": self._handle_relationship_event,
            "READ_STATE_UPDATE": self._handle_read_state_event,
        }

        handler = handlers.get(event_name)
        if handler:
            await handler(event_name, data)

        if event_name not in {"READY", "RESUMED"}:
            snake_event = event_name.lower()
            await self._dispatch(f"on_{snake_event}", data)
        await self._dispatch("on_raw_event", event_name, data)

    async def _handle_ready(self, _: str, data: Any) -> None:
        self._set_user(data.get("user"))
        if self.user:
            LOGGER.info("Logged in as %s (%s)", self.user, self.user.id)
        await self._dispatch("on_ready")
        await self._dispatch("on_ready_raw", data)

    async def _handle_resumed(self, _: str, data: Any) -> None:
        await self._dispatch("on_resumed", data)

    async def _handle_message_create(self, _: str, data: Any) -> None:
        msg = Message(self, data)
        self._cache_message(msg)
        await self._dispatch("on_message", msg)

    async def _handle_message_update(self, _: str, data: Any) -> None:
        after = Message(self, data)
        before = self._get_message(after.id)
        self._cache_message(after)
        await self._dispatch("on_message_edit", before, after)

    async def _handle_message_delete(self, _: str, data: Any) -> None:
        msg_id = data.get("id") or data.get("message_id")
        cached = self._pop_message(msg_id)
        if cached:
            await self._dispatch("on_message_delete", cached)
        else:
            await self._dispatch("on_message_delete", RawMessageDelete.from_dict(data))
        await self._dispatch("on_raw_message_delete", data)

    async def _handle_message_delete_bulk(self, _: str, data: Any) -> None:
        await self._dispatch("on_bulk_message_delete", data)
        await self._dispatch("on_raw_bulk_message_delete", data)

    async def _handle_reaction_event(self, event: str, data: Any) -> None:
        reaction = Reaction.from_dict(data)
        if event == "MESSAGE_REACTION_ADD":
            await self._dispatch("on_reaction_add", reaction)
        elif event == "MESSAGE_REACTION_REMOVE":
            await self._dispatch("on_reaction_remove", reaction)
        elif event == "MESSAGE_REACTION_REMOVE_ALL":
            await self._dispatch("on_reaction_clear", reaction)
        elif event == "MESSAGE_REACTION_REMOVE_EMOJI":
            await self._dispatch("on_reaction_clear_emoji", reaction)

    async def _handle_channel_event(self, event: str, data: Any) -> None:
        channel = channel_from_data(self, data)
        self._cache_channel(channel)
        if event == "CHANNEL_CREATE":
            await self._dispatch("on_channel_create", channel)
        elif event == "CHANNEL_UPDATE":
            await self._dispatch("on_channel_update", channel)
        elif event == "CHANNEL_DELETE":
            await self._dispatch("on_channel_delete", channel)

    async def _handle_guild_event(self, event: str, data: Any) -> None:
        guild = Guild.from_dict(data, client=self)
        self._cache_guild(guild)
        if event == "GUILD_CREATE":
            await self._dispatch("on_guild_join", guild)
        elif event == "GUILD_UPDATE":
            await self._dispatch("on_guild_update", guild)
        elif event == "GUILD_DELETE":
            await self._dispatch("on_guild_remove", guild)

    async def _handle_member_event(self, event: str, data: Any) -> None:
        guild_id = data.get("guild_id") or data.get("guild", {}).get("id")
        member = Member.from_dict(data, guild_id, client=self) if guild_id else data
        if event == "GUILD_MEMBER_ADD":
            await self._dispatch("on_member_join", member)
        elif event == "GUILD_MEMBER_UPDATE":
            await self._dispatch("on_member_update", member)
        elif event == "GUILD_MEMBER_REMOVE":
            await self._dispatch("on_member_remove", member)

    async def _handle_role_event(self, event: str, data: Any) -> None:
        role_data = data.get("role") if isinstance(data, dict) else data
        role = Role.from_dict(role_data) if isinstance(role_data, dict) else role_data
        if event == "GUILD_ROLE_CREATE":
            await self._dispatch("on_guild_role_create", role)
        elif event == "GUILD_ROLE_UPDATE":
            await self._dispatch("on_guild_role_update", role)
        elif event == "GUILD_ROLE_DELETE":
            await self._dispatch("on_guild_role_delete", role)

    async def _handle_emoji_event(self, _: str, data: Any) -> None:
        emojis = [Emoji.from_dict(e) for e in data.get("emojis", [])] if isinstance(data, dict) else []
        await self._dispatch("on_guild_emojis_update", emojis)

    async def _handle_sticker_event(self, _: str, data: Any) -> None:
        stickers = [Sticker.from_dict(s) for s in data.get("stickers", [])] if isinstance(data, dict) else []
        await self._dispatch("on_guild_stickers_update", stickers)

    async def _handle_invite_event(self, event: str, data: Any) -> None:
        invite = Invite.from_dict(data, client=self)
        if event == "INVITE_CREATE":
            await self._dispatch("on_invite_create", invite)
        elif event == "INVITE_DELETE":
            await self._dispatch("on_invite_delete", invite)

    async def _handle_presence_event(self, _: str, data: Any) -> None:
        presence = Presence.from_dict(data, client=self)
        await self._dispatch("on_presence_update", presence)

    async def _handle_voice_state_event(self, _: str, data: Any) -> None:
        voice = VoiceState.from_dict(data)
        await self._dispatch("on_voice_state_update", voice)

    async def _handle_voice_server_event(self, _: str, data: Any) -> None:
        await self._dispatch("on_voice_server_update", data)

    async def _handle_call_event(self, event: str, data: Any) -> None:
        call = Call.from_dict(data)
        if event == "CALL_CREATE":
            await self._dispatch("on_call_create", call)
        elif event == "CALL_UPDATE":
            await self._dispatch("on_call_update", call)
        elif event == "CALL_DELETE":
            await self._dispatch("on_call_delete", call)

    async def _handle_typing_event(self, _: str, data: Any) -> None:
        await self._dispatch("on_typing", data)

    async def _handle_webhooks_update(self, _: str, data: Any) -> None:
        await self._dispatch("on_webhooks_update", data)

    async def _handle_relationship_event(self, event: str, data: Any) -> None:
        if event == "RELATIONSHIP_ADD":
            await self._dispatch("on_relationship_add", data)
        elif event == "RELATIONSHIP_UPDATE":
            await self._dispatch("on_relationship_update", data)
        elif event == "RELATIONSHIP_REMOVE":
            await self._dispatch("on_relationship_remove", data)

    async def _handle_read_state_event(self, _: str, data: Any) -> None:
        state = ReadState.from_dict(data)
        await self._dispatch("on_read_state_update", state)

    async def _dispatch(self, name: str, *args: Any) -> None:
        waiters = self._waiters.get(name)
        if waiters:
            to_remove: list[tuple[asyncio.Future, Optional[Callable[..., Any]]]] = []
            for future, check in list(waiters):
                if future.done():
                    to_remove.append((future, check))
                    continue
                if check is None:
                    future.set_result(args[0] if len(args) == 1 else args)
                    to_remove.append((future, check))
                    continue
                try:
                    result = check(*args)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    future.set_exception(exc)
                    to_remove.append((future, check))
                    continue
                if result:
                    future.set_result(args[0] if len(args) == 1 else args)
                    to_remove.append((future, check))
            if to_remove:
                remaining = [item for item in waiters if item not in to_remove]
                if remaining:
                    self._waiters[name] = remaining
                else:
                    self._waiters.pop(name, None)
        handler = self._listeners.get(name)
        if handler:
            try:
                await handler(*args)
            except Exception as exc:
                LOGGER.exception("Error in event handler %s: %s", name, exc)

    async def wait_for(
        self,
        event: str,
        *,
        check: Optional[Callable[..., Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        event_name = event if event.startswith("on_") else f"on_{event}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._waiters.setdefault(event_name, []).append((future, check))
        if timeout is not None:
            return await asyncio.wait_for(future, timeout=timeout)
        return await future

    async def login(self, token: str) -> None:
        self.token = token
        self.http.set_token(token)

    async def change_presence(
        self,
        *,
        status: Optional[str] = None,
        activity: Optional[dict] = None,
        afk: bool = False,
        since: Optional[int] = None,
    ) -> None:
        payload = {
            "status": status,
            "afk": afk,
            "since": since,
            "activities": [activity] if activity else [],
        }
        await self.gateway.send({"op": 3, "d": payload})

    def get_channel(self, channel_id: str) -> Optional[TextChannel]:
        return self._channel_cache.get(str(channel_id))

    def get_guild(self, guild_id: str) -> Optional[Guild]:
        return self._guild_cache.get(str(guild_id))

    async def fetch_channel(self, channel_id: str) -> TextChannel:
        data = await self.http.get_channel(str(channel_id))
        channel = channel_from_data(self, data)
        self._cache_channel(channel)
        return channel

    async def fetch_guild(self, guild_id: str) -> Guild:
        data = await self.api.guilds.get_guild_information(guild_id=str(guild_id))
        guild = Guild.from_dict(data, client=self)
        self._cache_guild(guild)
        return guild

    async def fetch_user(self, user_id: str) -> User:
        data = await self.api.users.get_user_by_id(user_id=str(user_id))
        return User.from_dict(data, client=self)

    async def fetch_member(self, guild_id: str, user_id: str) -> Member:
        data = await self.api.guilds.get_guild_member_by_user_id(
            guild_id=str(guild_id),
            user_id=str(user_id),
        )
        return Member.from_dict(data, str(guild_id), client=self)

    async def create_dm(self, user: User | str) -> TextChannel:
        recipient_id = user.id if isinstance(user, User) else str(user)
        data = await self.api.users.create_private_channel(recipient_id=recipient_id)
        channel = channel_from_data(self, data)
        self._cache_channel(channel)
        return channel

    async def start(self, token: Optional[str] = None) -> None:
        if token:
            self.token = token
            self.http.set_token(token)

        if not self.token:
            raise FluxerError("Token is required to start the client")

        # Accept tokens with common prefixes.
        lowered = self.token.lower()
        if lowered.startswith("bot "):
            self.token = self.token[4:]
            self.http.set_token(self.token)
        elif lowered.startswith("bearer "):
            self.token = self.token[7:]
            self.http.set_token(self.token)

        LOGGER.info("Starting Fluxer client")
        await self.http.start()
        try:
            await self.gateway.connect()
        except asyncio.CancelledError:
            await self.close()
            raise
        except HTTPException as exc:
            await self.close()
            if exc.status in (401, 403):
                raise LoginFailure("Invalid token") from exc
            raise
        except Exception:
            await self.close()
            raise

    def run(self, token: Optional[str] = None) -> None:
        try:
            asyncio.run(self.start(token))
        except KeyboardInterrupt:
            LOGGER.info("Received KeyboardInterrupt, shutting down")
            try:
                asyncio.run(self.close())
            except Exception:
                pass

    async def close(self) -> None:
        LOGGER.info("Closing Fluxer client")
        await self.gateway.close()
        await self.http.close()
