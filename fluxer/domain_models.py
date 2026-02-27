from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class DomainModel:
    raw: Dict[str, Any]

    def __getattr__(self, item: str) -> Any:
        if item in self.raw:
            return self.raw[item]
        raise AttributeError(item)

    def __getitem__(self, item: str) -> Any:
        return self.raw[item]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.raw)

    @property
    def id(self) -> Optional[str]:
        for key in ("id", "code", "key", "token", "session_id"):
            value = self.raw.get(key)
            if value is not None:
                return str(value)
        return None

    @property
    def name(self) -> Optional[str]:
        for key in ("name", "username", "display_name", "title", "slug"):
            value = self.raw.get(key)
            if value is not None:
                return str(value)
        return None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainModel":
        return cls(raw=data or {})


class AdminResource(DomainModel):
    pass


class AdminApiKey(DomainModel):
    pass


class AdminAuditLog(DomainModel):
    pass


class AdminArchive(DomainModel):
    pass


class AdminVoiceRegion(DomainModel):
    pass


class AdminVoiceServer(DomainModel):
    pass


class AuthSession(DomainModel):
    pass


class BillingSession(DomainModel):
    pass


class Connection(DomainModel):
    pass


class DiscoveryResource(DomainModel):
    pass


class DonationSession(DomainModel):
    pass


class GiftCode(DomainModel):
    pass


class GatewayInfo(DomainModel):
    pass


class HealthStatus(DomainModel):
    pass


class InstanceDiscovery(DomainModel):
    pass


class KlipyGif(DomainModel):
    pass


class OAuth2Application(DomainModel):
    pass


class OAuth2Authorization(DomainModel):
    pass


class OAuth2Token(DomainModel):
    pass


class OAuth2User(DomainModel):
    pass


class PackResource(DomainModel):
    pass


class PremiumSubscription(DomainModel):
    pass


class ReportResource(DomainModel):
    pass


class SavedMediaItem(DomainModel):
    pass


class SearchResult(DomainModel):
    pass


class TenorGif(DomainModel):
    pass


class ThemeResource(DomainModel):
    pass
