from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Endpoint:
    group: str
    name: str
    method: str
    path: str
    base_url: str
    docs_url: str

    @property
    def path_params(self) -> tuple[str, ...]:
        return tuple(re.findall(r"{(\w+)}", self.path))


class EndpointCall:
    def __init__(self, client, endpoint: Endpoint) -> None:
        self._client = client
        self._endpoint = endpoint
        self.__name__ = endpoint.name
        self.__doc__ = f"{endpoint.method} {endpoint.path}\nDocs: {endpoint.docs_url}"

    async def __call__(
        self,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        files: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: bool = True,
        reason: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        endpoint = self._endpoint
        path_params = {}
        for name in endpoint.path_params:
            if name in kwargs:
                path_params[name] = kwargs.pop(name)

        if len(path_params) != len(endpoint.path_params):
            missing = [n for n in endpoint.path_params if n not in path_params]
            if missing:
                raise ValueError(f"Missing path params: {', '.join(missing)}")

        path = endpoint.path.format(**path_params)

        if params is None and json is None and data is None and files is None and kwargs:
            if endpoint.method in ("GET", "DELETE"):
                params = kwargs
            else:
                json = kwargs
        elif kwargs:
            raise ValueError("Unexpected keyword arguments: use params or json")

        if reason:
            headers = dict(headers or {})
            headers["X-Audit-Log-Reason"] = reason

        return await self._client.http.request(
            endpoint.method,
            path,
            params=params,
            json=json,
            data=data,
            files=files,
            headers=headers,
            auth=auth,
            base_url_override=base_url or endpoint.base_url,
        )


class APIGroup:
    def __init__(self, client, name: str, endpoints: Dict[str, Endpoint]) -> None:
        self._client = client
        self._name = name
        self._endpoints = endpoints
        self._cache: Dict[str, EndpointCall] = {}

    def __getattr__(self, item: str) -> EndpointCall:
        if item in self._cache:
            return self._cache[item]
        endpoint = self._endpoints.get(item)
        if not endpoint:
            raise AttributeError(item)
        call = EndpointCall(self._client, endpoint)
        self._cache[item] = call
        return call

    def list_endpoints(self) -> Dict[str, Endpoint]:
        return dict(self._endpoints)


class API:
    def __init__(self, client) -> None:
        self._client = client
        self._groups: Dict[str, APIGroup] = {}
        self._aliases: Dict[str, str] = {}
        self._load_endpoints()

    def _load_endpoints(self) -> None:
        path = Path(__file__).with_name("api_endpoints.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        groups = data.get("groups", {})
        for group_name, group_data in groups.items():
            endpoints: Dict[str, Endpoint] = {}
            for name, raw in group_data.items():
                endpoints[name] = Endpoint(
                    group=group_name,
                    name=name,
                    method=raw["method"],
                    path=raw["path"],
                    base_url=raw.get("base_url") or self._client.http._base_url,
                    docs_url=raw.get("docs_url", ""),
                )
            self._groups[group_name] = APIGroup(self._client, group_name, endpoints)
            if "-" in group_name:
                alias = group_name.replace("-", "_")
                if alias not in self._groups:
                    self._aliases[alias] = group_name

    def __getattr__(self, item: str) -> APIGroup:
        group = self._groups.get(item)
        if not group:
            target = self._aliases.get(item)
            if target:
                return self._groups[target]
            raise AttributeError(item)
        return group

    def list_groups(self, *, include_aliases: bool = False) -> Dict[str, APIGroup]:
        if not include_aliases:
            return dict(self._groups)
        groups = dict(self._groups)
        for alias, name in self._aliases.items():
            groups[alias] = self._groups[name]
        return groups
