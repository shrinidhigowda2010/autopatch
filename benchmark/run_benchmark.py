"""Entry point so a judge can reproduce the benchmark numbers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.benchmark.runner import run_benchmark  # noqa: E402


def main() -> None:
    result = run_benchmark()
    out = ROOT / "benchmark" / "results"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "latest.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"detection {result['detection_rate']:.0%}  "
        f"fix success {result['fix_success_rate']:.0%}  "
        f"false positives {result['false_positive_count']}"
    )
    print(path)


if __name__ == "__main__":
    main()
