"""Fetch code from a pasted link without letting the link reach private networks.

Supported: GitHub repos (zip download), GitHub file pages (turned into raw
links), Gists, Pastebin pages, and any public http(s) file URL.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

import httpx

from app.config import settings
from app.ingest.files import IngestError

MAX_REDIRECTS = 4
_TIMEOUT = httpx.Timeout(15.0, connect=6.0)

_GITHUB_REPO = re.compile(r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$")
_GITHUB_TREE = re.compile(r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/tree/.+$")
_GITHUB_BLOB = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?:blob|raw)/(?P<rest>[^?#]+)"
)
_GIST = re.compile(r"^https?://gist\.github\.com/(?:[\w-]+/)?(?P<id>[0-9a-fA-F]{6,})/?(?:[?#].*)?$")
_PASTEBIN = re.compile(r"^https?://(?:www\.)?pastebin\.com/(?:raw/)?(?P<id>\w{4,})/?$")


@dataclass
class Link:
    kind: str  # repo | gist | file
    url: str
    filename: str = ""


def resolve_link(raw: str) -> Link:
    url = raw.strip()
    scheme = urlsplit(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise IngestError("Only http and https links are allowed.")
    if match := _GITHUB_REPO.match(url):
        return Link("repo", f"https://github.com/{match['owner']}/{match['repo']}")
    if match := _GITHUB_TREE.match(url):
        return Link("repo", f"https://github.com/{match['owner']}/{match['repo']}")
    if match := _GITHUB_BLOB.match(url):
        raw_url = f"https://raw.githubusercontent.com/{match['owner']}/{match['repo']}/{match['rest']}"
        return Link("file", raw_url, _filename(raw_url))
    if match := _GIST.match(url):
        return Link("gist", f"https://api.github.com/gists/{match['id']}")
    if match := _PASTEBIN.match(url):
        return Link("file", f"https://pastebin.com/raw/{match['id']}", f"pastebin_{match['id']}.txt")
    return Link("file", url, _filename(url))


def _filename(url: str) -> str:
    name = PurePosixPath(unquote(urlsplit(url).path)).name
    return name or "download.txt"


def check_public(url: str) -> None:
    """Refuse URLs whose host resolves to loopback, private, link-local or reserved space."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"}:
        raise IngestError("Only http and https links are allowed.")
    host = parts.hostname
    if not host:
        raise IngestError("That link has no host name.")
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, ValueError) as exc:
        raise IngestError("FixPilot couldn't find that website.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global or address.is_multicast or address.is_reserved:
            raise IngestError("That link points to a private or local address, so FixPilot won't fetch it.")


def safe_get(url: str, max_bytes: int | None = None, accept: str = "*/*") -> bytes:
    """GET a public URL with timeouts, a byte cap, and a host check on every redirect."""
    cap = max_bytes or settings.max_upload_mb * 1024 * 1024
    current = url
    headers = {"User-Agent": "FixPilot", "Accept": accept}
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=False, headers=headers) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            check_public(current)
            try:
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location", "")
                        current = str(response.url.join(location))
                        continue
                    if response.status_code != 200:
                        raise IngestError(f"The link returned HTTP {response.status_code}.")
                    declared = response.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > cap:
                        raise IngestError(f"That file is larger than {cap // (1024 * 1024)} MB.")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > cap:
                            raise IngestError(f"That file is larger than {cap // (1024 * 1024)} MB.")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.TimeoutException as exc:
                raise IngestError("The link took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise IngestError("FixPilot couldn't download that link.") from exc
    raise IngestError("The link redirected too many times.")


def fetch_gist(api_url: str) -> list[tuple[str, str]]:
    import json

    try:
        payload = json.loads(safe_get(api_url, accept="application/vnd.github+json"))
    except ValueError as exc:
        raise IngestError("GitHub returned something unexpected for that Gist.") from exc
    files = []
    for name, item in (payload.get("files") or {}).items():
        if not isinstance(item, dict):
            continue
        content = item.get("content") or ""
        if item.get("truncated") and item.get("raw_url"):
            content = safe_get(str(item["raw_url"])).decode("utf-8", errors="replace")
        files.append((PurePosixPath(str(name)).name or "gist.txt", content))
    if not files:
        raise IngestError("That Gist has no files.")
    return files
