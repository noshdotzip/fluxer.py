from __future__ import annotations

from typing import Any, Dict, List, Optional


class Embed:
    def __init__(
        self,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        url: Optional[str] = None,
        color: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        self.title = title
        self.description = description
        self.url = url
        if color is not None and hasattr(color, "value"):
            color = int(getattr(color, "value"))
        self.color = color
        self.timestamp = timestamp
        self._footer: Dict[str, Any] = {}
        self._image: Dict[str, Any] = {}
        self._thumbnail: Dict[str, Any] = {}
        self._author: Dict[str, Any] = {}
        self._fields: List[Dict[str, Any]] = []

    def set_footer(self, *, text: Optional[str] = None, icon_url: Optional[str] = None) -> "Embed":
        if text is not None:
            self._footer["text"] = text
        if icon_url is not None:
            self._footer["icon_url"] = icon_url
        return self

    def set_image(self, *, url: str) -> "Embed":
        self._image["url"] = url
        return self

    def set_thumbnail(self, *, url: str) -> "Embed":
        self._thumbnail["url"] = url
        return self

    def set_author(
        self,
        *,
        name: str,
        url: Optional[str] = None,
        icon_url: Optional[str] = None,
    ) -> "Embed":
        self._author["name"] = name
        if url is not None:
            self._author["url"] = url
        if icon_url is not None:
            self._author["icon_url"] = icon_url
        return self

    def add_field(self, *, name: str, value: str, inline: bool = False) -> "Embed":
        self._fields.append({"name": name, "value": value, "inline": inline})
        return self

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.title is not None:
            payload["title"] = self.title
        if self.description is not None:
            payload["description"] = self.description
        if self.url is not None:
            payload["url"] = self.url
        if self.color is not None:
            payload["color"] = self.color
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        if self._footer:
            payload["footer"] = self._footer
        if self._image:
            payload["image"] = self._image
        if self._thumbnail:
            payload["thumbnail"] = self._thumbnail
        if self._author:
            payload["author"] = self._author
        if self._fields:
            payload["fields"] = list(self._fields)
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Embed":
        embed = cls(
            title=data.get("title"),
            description=data.get("description"),
            url=data.get("url"),
            color=data.get("color"),
            timestamp=data.get("timestamp"),
        )
        if "footer" in data:
            embed._footer = dict(data.get("footer") or {})
        if "image" in data:
            embed._image = dict(data.get("image") or {})
        if "thumbnail" in data:
            embed._thumbnail = dict(data.get("thumbnail") or {})
        if "author" in data:
            embed._author = dict(data.get("author") or {})
        if "fields" in data:
            embed._fields = list(data.get("fields") or [])
        return embed
