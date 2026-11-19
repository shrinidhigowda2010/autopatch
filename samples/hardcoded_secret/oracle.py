"""Oracle for the hardcoded secret sample."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def check(project_dir: Path) -> list[str]:
    project_dir = Path(project_dir)
    text = (project_dir / "config.py").read_text(encoding="utf-8")
    failures = []
    if "sk-live-51H7autopatchDemoKeyDoNotUse" in text:
        failures.append("API key literal is still in the file")
    if "ProdDb#Password-2024" in text:
        failures.append("database password literal is still in the file")
    if "os.environ" not in text:
        failures.append("secrets are not read from the environment")

    os.environ["API_KEY"] = "from-env"
    os.environ["DB_PASSWORD"] = "also-from-env"
    spec = importlib.util.spec_from_file_location("config_oracle", project_dir / "config.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"config import failed: {exc}")
        return failures
    if module.API_KEY != "from-env":
        failures.append("API_KEY did not come from the environment")
    if module.DB_PASSWORD != "also-from-env":
        failures.append("DB_PASSWORD did not come from the environment")
    if module.service_name() != "billing":
        failures.append("service_name changed")
    return failures
