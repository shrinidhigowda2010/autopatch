"""Copy uploads and sample projects into the data directory."""

from __future__ import annotations

import io
import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from app.config import settings

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".idea", ".vscode"}


class IngestError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def project_paths(project_id: str) -> tuple[Path, Path]:
    base = settings.data_dir / "projects" / project_id
    source = base / "source"
    workspace = base / "workspace"
    source.mkdir(parents=True, exist_ok=True)
    return source, workspace


def _too_big(size: int) -> None:
    if size > settings.max_upload_mb * 1024 * 1024:
        raise IngestError(f"Upload is larger than {settings.max_upload_mb} MB.")


def copy_project(origin: Path, project_id: str) -> Path:
    source, workspace = project_paths(project_id)
    if source.exists():
        shutil.rmtree(source)
    shutil.copytree(origin, source, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(source, workspace)
    _guard_tree(workspace)
    return workspace


def extract_zip(project_id: str, data: bytes) -> Path:
    _too_big(len(data))
    source, workspace = project_paths(project_id)
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True, exist_ok=True)
    tmp = source.parent / "upload.zip"
    tmp.write_bytes(data)
    try:
        with zipfile.ZipFile(tmp) as archive:
            _safe_extract(archive, source)
    except zipfile.BadZipFile as exc:
        raise IngestError("That zip could not be read.") from exc
    finally:
        tmp.unlink(missing_ok=True)
    _flatten_single_root(source)
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(source, workspace)
    _guard_tree(workspace)
    return workspace


def extract_tar(project_id: str, data: bytes) -> Path:
    _too_big(len(data))
    source, workspace = project_paths(project_id)
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            _safe_extract_tar(archive, source)
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise IngestError("That archive could not be read.") from exc
    _flatten_single_root(source)
    return _refresh_workspace(source, workspace)


def _safe_extract_tar(archive: tarfile.TarFile, dest: Path) -> None:
    dest_resolved = dest.resolve()
    total = 0
    count = 0
    cap = settings.max_unzip_mb * 1024 * 1024
    for member in archive:
        # Links, devices and fifos are never written; only plain files.
        if not member.isfile():
            continue
        count += 1
        if count > settings.max_files:
            raise IngestError("The archive has too many files.")
        total += member.size
        if total > cap:
            raise IngestError("The archive expands to more than the allowed size.")
        target = (dest / member.name).resolve()
        if target == dest_resolved or dest_resolved not in target.parents:
            raise IngestError("The archive tried to write outside its folder.")
        handle = archive.extractfile(member)
        if handle is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with handle, target.open("wb") as out:
            shutil.copyfileobj(handle, out)


def safe_relative_path(raw: str) -> str:
    """Clean a user-supplied file path, refusing anything that escapes the project."""
    cleaned = (raw or "").strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    path = PurePosixPath(cleaned)
    if not cleaned or path.is_absolute() or ".." in path.parts or len(cleaned) > 200:
        raise IngestError(f"“{raw[:60]}” is not a valid file name.")
    if any(part in SKIP_DIRS for part in path.parts) or ":" in cleaned:
        raise IngestError(f"“{raw[:60]}” is not a valid file name.")
    return path.as_posix()


def write_files(project_id: str, files: list[tuple[str, str]]) -> Path:
    """Create a project from in-memory files (pasted code or a confirmed preview)."""
    if not files:
        raise IngestError("Add at least one file.")
    if len(files) > settings.max_files:
        raise IngestError("Too many files.")
    _too_big(sum(len(content.encode("utf-8")) for _path, content in files))
    source, workspace = project_paths(project_id)
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    for raw_path, content in files:
        rel = safe_relative_path(raw_path)
        if rel.lower() in seen:
            raise IngestError(f"Two files are named {rel}.")
        seen.add(rel.lower())
        target = source / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return _refresh_workspace(source, workspace)


def _refresh_workspace(source: Path, workspace: Path) -> Path:
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(source, workspace)
    _guard_tree(workspace)
    return workspace


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    dest_resolved = dest.resolve()
    total = 0
    count = 0
    cap = settings.max_unzip_mb * 1024 * 1024
    for info in archive.infolist():
        if info.is_dir():
            continue
        count += 1
        if count > settings.max_files:
            raise IngestError("The zip has too many files.")
        total += info.file_size
        if total > cap:
            raise IngestError("The zip expands to more than the allowed size.")
        target = (dest / info.filename).resolve()
        if target != dest_resolved and dest_resolved not in target.parents:
            raise IngestError("The zip tried to write outside its folder.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def _flatten_single_root(dest: Path) -> None:
    children = [path for path in dest.iterdir() if path.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        inner = children[0]
        for path in inner.iterdir():
            shutil.move(str(path), dest / path.name)
        inner.rmdir()


def _guard_tree(root: Path) -> None:
    count = 0
    for path in root.rglob("*"):
        if path.is_file():
            count += 1
            if count > settings.max_files:
                raise IngestError("The project has too many files.")
