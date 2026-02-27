from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .allowed_mentions import AllowedMentions
from .embeds import Embed
from .enums import ChannelType
from .files import File
from .permissions import PermissionOverwrite, Permissions
from .utils import snowflake_time
from .voice import VoiceClient


@dataclass
class User:
    id: str
    username: Optional[str] = None
    discriminator: Optional[str] = None
    bot: bool = False
    raw: Dict[str, Any] = None
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], client: Any = None) -> "User":
        if data is None:
            return cls(id="0", username=None, discriminator=None, bot=False, raw={}, _client=client)
        return cls(
            id=str(data.get("id")),
            username=data.get("username"),
            discriminator=data.get("discriminator"),
            bot=bool(data.get("bot") or data.get("is_bot") or False),
            raw=data,
            _client=client,
        )

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    async def create_dm(self):
        if not self._client:
            raise RuntimeError("User has no client attached")
        data = await self._client.api.users.create_private_channel(recipient_id=self.id)
        return channel_from_data(self._client, data)

    async def send(self, content: Optional[str] = None, **kwargs: Any) -> "Message":
        channel = await self.create_dm()
        return await channel.send(content, **kwargs)

    def __str__(self) -> str:
        if self.discriminator:
            return f"{self.username}#{self.discriminator}"
        return self.username or self.id


@dataclass
class Channel:
    id: str
    type: Optional[int] = None
    name: Optional[str] = None
    guild_id: Optional[str] = None
    raw: Dict[str, Any] = None


class TextChannel(Channel):
    def __init__(self, client, data: Dict[str, Any]):
        super().__init__(
            id=str(data.get("id")),
            type=data.get("type"),
            name=data.get("name"),
            guild_id=data.get("guild_id"),
            raw=data,
        )
        self._client = client

    async def send(
        self,
        content: Optional[str] = None,
        **kwargs: Any,
    ) -> "Message":
        payload = {}
        file = kwargs.pop("file", None)
        files = kwargs.pop("files", None)
        embed = kwargs.pop("embed", None)
        embeds = kwargs.pop("embeds", None)
        allowed_mentions = kwargs.pop("allowed_mentions", None)
        reference = kwargs.pop("reference", None)

        if file is not None and files is not None:
            raise ValueError("Use file or files, not both")
        if file is not None:
            files = [file]

        if content is not None:
            payload["content"] = content

        if embed is not None and embeds is not None:
            raise ValueError("Use embed or embeds, not both")
        if embed is not None:
            embeds = [embed]
        if embeds is not None:
            converted = []
            for item in embeds:
                if isinstance(item, Embed):
                    converted.append(item.to_dict())
                else:
                    converted.append(item)
            payload["embeds"] = converted

        if reference is not None:
            if isinstance(reference, Message):
                payload["message_reference"] = {"message_id": reference.id}
            elif isinstance(reference, dict):
                payload["message_reference"] = reference
            else:
                payload["message_reference"] = {"message_id": str(reference)}

        if allowed_mentions is None:
            allowed_mentions = getattr(self._client, "allowed_mentions", None)
        if isinstance(allowed_mentions, AllowedMentions):
            payload["allowed_mentions"] = allowed_mentions.to_dict()
        elif isinstance(allowed_mentions, dict):
            payload["allowed_mentions"] = allowed_mentions

        payload.update(kwargs)
        if files is not None:
            attachments = payload.get("attachments")
            if attachments is None:
                attachments = []
                for idx, f in enumerate(files):
                    if isinstance(f, File):
                        attachments.append(
                            {"id": idx, "filename": f.filename, "description": f.description}
                        )
                if attachments:
                    payload["attachments"] = attachments
            data = await self._client.http.request(
                "POST",
                f"/channels/{self.id}/messages",
                json=payload,
                files=files,
            )
        else:
            data = await self._client.http.create_message(self.id, payload)
        return Message(self._client, data)

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    async def typing(self) -> None:
        await self._client.http.trigger_typing(self.id)

    async def history(self, **params: Any):
        data = await self._client.http.list_channel_messages(self.id, **params)
        return [Message(self._client, item) for item in data]

    async def fetch_message(self, message_id: str) -> "Message":
        data = await self._client.http.request(
            "GET", f"/channels/{self.id}/messages/{message_id}"
        )
        return Message(self._client, data)

    async def edit(self, **kwargs: Any) -> "TextChannel":
        data = await self._client.http.request("PATCH", f"/channels/{self.id}", json=kwargs)
        return TextChannel(self._client, data)

    async def delete(self) -> None:
        await self._client.http.request("DELETE", f"/channels/{self.id}")

    async def pins(self) -> List["Message"]:
        data = await self._client.http.request("GET", f"/channels/{self.id}/messages/pins")
        return [Message(self._client, item) for item in data]

    async def bulk_delete(self, messages: List["Message" | str]) -> None:
        ids = [m.id if isinstance(m, Message) else str(m) for m in messages]
        await self._client.http.request(
            "POST",
            f"/channels/{self.id}/messages/bulk-delete",
            json={"messages": ids},
        )

    async def schedule_message(self, content: Optional[str] = None, **kwargs: Any) -> Any:
        payload = {}
        if content is not None:
            payload["content"] = content
        payload.update(kwargs)
        return await self._client.http.request(
            "POST",
            f"/channels/{self.id}/messages/schedule",
            json=payload,
        )

    async def set_permissions(self, target: Any, overwrite: PermissionOverwrite | None = None, **kwargs: Any) -> None:
        if overwrite is None:
            overwrite = PermissionOverwrite(**kwargs)
        if hasattr(target, "id"):
            overwrite_id = getattr(target, "id")
        else:
            overwrite_id = target
        payload = overwrite.to_dict()
        await self._client.http.request(
            "PUT",
            f"/channels/{self.id}/permissions/{overwrite_id}",
            json=payload,
        )

    async def remove_permissions(self, target: Any) -> None:
        overwrite_id = getattr(target, "id", target)
        await self._client.http.request(
            "DELETE",
            f"/channels/{self.id}/permissions/{overwrite_id}",
        )

    async def create_invite(self, **kwargs: Any):
        data = await self._client.http.request(
            "POST",
            f"/channels/{self.id}/invites",
            json=kwargs or None,
        )
        return Invite.from_dict(data, client=self._client)

    async def ring_call(self, **kwargs: Any) -> Any:
        return await self._client.http.request(
            "POST",
            f"/channels/{self.id}/call/ring",
            json=kwargs or None,
        )

    async def call_status(self) -> Any:
        return await self._client.http.request("GET", f"/channels/{self.id}/call")

    async def stop_ringing(self) -> Any:
        return await self._client.http.request(
            "POST",
            f"/channels/{self.id}/call/stop-ringing",
        )

    async def end_call(self) -> Any:
        return await self._client.http.request(
            "POST",
            f"/channels/{self.id}/call/end",
        )

    async def update_call_region(self, **kwargs: Any) -> Any:
        return await self._client.http.request(
            "PATCH",
            f"/channels/{self.id}/call",
            json=kwargs or None,
        )

    async def list_rtc_regions(self) -> Any:
        return await self._client.http.request(
            "GET",
            f"/channels/{self.id}/rtc-regions",
        )


class DMChannel(TextChannel):
    pass


class VoiceChannel(TextChannel):
    async def connect(self, *, timeout: float = 60.0) -> VoiceClient:
        voice = VoiceClient(self._client, self, timeout=timeout)
        await voice.connect(timeout=timeout)
        return voice


@dataclass
class Message:
    _client: Any
    id: str
    content: Optional[str]
    channel_id: str
    author: User
    guild_id: Optional[str]
    raw: Dict[str, Any]

    def __init__(self, client, data: Dict[str, Any]):
        self._client = client
        self.id = str(data.get("id"))
        self.content = data.get("content")
        self.channel_id = str(data.get("channel_id"))
        self.guild_id = data.get("guild_id")
        self.author = User.from_dict(data.get("author"), client=client)
        self.embeds = [Embed.from_dict(item) for item in data.get("embeds", []) or []]
        self.attachments = [
            Attachment(
                id=str(item.get("id")),
                filename=item.get("filename"),
                content_type=item.get("content_type"),
                size=item.get("size"),
                url=item.get("url"),
                proxy_url=item.get("proxy_url"),
                raw=item,
            )
            for item in data.get("attachments", []) or []
        ]
        self.raw = data

    @property
    def channel(self) -> TextChannel:
        return TextChannel(self._client, {"id": self.channel_id, "guild_id": self.guild_id})

    @property
    def created_at(self):
        return snowflake_time(self.id)

    async def reply(self, content: str, **kwargs: Any) -> "Message":
        mention_author = kwargs.pop("mention_author", None)
        allowed_mentions = kwargs.get("allowed_mentions")
        if mention_author is not None:
            if allowed_mentions is None:
                allowed_mentions = getattr(self._client, "allowed_mentions", None)
            if isinstance(allowed_mentions, AllowedMentions):
                allowed_mentions = allowed_mentions.merge(
                    AllowedMentions(replied_user=bool(mention_author))
                )
            elif isinstance(allowed_mentions, dict):
                allowed_mentions = dict(allowed_mentions)
                allowed_mentions["replied_user"] = bool(mention_author)
            else:
                allowed_mentions = AllowedMentions(replied_user=bool(mention_author))
            kwargs["allowed_mentions"] = allowed_mentions
        kwargs.setdefault("message_reference", {"message_id": self.id})
        return await self.channel.send(content, **kwargs)

    async def edit(self, *, content: Optional[str] = None, **kwargs: Any) -> "Message":
        if content is not None:
            kwargs["content"] = content
        embed = kwargs.pop("embed", None)
        embeds = kwargs.pop("embeds", None)
        if embed is not None and embeds is not None:
            raise ValueError("Use embed or embeds, not both")
        if embed is not None:
            embeds = [embed]
        if embeds is not None:
            converted = []
            for item in embeds:
                if isinstance(item, Embed):
                    converted.append(item.to_dict())
                else:
                    converted.append(item)
            kwargs["embeds"] = converted
        data = await self._client.http.request(
            "PATCH",
            f"/channels/{self.channel_id}/messages/{self.id}",
            json=kwargs,
        )
        return Message(self._client, data)

    async def delete(self) -> None:
        await self._client.http.request(
            "DELETE",
            f"/channels/{self.channel_id}/messages/{self.id}",
        )

    async def add_reaction(self, emoji: Any) -> None:
        encoded = _encode_emoji(emoji)
        await self._client.http.request(
            "PUT",
            f"/channels/{self.channel_id}/messages/{self.id}/reactions/{encoded}/@me",
        )

    async def remove_reaction(self, emoji: Any, user: Any = None) -> None:
        encoded = _encode_emoji(emoji)
        if user is None:
            await self._client.http.request(
                "DELETE",
                f"/channels/{self.channel_id}/messages/{self.id}/reactions/{encoded}/@me",
            )
            return
        user_id = getattr(user, "id", user)
        await self._client.http.request(
            "DELETE",
            f"/channels/{self.channel_id}/messages/{self.id}/reactions/{encoded}/{user_id}",
        )

    async def clear_reaction(self, emoji: Any) -> None:
        encoded = _encode_emoji(emoji)
        await self._client.http.request(
            "DELETE",
            f"/channels/{self.channel_id}/messages/{self.id}/reactions/{encoded}",
        )

    async def clear_reactions(self) -> None:
        await self._client.http.request(
            "DELETE",
            f"/channels/{self.channel_id}/messages/{self.id}/reactions",
        )

    async def pin(self) -> None:
        await self._client.http.request(
            "PUT",
            f"/channels/{self.channel_id}/pins/{self.id}",
        )

    async def unpin(self) -> None:
        await self._client.http.request(
            "DELETE",
            f"/channels/{self.channel_id}/pins/{self.id}",
        )


@dataclass
class Attachment:
    id: str
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    url: Optional[str] = None
    proxy_url: Optional[str] = None
    raw: Dict[str, Any] = None


@dataclass
class Guild:
    id: str
    name: Optional[str] = None
    raw: Dict[str, Any] = None
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], client: Any = None) -> "Guild":
        return cls(
            id=str(data.get("id")),
            name=data.get("name"),
            raw=data,
            _client=client,
        )

    async def fetch_channels(self) -> List[TextChannel]:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.list_guild_channels(guild_id=self.id)
        return [TextChannel(self._client, item) for item in data]

    async def fetch_members(self, **params: Any) -> List["Member"]:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.list_guild_members(guild_id=self.id, **params)
        return [Member.from_dict(item, self.id, client=self._client) for item in data]

    async def fetch_member(self, user_id: str) -> "Member":
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.get_guild_member_by_user_id(
            guild_id=self.id, user_id=str(user_id)
        )
        return Member.from_dict(data, self.id, client=self._client)

    async def fetch_roles(self) -> List["Role"]:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.list_guild_roles(guild_id=self.id)
        return [Role.from_dict(item, guild_id=self.id, client=self._client) for item in data]

    async def fetch_emojis(self) -> List["Emoji"]:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.list_guild_emojis(guild_id=self.id)
        return [Emoji.from_dict(item) for item in data]

    async def fetch_stickers(self) -> List["Sticker"]:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.list_guild_stickers(guild_id=self.id)
        return [Sticker.from_dict(item) for item in data]

    async def create_channel(self, **kwargs: Any) -> TextChannel:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.create_guild_channel(guild_id=self.id, **kwargs)
        return channel_from_data(self._client, data)

    async def create_role(self, **kwargs: Any) -> "Role":
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.create_guild_role(guild_id=self.id, **kwargs)
        return Role.from_dict(data, guild_id=self.id, client=self._client)

    async def edit(self, **kwargs: Any) -> "Guild":
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        data = await self._client.api.guilds.update_guild_settings(guild_id=self.id, **kwargs)
        return Guild.from_dict(data, client=self._client)

    async def leave(self) -> None:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        await self._client.api.guilds.leave_guild(guild_id=self.id)

    async def ban(self, user: Any, **kwargs: Any) -> None:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        user_id = getattr(user, "id", user)
        await self._client.api.guilds.ban_guild_member(guild_id=self.id, user_id=str(user_id), **kwargs)

    async def unban(self, user: Any) -> None:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        user_id = getattr(user, "id", user)
        await self._client.api.guilds.unban_guild_member(guild_id=self.id, user_id=str(user_id))

    async def kick(self, user: Any) -> None:
        if not self._client:
            raise RuntimeError("Guild has no client attached")
        user_id = getattr(user, "id", user)
        await self._client.api.guilds.remove_guild_member(guild_id=self.id, user_id=str(user_id))


@dataclass
class Member:
    user: User
    guild_id: str
    raw: Dict[str, Any] = None
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], guild_id: str, client: Any = None) -> "Member":
        return cls(
            user=User.from_dict(data.get("user"), client=client),
            guild_id=guild_id,
            raw=data,
            _client=client,
        )

    @property
    def id(self) -> str:
        return self.user.id

    async def send(self, content: Optional[str] = None, **kwargs: Any) -> "Message":
        return await self.user.send(content, **kwargs)

    async def add_roles(self, *roles: Any) -> None:
        if not self._client:
            raise RuntimeError("Member has no client attached")
        for role in roles:
            role_id = getattr(role, "id", role)
            await self._client.api.guilds.add_role_to_guild_member(
                guild_id=self.guild_id,
                user_id=self.user.id,
                role_id=str(role_id),
            )

    async def remove_roles(self, *roles: Any) -> None:
        if not self._client:
            raise RuntimeError("Member has no client attached")
        for role in roles:
            role_id = getattr(role, "id", role)
            await self._client.api.guilds.remove_role_from_guild_member(
                guild_id=self.guild_id,
                user_id=self.user.id,
                role_id=str(role_id),
            )

    async def ban(self, **kwargs: Any) -> None:
        if not self._client:
            raise RuntimeError("Member has no client attached")
        await self._client.api.guilds.ban_guild_member(
            guild_id=self.guild_id,
            user_id=self.user.id,
            **kwargs,
        )

    async def kick(self) -> None:
        if not self._client:
            raise RuntimeError("Member has no client attached")
        await self._client.api.guilds.remove_guild_member(
            guild_id=self.guild_id,
            user_id=self.user.id,
        )

    async def edit(self, **kwargs: Any) -> "Member":
        if not self._client:
            raise RuntimeError("Member has no client attached")
        data = await self._client.api.guilds.update_guild_member(
            guild_id=self.guild_id,
            user_id=self.user.id,
            **kwargs,
        )
        return Member.from_dict(data, self.guild_id, client=self._client)


@dataclass
class Role:
    id: str
    name: Optional[str] = None
    permissions: Optional[int] = None
    color: Optional[int] = None
    hoist: Optional[bool] = None
    position: Optional[int] = None
    managed: Optional[bool] = None
    mentionable: Optional[bool] = None
    raw: Dict[str, Any] = None
    guild_id: Optional[str] = None
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], guild_id: Optional[str] = None, client: Any = None) -> "Role":
        if data is None:
            return cls(id="0", raw={}, guild_id=guild_id, _client=client)
        perms = data.get("permissions")
        try:
            perms_value = int(perms) if perms is not None else None
        except (TypeError, ValueError):
            perms_value = None
        return cls(
            id=str(data.get("id")),
            name=data.get("name"),
            permissions=perms_value,
            color=data.get("color"),
            hoist=data.get("hoist"),
            position=data.get("position"),
            managed=data.get("managed"),
            mentionable=data.get("mentionable"),
            raw=data,
            guild_id=guild_id or data.get("guild_id"),
            _client=client,
        )

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"

    @property
    def permissions_object(self) -> Permissions:
        return Permissions(self.permissions or 0)

    async def edit(self, **kwargs: Any) -> "Role":
        if not self._client or not self.guild_id:
            raise RuntimeError("Role has no client or guild attached")
        data = await self._client.api.guilds.update_guild_role(
            guild_id=self.guild_id, role_id=self.id, **kwargs
        )
        return Role.from_dict(data, guild_id=self.guild_id, client=self._client)

    async def delete(self) -> None:
        if not self._client or not self.guild_id:
            raise RuntimeError("Role has no client or guild attached")
        await self._client.api.guilds.delete_guild_role(
            guild_id=self.guild_id, role_id=self.id
        )


@dataclass
class Emoji:
    id: Optional[str] = None
    name: Optional[str] = None
    animated: Optional[bool] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Emoji":
        if data is None:
            return cls(raw={})
        return cls(
            id=str(data.get("id")) if data.get("id") is not None else None,
            name=data.get("name"),
            animated=data.get("animated") or data.get("emoji_animated"),
            raw=data,
        )


@dataclass
class Sticker:
    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    format_type: Optional[int] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sticker":
        if data is None:
            return cls(raw={})
        return cls(
            id=str(data.get("id")) if data.get("id") is not None else None,
            name=data.get("name"),
            description=data.get("description"),
            format_type=data.get("format_type"),
            raw=data,
        )


@dataclass
class Invite:
    code: Optional[str] = None
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    inviter: Optional[User] = None
    uses: Optional[int] = None
    max_uses: Optional[int] = None
    max_age: Optional[int] = None
    temporary: Optional[bool] = None
    created_at: Optional[str] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], client: Any = None) -> "Invite":
        if data is None:
            return cls(raw={})
        return cls(
            code=data.get("code"),
            guild_id=data.get("guild_id"),
            channel_id=data.get("channel_id"),
            inviter=User.from_dict(data.get("inviter"), client=client)
            if data.get("inviter")
            else None,
            uses=data.get("uses"),
            max_uses=data.get("max_uses"),
            max_age=data.get("max_age"),
            temporary=data.get("temporary"),
            created_at=data.get("created_at"),
            raw=data,
        )


@dataclass
class Webhook:
    id: Optional[str] = None
    type: Optional[int] = None
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    name: Optional[str] = None
    avatar: Optional[str] = None
    token: Optional[str] = None
    raw: Dict[str, Any] = None
    _client: Any = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], client: Any = None) -> "Webhook":
        if data is None:
            return cls(raw={})
        return cls(
            id=str(data.get("id")) if data.get("id") is not None else None,
            type=data.get("type"),
            guild_id=data.get("guild_id"),
            channel_id=data.get("channel_id"),
            name=data.get("name"),
            avatar=data.get("avatar"),
            token=data.get("token"),
            raw=data,
            _client=client,
        )

    async def send(self, content: Optional[str] = None, **kwargs: Any) -> "Message":
        if not self._client:
            raise RuntimeError("Webhook has no client attached")
        if not self.id or not self.token:
            raise RuntimeError("Webhook id/token missing")
        payload = {}
        file = kwargs.pop("file", None)
        files = kwargs.pop("files", None)
        embed = kwargs.pop("embed", None)
        embeds = kwargs.pop("embeds", None)
        allowed_mentions = kwargs.pop("allowed_mentions", None)

        if file is not None and files is not None:
            raise ValueError("Use file or files, not both")
        if file is not None:
            files = [file]

        if content is not None:
            payload["content"] = content

        if embed is not None and embeds is not None:
            raise ValueError("Use embed or embeds, not both")
        if embed is not None:
            embeds = [embed]
        if embeds is not None:
            converted = []
            for item in embeds:
                if isinstance(item, Embed):
                    converted.append(item.to_dict())
                else:
                    converted.append(item)
            payload["embeds"] = converted

        if isinstance(allowed_mentions, AllowedMentions):
            payload["allowed_mentions"] = allowed_mentions.to_dict()
        elif isinstance(allowed_mentions, dict):
            payload["allowed_mentions"] = allowed_mentions

        payload.update(kwargs)
        if files is not None:
            attachments = payload.get("attachments")
            if attachments is None:
                attachments = []
                for idx, f in enumerate(files):
                    if isinstance(f, File):
                        attachments.append(
                            {"id": idx, "filename": f.filename, "description": f.description}
                        )
                if attachments:
                    payload["attachments"] = attachments
            data = await self._client.http.request(
                "POST",
                f"/webhooks/{self.id}/{self.token}",
                json=payload,
                files=files,
            )
        else:
            data = await self._client.http.request(
                "POST",
                f"/webhooks/{self.id}/{self.token}",
                json=payload,
            )
        return Message(self._client, data)

    async def edit(self, **kwargs: Any) -> "Webhook":
        if not self._client or not self.id:
            raise RuntimeError("Webhook has no client attached")
        if self.token:
            data = await self._client.api.webhooks.update_webhook_with_token(
                webhook_id=self.id, token=self.token, **kwargs
            )
        else:
            data = await self._client.api.webhooks.update_webhook(webhook_id=self.id, **kwargs)
        return Webhook.from_dict(data, client=self._client)

    async def delete(self) -> None:
        if not self._client or not self.id:
            raise RuntimeError("Webhook has no client attached")
        if self.token:
            await self._client.api.webhooks.delete_webhook_with_token(
                webhook_id=self.id, token=self.token
            )
        else:
            await self._client.api.webhooks.delete_webhook(webhook_id=self.id)


@dataclass
class Reaction:
    message_id: Optional[str] = None
    channel_id: Optional[str] = None
    guild_id: Optional[str] = None
    user_id: Optional[str] = None
    emoji: Optional[Emoji] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Reaction":
        if data is None:
            return cls(raw={})
        return cls(
            message_id=data.get("message_id"),
            channel_id=data.get("channel_id"),
            guild_id=data.get("guild_id"),
            user_id=data.get("user_id"),
            emoji=Emoji.from_dict(data.get("emoji")) if data.get("emoji") else None,
            raw=data,
        )


@dataclass
class VoiceState:
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    mute: Optional[bool] = None
    deaf: Optional[bool] = None
    self_mute: Optional[bool] = None
    self_deaf: Optional[bool] = None
    self_stream: Optional[bool] = None
    self_video: Optional[bool] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceState":
        if data is None:
            return cls(raw={})
        return cls(
            guild_id=data.get("guild_id"),
            channel_id=data.get("channel_id"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            mute=data.get("mute"),
            deaf=data.get("deaf"),
            self_mute=data.get("self_mute"),
            self_deaf=data.get("self_deaf"),
            self_stream=data.get("self_stream"),
            self_video=data.get("self_video"),
            raw=data,
        )


@dataclass
class Presence:
    user: Optional[User] = None
    status: Optional[str] = None
    mobile: Optional[bool] = None
    afk: Optional[bool] = None
    custom_status: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], client: Any = None) -> "Presence":
        if data is None:
            return cls(raw={})
        return cls(
            user=User.from_dict(data.get("user"), client=client) if data.get("user") else None,
            status=data.get("status"),
            mobile=data.get("mobile"),
            afk=data.get("afk"),
            custom_status=data.get("custom_status"),
            raw=data,
        )


@dataclass
class Call:
    channel_id: Optional[str] = None
    message_id: Optional[str] = None
    region: Optional[str] = None
    ringing: Optional[List[str]] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Call":
        if data is None:
            return cls(raw={})
        return cls(
            channel_id=data.get("channel_id"),
            message_id=data.get("message_id"),
            region=data.get("region"),
            ringing=data.get("ringing") or [],
            raw=data,
        )


@dataclass
class ReadState:
    id: Optional[str] = None
    mention_count: Optional[int] = None
    last_message_id: Optional[str] = None
    last_pin_timestamp: Optional[str] = None
    raw: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReadState":
        if data is None:
            return cls(raw={})
        return cls(
            id=data.get("id"),
            mention_count=data.get("mention_count"),
            last_message_id=data.get("last_message_id"),
            last_pin_timestamp=data.get("last_pin_timestamp"),
            raw=data,
        )


@dataclass
class RawMessageDelete:
    message_id: Optional[str]
    channel_id: Optional[str]
    guild_id: Optional[str]
    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RawMessageDelete":
        return cls(
            message_id=data.get("id") or data.get("message_id"),
            channel_id=data.get("channel_id"),
            guild_id=data.get("guild_id"),
            raw=data,
        )


def _encode_emoji(emoji: Any) -> str:
    if isinstance(emoji, Emoji):
        if emoji.id:
            name = emoji.name or "emoji"
            return quote(f"{name}:{emoji.id}", safe="")
        return quote(emoji.name or "", safe="")
    if hasattr(emoji, "id") and hasattr(emoji, "name"):
        name = getattr(emoji, "name") or "emoji"
        emoji_id = getattr(emoji, "id")
        if emoji_id:
            return quote(f"{name}:{emoji_id}", safe="")
    return quote(str(emoji), safe="")


def channel_from_data(client: Any, data: Dict[str, Any]) -> TextChannel:
    channel_type = data.get("type")
    if channel_type in (ChannelType.dm, ChannelType.group_dm, 1, 3):
        return DMChannel(client, data)
    if channel_type in (ChannelType.voice, 2):
        return VoiceChannel(client, data)
    return TextChannel(client, data)
