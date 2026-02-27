import asyncio
from typing import Any, Dict, Optional

import json as _json

import aiohttp
from aiohttp import FormData

from .errors import Forbidden, HTTPError, HTTPException, NotFound


class RESTClient:
    def __init__(
        self,
        token: Optional[str],
        base_url: str = "https://api.fluxer.app",
        api_version: str = "1",
        token_prefix: str = "Bot ",
        user_agent: str = "fluxer.py (compat layer)"
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._api_version = str(api_version).lstrip("v")
        self._token_prefix = token_prefix
        self._user_agent = user_agent
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def set_token(self, token: str) -> None:
        self._token = token

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("RESTClient has not been started")
        return self._session

    def _headers(
        self,
        *,
        content_type: Optional[str] = "application/json",
        headers: Optional[Dict[str, str]] = None,
        auth: bool = True,
    ) -> Dict[str, str]:
        base = {
            "User-Agent": self._user_agent,
        }
        if content_type:
            base["Content-Type"] = content_type
        if auth and self._token:
            base["Authorization"] = f"{self._token_prefix}{self._token}"
        if headers:
            base.update(headers)
        return base

    def _url(self, path: str, base_url_override: Optional[str] = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        path = path if path.startswith("/") else f"/{path}"
        base = (base_url_override or self._base_url).rstrip("/")
        if path.startswith("/v") and len(path) > 2 and path[2].isdigit():
            return f"{base}{path}"
        return f"{base}/v{self._api_version}{path}"

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        files: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: bool = True,
        base_url_override: Optional[str] = None,
    ) -> Any:
        url = self._url(path, base_url_override=base_url_override)
        content_type = "application/json" if json is not None else None
        payload = data
        json_param = json

        if data is not None and json is not None:
            raise ValueError("Use json or data, not both")

        if files is not None:
            form = FormData()
            if json is not None:
                form.add_field("payload_json", _json.dumps(json))
            if isinstance(files, (list, tuple)):
                for idx, file in enumerate(files):
                    if hasattr(file, "to_form"):
                        file.to_form(form, idx)
                    else:
                        # Expect tuple: (name, fp, filename, content_type)
                        name, fp, filename, ctype = file
                        form.add_field(name, fp, filename=filename, content_type=ctype)
            else:
                raise ValueError("files must be a list/tuple of file entries")
            payload = form
            content_type = None
            json_param = None

        async with self.session.request(
            method=method,
            url=url,
            headers=self._headers(content_type=content_type, headers=headers, auth=auth),
            params=params,
            json=json_param,
            data=payload,
        ) as resp:
            if resp.status == 204:
                return None
            try:
                data = await resp.json(content_type=None)
            except aiohttp.ContentTypeError:
                data = await resp.text()

            if resp.status >= 400:
                if resp.status == 403:
                    raise Forbidden(resp.status, resp.reason, data)
                if resp.status == 404:
                    raise NotFound(resp.status, resp.reason, data)
                raise HTTPException(resp.status, resp.reason, data)
            return data

    async def get_gateway_bot(self) -> Dict[str, Any]:
        return await self.request("GET", "/gateway/bot")

    async def get_channel(self, channel_id: str) -> Dict[str, Any]:
        return await self.request("GET", f"/channels/{channel_id}")

    async def list_channel_messages(
        self,
        channel_id: str,
        limit: Optional[int] = None,
        before: Optional[str] = None,
        after: Optional[str] = None,
        around: Optional[str] = None,
    ) -> Any:
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        if around is not None:
            params["around"] = around
        return await self.request("GET", f"/channels/{channel_id}/messages", params=params)

    async def create_message(self, channel_id: str, payload: Dict[str, Any]) -> Any:
        return await self.request("POST", f"/channels/{channel_id}/messages", json=payload)

    async def delete_message(self, channel_id: str, message_id: str) -> Any:
        return await self.request("DELETE", f"/channels/{channel_id}/messages/{message_id}")

    async def trigger_typing(self, channel_id: str) -> Any:
        return await self.request("POST", f"/channels/{channel_id}/typing")
