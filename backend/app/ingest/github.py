"""Download a public GitHub repository as a zip. No credentials are sent."""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

import httpx

from app.ingest.files import IngestError, _flatten_single_root, _safe_extract

_REPO = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str]:
    match = _REPO.match(url.strip())
    if not match:
        raise IngestError("Use a public GitHub URL like https://github.com/owner/repo.")
    return match.group("owner"), match.group("repo")


def download_github(url: str) -> Path:
    owner, repo = parse_github_url(url)
    branch = _default_branch(owner, repo)
    payload = _download_zip(owner, repo, branch)
    dest = Path(tempfile.mkdtemp(prefix="fixpilot-gh-"))
    archive_path = dest / "repo.zip"
    archive_path.write_bytes(payload)
    with zipfile.ZipFile(archive_path) as archive:
        _safe_extract(archive, dest / "src")
    archive_path.unlink(missing_ok=True)
    _flatten_single_root(dest / "src")
    return dest / "src"


def _default_branch(owner: str, repo: str) -> str:
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "FixPilot"},
            )
        if response.status_code == 200:
            name = response.json().get("default_branch")
            if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._/-]+", name):
                return name
    except httpx.HTTPError:
        pass
    return "main"


def _download_zip(owner: str, repo: str, branch: str) -> bytes:
    candidates = [branch]
    for extra in ("main", "master"):
        if extra not in candidates:
            candidates.append(extra)
    last = "GitHub did not return the repository."
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for name in candidates:
            url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{name}"
            try:
                response = client.get(url, headers={"User-Agent": "FixPilot"})
            except httpx.HTTPError as exc:
                last = str(exc)
                continue
            if response.status_code != 200:
                last = f"GitHub returned {response.status_code} for branch {name}."
                continue
            data = response.content
            if len(data) > 8 * 1024 * 1024:
                raise IngestError("That repository is larger than 8 MB. Upload a zip of the files you care about.")
            return data
    raise IngestError(last)
