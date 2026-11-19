"""Oracle for the division-by-zero sample."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(project_dir: Path):
    spec = importlib.util.spec_from_file_location("stats_oracle", project_dir / "stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(project_dir: Path) -> list[str]:
    stats = _load(Path(project_dir))
    failures = []
    try:
        stats.mean([])
        failures.append("mean of an empty list did not fail")
    except ValueError:
        pass
    except ZeroDivisionError:
        failures.append("mean still divides by zero")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"mean raised {type(exc).__name__}")

    try:
        stats.ratio(1, 0)
        failures.append("ratio accepted zero")
    except ValueError:
        pass
    except ZeroDivisionError:
        failures.append("ratio still divides by zero")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"ratio raised {type(exc).__name__}")

    try:
        assert stats.mean([2, 4]) == 3
        assert stats.ratio(10, 2) == 5
    except Exception as exc:  # noqa: BLE001
        failures.append(f"normal maths failed: {exc}")
    return failures
