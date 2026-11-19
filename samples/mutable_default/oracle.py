"""Oracle for the mutable default argument."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(project_dir: Path):
    spec = importlib.util.spec_from_file_location("cart_oracle", project_dir / "cart.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(project_dir: Path) -> list[str]:
    cart = _load(Path(project_dir))
    failures = []
    try:
        first = cart.add_item("apple")
        second = cart.add_item("pear")
    except Exception as exc:  # noqa: BLE001
        return [f"add_item crashed: {exc}"]
    if second != ["pear"]:
        failures.append(f"second call reused the default and returned {second}")
    if first is second:
        failures.append("both calls returned the same list")
    try:
        assert cart.add_item("pen", []) == ["pen"]
    except Exception as exc:  # noqa: BLE001
        failures.append(f"explicit cart failed: {exc}")
    return failures
