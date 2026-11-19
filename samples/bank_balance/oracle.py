"""Oracle for the bank account sample."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(project_dir: Path):
    spec = importlib.util.spec_from_file_location("bank_oracle", project_dir / "bank.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(project_dir: Path) -> list[str]:
    bank = _load(Path(project_dir))
    failures = []
    account = bank.Account("Ada", 100)
    try:
        account.deposit(-50)
        failures.append("negative deposit was accepted")
    except ValueError:
        pass
    except Exception as exc:  # noqa: BLE001
        failures.append(f"negative deposit raised {type(exc).__name__}")

    account = bank.Account("Ada", 100)
    try:
        account.withdraw(150)
        failures.append("overdraft was accepted")
    except ValueError:
        pass
    except Exception as exc:  # noqa: BLE001
        failures.append(f"overdraft raised {type(exc).__name__}")

    account = bank.Account("Ada", 80)
    try:
        assert account.deposit(20) == 100
        assert account.withdraw(40) == 60
    except Exception as exc:  # noqa: BLE001
        failures.append(f"honest movement failed: {exc}")
    return failures
