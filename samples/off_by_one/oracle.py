"""Oracle for the off-by-one sample."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(project_dir: Path):
    spec = importlib.util.spec_from_file_location("window_oracle", project_dir / "window.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(project_dir: Path) -> list[str]:
    window = _load(Path(project_dir))
    failures = []
    try:
        pairs = window.average_pairs([1, 3, 5])
    except Exception as exc:  # noqa: BLE001
        failures.append(f"average_pairs crashed: {type(exc).__name__}")
        return failures
    if pairs != [2, 4]:
        failures.append(f"pairs were {pairs}")
    try:
        assert window.reading_count([1]) == 1
    except Exception as exc:  # noqa: BLE001
        failures.append(f"reading_count failed: {exc}")
    return failures
