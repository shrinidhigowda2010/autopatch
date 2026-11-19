"""File tree, languages, dependencies, important files and the import graph."""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

from app.ingest.languages import LANGUAGES

_LANG = LANGUAGES


def describe_project(root: Path) -> dict:
    files = [path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    languages = Counter()
    for path in files:
        languages[_LANG.get(path.suffix.lower(), "Other")] += 1
    return {
        "file_count": len(files),
        "languages": [{"name": name, "files": count} for name, count in languages.most_common()],
        "dependencies": _dependencies(root),
        "important": _important(root, files),
        "tree": _tree(root, root),
        "graph": _graph(root),
    }


def _tree(root: Path, directory: Path) -> list[dict]:
    nodes = []
    for path in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        if path.name in {"__pycache__", ".git", "node_modules", ".venv"}:
            continue
        if path.is_dir():
            nodes.append({"name": path.name, "type": "dir", "children": _tree(root, path)})
        else:
            nodes.append(
                {
                    "name": path.name,
                    "type": "file",
                    "path": path.relative_to(root).as_posix(),
                    "language": _LANG.get(path.suffix.lower(), "Other"),
                    "bytes": path.stat().st_size,
                }
            )
    return nodes


def _dependencies(root: Path) -> list[dict]:
    found: list[dict] = []
    req = root / "requirements.txt"
    if req.is_file():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            found.append({"name": line, "source": "requirements.txt"})
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip().strip(",").strip('"').strip("'")
            if stripped and not stripped.startswith("[") and not stripped.startswith("#"):
                if any(op in stripped for op in ("==", ">=", "~=")):
                    found.append({"name": stripped, "source": "pyproject.toml"})
    return found


def _important(root: Path, files: list[Path]) -> list[dict]:
    notes = []
    names = {
        "readme.md": "Project readme",
        "requirements.txt": "Python dependencies",
        "pyproject.toml": "Project metadata",
        "package.json": "JavaScript dependencies",
    }
    for path in files:
        rel = path.relative_to(root).as_posix()
        key = path.name.lower()
        if key in names:
            notes.append({"path": rel, "reason": names[key]})
        elif path.suffix == ".py" and path.name in {"main.py", "app.py", "cli.py"}:
            notes.append({"path": rel, "reason": "Likely entry point"})
        elif path.suffix == ".py":
            text = path.read_text(encoding="utf-8", errors="replace")
            if "__name__" in text and "__main__" in text:
                notes.append({"path": rel, "reason": "Runs as a script"})
    if not notes and files:
        first = files[0].relative_to(root).as_posix()
        notes.append({"path": first, "reason": "Only source file"})
    return notes[:12]


def _graph(root: Path) -> dict:
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    py_files = [path for path in root.rglob("*.py") if "__pycache__" not in path.parts and "tests" not in path.parts]
    modules = {}
    for path in py_files:
        rel = path.relative_to(root).as_posix()
        modules[rel.removesuffix(".py").replace("/", ".")] = rel
        if path.name == "__init__.py":
            modules[str(path.parent.relative_to(root)).replace("/", ".")] = rel
    nodes = [{"id": path.relative_to(root).as_posix(), "kind": "internal"} for path in py_files]
    edges = []
    external = set()
    for path in py_files:
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Import):
                target = node.names[0].name if node.names else None
            elif isinstance(node, ast.ImportFrom) and node.module:
                target = node.module
            if not target:
                continue
            root_name = target.split(".")[0]
            internal = modules.get(target) or modules.get(root_name)
            if internal:
                edges.append({"from": rel, "to": internal, "kind": "internal"})
            else:
                kind = "stdlib" if root_name in stdlib else "third_party"
                external.add((root_name, kind))
                edges.append({"from": rel, "to": root_name, "kind": kind})
    for name, kind in sorted(external):
        nodes.append({"id": name, "kind": kind})
    # Drop duplicate edges.
    unique = []
    seen = set()
    for edge in edges:
        key = (edge["from"], edge["to"], edge["kind"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    return {"nodes": nodes, "edges": unique}
