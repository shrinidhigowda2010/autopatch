"""The sandbox has to stop a runaway program."""

from pathlib import Path

from app.sandbox.runner import run_in_sandbox
import sys


def test_infinite_loop_is_stopped(tmp_path: Path):
    script = tmp_path / "loop.py"
    script.write_text("while True:\n    pass\n", encoding="utf-8")
    result = run_in_sandbox([sys.executable, str(script)], tmp_path, timeout=2, mem_mb=256)
    assert result.timed_out or result.returncode != 0
    assert len(result.stdout) < 9000
