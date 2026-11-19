"""Copy uploads and sample projects into the data directory."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from app.config import settings

ALLOWED_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".txt", ".md",
    ".toml", ".yml", ".yaml", ".cfg", ".ini", ".css", ".html",
}
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


def save_single_file(project_id: str, filename: str, data: bytes) -> Path:
    _too_big(len(data))
    name = Path(filename).name
    if not name or name.startswith("."):
        raise IngestError("Pick a source file.")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise IngestError(f"{suffix or 'that file type'} is not allowed.")
    source, workspace = project_paths(project_id)
    (source / name).write_bytes(data)
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(source, workspace)
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
