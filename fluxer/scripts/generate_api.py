"""Generate Fluxer API endpoint map from docs.fluxer.app.

This script fetches the API reference index and each endpoint page,
extracts the HTTP method and request URL from the curl example, and
writes a JSON map consumed by fluxer/api.py.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html import unescape
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests

DOCS_BASE = "https://docs.fluxer.app"
INDEX_URL = f"{DOCS_BASE}/api-reference"
USER_AGENT = "fluxer.py api generator"


@dataclass
class Endpoint:
    group: str
    name: str
    method: str
    path: str
    base_url: str
    docs_url: str


def _fetch(session: requests.Session, url: str) -> str:
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def _extract_links(html: str) -> List[str]:
    # Capture /api-reference/... links
    links = set(re.findall(r'href="(/api-reference/[^"#]+)"', html))
    # Include any non-api-reference docs pages that expose endpoints
    extra = set(re.findall(r'href="(/(media-proxy-api|relay-directory-api)/[^"#]+)"', html))
    for _, link in extra:
        links.add(link)
    return sorted(links)


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", "_")


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return unescape(text)


def _parse_endpoint(html: str, docs_url: str) -> Optional[Endpoint]:
    # Find curl --request METHOD --url URL in the rendered text
    text = _strip_html(html)
    match = re.search(
        r"curl\s+--request\s+(\w+)\s+\\?\s*--url\s+"
        r"(https?://\S+?)(?=(?:\d{3})|Copy|\s|$)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    method = match.group(1).upper()
    full_url = match.group(2)
    parsed = urlparse(full_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path

    # Strip version prefix if present
    if path.startswith("/v1/"):
        path = path[len("/v1"):]

    # Determine group and name from docs_url path
    docs_path = urlparse(docs_url).path.strip("/")
    parts = docs_path.split("/")
    group = parts[1] if len(parts) > 1 else "misc"
    name = parts[2] if len(parts) > 2 else parts[-1]
    return Endpoint(
        group=group,
        name=_slug_to_name(name),
        method=method,
        path=path,
        base_url=base_url,
        docs_url=docs_url,
    )


def _fetch_endpoint(args: Tuple[str, str]) -> Optional[Endpoint]:
    docs_url, user_agent = args
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    try:
        page = _fetch(session, docs_url)
    except Exception as exc:
        print(f"Failed to fetch {docs_url}: {exc}", file=sys.stderr)
        return None
    return _parse_endpoint(page, docs_url)


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    html = _fetch(session, INDEX_URL)
    links = _extract_links(html)

    endpoints: List[Endpoint] = []
    seen: Set[str] = set()

    urls = [urljoin(DOCS_BASE, link) for link in links]
    max_workers = 12
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_fetch_endpoint, (url, USER_AGENT)) for url in urls]
        for future in as_completed(futures):
            endpoint = future.result()
            if not endpoint:
                continue

            key = f"{endpoint.group}.{endpoint.name}.{endpoint.method}.{endpoint.path}"
            if key in seen:
                continue
            seen.add(key)
            endpoints.append(endpoint)

    data: Dict[str, Dict[str, Dict[str, str]]] = {"groups": {}}
    for ep in endpoints:
        group = data["groups"].setdefault(ep.group, {})
        name = ep.name
        # Ensure unique names if collisions occur
        if name in group:
            suffix = 2
            while f"{name}_{suffix}" in group:
                suffix += 1
            name = f"{name}_{suffix}"
        group[name] = {
            "method": ep.method,
            "path": ep.path,
            "base_url": ep.base_url,
            "docs_url": ep.docs_url,
        }

    out_path = "fluxer/api_endpoints.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    print(f"Wrote {out_path} with {len(endpoints)} endpoints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
