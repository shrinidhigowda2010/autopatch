"""Checks that define 'fixed' for the marks calculator. Not part of the scanned project."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(project_dir: Path):
    path = project_dir / "marks.py"
    spec = importlib.util.spec_from_file_location("marks_oracle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(project_dir: Path) -> list[str]:
    marks = _load(Path(project_dir))
    failures = []
    try:
        marks.calculate([-5, 80])
        failures.append("negative mark was accepted")
    except ValueError:
        pass
    except Exception as exc:  # noqa: BLE001
        failures.append(f"negative mark raised {type(exc).__name__}")

    try:
        marks.calculate([150])
        failures.append("mark over 100 was accepted")
    except ValueError:
        pass
    except Exception as exc:  # noqa: BLE001
        failures.append(f"mark over 100 raised {type(exc).__name__}")

    try:
        marks.calculate([])
        failures.append("empty list did not fail")
    except ValueError:
        pass
    except ZeroDivisionError:
        failures.append("empty list still divides by zero")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"empty list raised {type(exc).__name__}")

    try:
        result = marks.calculate([0, 100])
    except Exception as exc:  # noqa: BLE001
        failures.append(f"boundary marks crashed: {exc}")
    else:
        if result["percentage"] != 50:
            failures.append(f"boundary percentage was {result['percentage']}")
        if result["grade"] != "C":
            failures.append(f"boundary grade was {result['grade']}")
    return failures
