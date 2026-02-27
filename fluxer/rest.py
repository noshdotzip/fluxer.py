from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from .api import API
from .domain_models import (
    AdminApiKey,
    AdminArchive,
    AdminAuditLog,
    AdminResource,
    AdminVoiceRegion,
    AdminVoiceServer,
    AuthSession,
    BillingSession,
    Connection,
    DiscoveryResource,
    DonationSession,
    GiftCode,
    GatewayInfo,
    HealthStatus,
    InstanceDiscovery,
    KlipyGif,
    OAuth2Application,
    OAuth2Authorization,
    OAuth2Token,
    OAuth2User,
    PackResource,
    PremiumSubscription,
    ReportResource,
    SavedMediaItem,
    SearchResult,
    TenorGif,
    ThemeResource,
)
from .models import (
    Emoji,
    Guild,
    Invite,
    Member,
    Message,
    ReadState,
    Role,
    Sticker,
    TextChannel,
    User,
    Webhook,
    channel_from_data,
)


@dataclass
class Resource:
    raw: Dict[str, Any]

    def __getattr__(self, item: str) -> Any:
        if item in self.raw:
            return self.raw[item]
        raise AttributeError(item)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.raw)


def _wrap_resource(data: Any) -> Any:
    if isinstance(data, dict):
        return Resource(data)
    if isinstance(data, list):
        return [_wrap_resource(item) for item in data]
    return data


Converter = Callable[[Any, Dict[str, Any]], Any]
DEFAULT_CONVERTER_KEY = "__default__"


class RESTCall:
    def __init__(
        self,
        client,
        endpoint,
        *,
        converter: Optional[Converter] = None,
        wrap: bool = False,
    ) -> None:
        self._client = client
        self._endpoint = endpoint
        self._converter = converter
        self._wrap = wrap
        self.__name__ = getattr(endpoint, "__name__", endpoint.name)
        self.__doc__ = getattr(endpoint, "__doc__", "")

    async def __call__(self, *, raw: bool = False, **kwargs: Any) -> Any:
        data = await self._endpoint(**kwargs)
        if raw:
            return data
        if self._converter is not None:
            return self._converter(data, kwargs)
        if self._wrap:
            return _wrap_resource(data)
        return data


class RESTGroup:
    def __init__(self, client, api_group, converters: Dict[str, Converter], wrap: bool) -> None:
        self._client = client
        self._api_group = api_group
        self._converters = dict(converters or {})
        self._default_converter = self._converters.pop(DEFAULT_CONVERTER_KEY, None)
        self._wrap = wrap
        self._cache: Dict[str, RESTCall] = {}

    def __getattr__(self, item: str) -> RESTCall:
        if item in self._cache:
            return self._cache[item]
        endpoint = getattr(self._api_group, item)
        converter = self._converters.get(item, self._default_converter)
        call = RESTCall(self._client, endpoint, converter=converter, wrap=self._wrap)
        self._cache[item] = call
        return call


class REST:
    def __init__(self, client) -> None:
        self._client = client
        self._api = API(client)
        self._groups: Dict[str, RESTGroup] = {}
        self._build_groups()

    def _build_groups(self) -> None:
        converters = _default_converters(self._client)
        wrap_groups = _wrap_groups()
        created: Dict[int, RESTGroup] = {}
        for name, group in self._api.list_groups(include_aliases=True).items():
            group_name = getattr(group, "_name", name)
            group_id = id(group)
            rest_group = created.get(group_id)
            if rest_group is None:
                rest_group = RESTGroup(
                    self._client,
                    group,
                    converters.get(group_name, {}),
                    wrap=group_name in wrap_groups,
                )
                created[group_id] = rest_group
            self._groups[name] = rest_group

    def __getattr__(self, item: str) -> RESTGroup:
        group = self._groups.get(item)
        if not group:
            raise AttributeError(item)
        return group


def _default_converters(client) -> Dict[str, Dict[str, Converter]]:
    def model_from(model_cls):
        def _convert(data: Any, _: Dict[str, Any]) -> Any:
            if isinstance(data, list):
                if data and isinstance(data[0], dict):
                    return [model_cls.from_dict(item) for item in data]
                return data
            if isinstance(data, dict):
                return model_cls.from_dict(data)
            return data

        return _convert

    def channel_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, list):
            return [channel_from_data(client, item) for item in data]
        if isinstance(data, dict):
            return channel_from_data(client, data)
        return data

    def message_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, list):
            return [Message(client, item) for item in data]
        if isinstance(data, dict):
            return Message(client, data)
        return data

    def guild_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, dict):
            return Guild.from_dict(data, client=client)
        return data

    def member_from(data: Any, kwargs: Dict[str, Any]) -> Any:
        if isinstance(data, dict):
            guild_id = kwargs.get("guild_id") or data.get("guild_id") or ""
            return Member.from_dict(data, guild_id, client=client)
        return data

    def user_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, dict):
            return User.from_dict(data, client=client)
        return data

    def role_from(data: Any, kwargs: Dict[str, Any]) -> Any:
        guild_id = kwargs.get("guild_id")
        if isinstance(data, list):
            return [Role.from_dict(item, guild_id=guild_id, client=client) for item in data]
        if isinstance(data, dict):
            return Role.from_dict(data, guild_id=guild_id, client=client)
        return data

    def invite_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, list):
            return [Invite.from_dict(item, client=client) for item in data]
        if isinstance(data, dict):
            return Invite.from_dict(data, client=client)
        return data

    def webhook_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, list):
            return [Webhook.from_dict(item, client=client) for item in data]
        if isinstance(data, dict):
            return Webhook.from_dict(data, client=client)
        return data

    def emoji_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, list):
            return [Emoji.from_dict(item) for item in data]
        if isinstance(data, dict):
            return Emoji.from_dict(data)
        return data

    def sticker_from(data: Any, _: Dict[str, Any]) -> Any:
        if isinstance(data, list):
            return [Sticker.from_dict(item) for item in data]
        if isinstance(data, dict):
            return Sticker.from_dict(data)
        return data

    return {
        "admin": {
            DEFAULT_CONVERTER_KEY: model_from(AdminResource),
            "create_admin_api_key": model_from(AdminApiKey),
            "list_admin_api_keys": model_from(AdminApiKey),
            "list_audit_logs": model_from(AdminAuditLog),
            "search_audit_logs": model_from(AdminAuditLog),
            "get_archive_details": model_from(AdminArchive),
            "list_archives": model_from(AdminArchive),
            "get_voice_region": model_from(AdminVoiceRegion),
            "list_voice_regions": model_from(AdminVoiceRegion),
            "get_voice_server": model_from(AdminVoiceServer),
            "list_voice_servers": model_from(AdminVoiceServer),
            "list_guild_emojis": emoji_from,
            "list_guild_stickers": sticker_from,
            "list_guild_members": member_from,
            "list_user_guilds": guild_from,
            "list_user_dm_channels": channel_from,
            "lookup_user": user_from,
            "look_up_guild": guild_from,
            "list_reports": model_from(ReportResource),
            "get_report_details": model_from(ReportResource),
            "resolve_report": model_from(ReportResource),
            "search_reports": model_from(ReportResource),
            "list_user_sessions": model_from(AuthSession),
        },
        "auth": {
            DEFAULT_CONVERTER_KEY: model_from(AuthSession),
            "list_auth_sessions": model_from(AuthSession),
        },
        "billing": {
            DEFAULT_CONVERTER_KEY: model_from(BillingSession),
        },
        "connections": {
            DEFAULT_CONVERTER_KEY: model_from(Connection),
        },
        "discovery": {
            DEFAULT_CONVERTER_KEY: model_from(DiscoveryResource),
        },
        "donations": {
            DEFAULT_CONVERTER_KEY: model_from(DonationSession),
        },
        "gifts": {
            DEFAULT_CONVERTER_KEY: model_from(GiftCode),
        },
        "gateway": {
            DEFAULT_CONVERTER_KEY: model_from(GatewayInfo),
        },
        "health": {
            DEFAULT_CONVERTER_KEY: model_from(HealthStatus),
        },
        "instance": {
            DEFAULT_CONVERTER_KEY: model_from(InstanceDiscovery),
        },
        "klipy": {
            DEFAULT_CONVERTER_KEY: model_from(KlipyGif),
        },
        "oauth2": {
            DEFAULT_CONVERTER_KEY: model_from(OAuth2Application),
            "exchange_oauth2_token": model_from(OAuth2Token),
            "introspect_oauth2_token": model_from(OAuth2Token),
            "revoke_oauth2_token": model_from(OAuth2Token),
            "grant_oauth2_consent": model_from(OAuth2Authorization),
            "list_user_oauth2_authorizations": model_from(OAuth2Authorization),
            "get_current_oauth2_user": model_from(OAuth2User),
            "get_oauth2_user_information": model_from(OAuth2User),
            "get_application": model_from(OAuth2Application),
            "get_public_application": model_from(OAuth2Application),
            "list_current_user_applications": model_from(OAuth2Application),
            "list_user_applications": model_from(OAuth2Application),
            "list_user_applications_1": model_from(OAuth2Application),
            "create_oauth2_application": model_from(OAuth2Application),
            "update_application": model_from(OAuth2Application),
            "update_bot_profile": model_from(OAuth2Application),
            "reset_client_secret": model_from(OAuth2Application),
            "reset_bot_token": model_from(OAuth2Application),
        },
        "packs": {
            DEFAULT_CONVERTER_KEY: model_from(PackResource),
            "list_pack_emojis": emoji_from,
            "list_pack_stickers": sticker_from,
            "create_pack_emoji": emoji_from,
            "create_pack_sticker": sticker_from,
            "update_pack_emoji": emoji_from,
            "update_pack_sticker": sticker_from,
            "bulk_create_pack_emojis": emoji_from,
            "bulk_create_pack_stickers": sticker_from,
        },
        "premium": {
            DEFAULT_CONVERTER_KEY: model_from(PremiumSubscription),
        },
        "read-states": {
            DEFAULT_CONVERTER_KEY: model_from(ReadState),
        },
        "reports": {
            DEFAULT_CONVERTER_KEY: model_from(ReportResource),
        },
        "saved-media": {
            DEFAULT_CONVERTER_KEY: model_from(SavedMediaItem),
        },
        "search": {
            DEFAULT_CONVERTER_KEY: model_from(SearchResult),
        },
        "tenor": {
            DEFAULT_CONVERTER_KEY: model_from(TenorGif),
        },
        "themes": {
            DEFAULT_CONVERTER_KEY: model_from(ThemeResource),
        },
        "channels": {
            "fetch_a_channel": channel_from,
            "send_a_message": message_from,
            "edit_a_message": message_from,
            "fetch_a_message": message_from,
            "list_messages_in_a_channel": message_from,
            "list_pinned_messages": message_from,
        },
        "guilds": {
            "get_guild_information": guild_from,
            "get_guild_member_by_user_id": member_from,
            "list_guild_channels": channel_from,
            "create_guild_channel": channel_from,
            "list_guild_roles": role_from,
            "list_guild_emojis": emoji_from,
            "list_guild_stickers": sticker_from,
            "create_guild_emoji": emoji_from,
            "create_guild_sticker": sticker_from,
            "update_guild_emoji": emoji_from,
            "update_guild_sticker": sticker_from,
        },
        "users": {
            "get_user_by_id": user_from,
            "create_private_channel": channel_from,
            "list_private_channels": channel_from,
        },
        "invites": {
            "get_invite_information": invite_from,
            "create_channel_invite": invite_from,
            "delete_invite": invite_from,
            "list_channel_invites": invite_from,
            "list_guild_invites": invite_from,
        },
        "webhooks": {
            "get_webhook": webhook_from,
            "get_webhook_with_token": webhook_from,
            "list_channel_webhooks": webhook_from,
            "list_guild_webhooks": webhook_from,
            "create_webhook": webhook_from,
            "update_webhook": webhook_from,
            "update_webhook_with_token": webhook_from,
            "execute_webhook": message_from,
            "execute_slack_webhook": message_from,
            "execute_sentry_webhook": message_from,
            "execute_github_webhook": message_from,
        },
    }


def _wrap_groups() -> Iterable[str]:
    # Keep generic wrapping for image endpoints where responses are not JSON objects.
    return {
        "images",
    }
