"""Run uploaded code in a temp directory with CPU, memory and time limits.

Network is not fully namespaced (that needs extra privileges). The child
does not receive API keys, database URLs, or proxy settings, and its output
is truncated.
"""

from __future__ import annotations

import contextlib
import os
import resource
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

_SECRET_PREFIXES = (
    "GEMINI",
    "DATABASE",
    "AWS",
    "SECRET",
    "TOKEN",
    "KEY",
    "PASSWORD",
    "OPENAI",
    "ANTHROPIC",
)
_MAX_OUTPUT = 8000


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def sandbox_env(workdir: Path) -> dict[str, str]:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / ".tmp").mkdir(exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(workdir),
        "TMPDIR": str(workdir / ".tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(workdir),
    }


def _limits(cpu_seconds: int, mem_mb: int) -> None:
    cpu = max(1, cpu_seconds)
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    mem = mem_mb * 1024 * 1024
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_FSIZE, (8_000_000, 8_000_000))
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))


def run_in_sandbox(
    argv: list[str],
    cwd: Path,
    timeout: int | None = None,
    mem_mb: int | None = None,
) -> RunResult:
    timeout = timeout or settings.sandbox_timeout_s
    mem_mb = mem_mb or settings.sandbox_mem_mb
    started = time.monotonic()

    def preexec() -> None:
        _limits(timeout, mem_mb)

    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=sandbox_env(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            preexec_fn=preexec,
            start_new_session=True,
        )
        elapsed = time.monotonic() - started
        timed_out = proc.returncode < 0
        return RunResult(
            returncode=proc.returncode,
            stdout=_clip(proc.stdout),
            stderr=_clip(proc.stderr),
            timed_out=timed_out,
            duration_s=round(elapsed, 3),
        )
    except (subprocess.TimeoutExpired, PermissionError) as exc:
        elapsed = time.monotonic() - started
        stdout = getattr(exc, "stdout", "") or ""
        stderr = getattr(exc, "stderr", "") or ""
        if not isinstance(stdout, str):
            stdout = ""
        if not isinstance(stderr, str):
            stderr = ""
        return RunResult(
            returncode=-1,
            stdout=_clip(stdout),
            stderr=_clip(stderr + "\nTimed out."),
            timed_out=True,
            duration_s=round(elapsed, 3),
        )


def run_pytest(cwd: Path, target: str = "tests", timeout: int | None = None) -> RunResult:
    return run_in_sandbox([sys.executable, "-m", "pytest", "-q", target, "--tb=line"], cwd, timeout=timeout)


def _clip(text: str | None) -> str:
    if not text:
        return ""
    if len(text) <= _MAX_OUTPUT:
        return text
    return text[:_MAX_OUTPUT] + "\n… output truncated …\n"
