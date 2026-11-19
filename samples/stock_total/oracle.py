"""Oracle for the skipped-first-row sample."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(project_dir: Path):
    spec = importlib.util.spec_from_file_location("stock_oracle", project_dir / "stock.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(project_dir: Path) -> list[str]:
    stock = _load(Path(project_dir))
    failures = []
    try:
        total = stock.total_stock([{"qty": 2}, {"qty": 3}])
        single = stock.total_stock([{"qty": 4}])
    except Exception as exc:  # noqa: BLE001
        return [f"total_stock crashed: {exc}"]
    if total != 5:
        failures.append(f"two rows totalled {total}")
    if single != 4:
        failures.append(f"one row totalled {single}")
    return failures
