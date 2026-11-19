"""Before/after proof runs. Patches are applied only in a scratch copy."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from app.analysis.findings import Finding
from app.patching.apply import apply_findings
from app.sandbox.runner import RunResult, run_pytest
from app.testing.generate import render_tests


def _summary(result: RunResult) -> dict:
    return {
        "returncode": result.returncode,
        "passed": result.ok or result.returncode == 5,
        "timed_out": result.timed_out,
        "duration_s": result.duration_s,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def prove(
    workspace: Path,
    findings: list[Finding],
    emit: Callable[[str, str, dict], None] | None = None,
) -> dict:
    """Run existing tests, generated edge tests, then the same tests after patches."""

    def say(message: str, status: str = "info", payload: dict | None = None) -> None:
        if emit:
            emit(message, status, payload or {})

    actionable = [item for item in findings if item.category != "style" and item.severity != "low"]
    scratch_root = Path(tempfile.mkdtemp(prefix="fixpilot-proof-"))
    before = scratch_root / "before"
    after = scratch_root / "after"
    shutil.copytree(workspace, before)
    shutil.copytree(workspace, after)

    say("Running the project's existing tests, before any patch.")
    existing = run_pytest(before, "tests")
    say(
        "Existing tests finished." if existing.returncode in {0, 5} else "Some existing tests failed on the original code.",
        "pass" if existing.returncode in {0, 5} else "fail",
        _summary(existing),
    )

    generated = render_tests(actionable)
    (before / "_fixpilot_generated_test.py").write_text(generated, encoding="utf-8")
    say("Running generated edge-case tests (normal, min, max, invalid) on the original code.")
    gen_before = run_pytest(before, "_fixpilot_generated_test.py")
    say(
        "Generated tests failed on the original code, which is what an unfixed bug should do."
        if not gen_before.ok
        else "Generated tests already passed. The bug may be narrower than the tests.",
        "fail" if not gen_before.ok else "pass",
        _summary(gen_before),
    )

    say("Applying the proposed patches in a scratch copy. The project itself is unchanged.")
    changed = apply_findings(after, actionable)
    say(f"Patched {len(changed)} file(s) in the scratch copy.", "info", {"files": changed})
    (after / "_fixpilot_generated_test.py").write_text(generated, encoding="utf-8")

    say("Re-running the generated tests on the patched code.")
    gen_after = run_pytest(after, "_fixpilot_generated_test.py")
    say(
        "Generated tests passed after the patch." if gen_after.ok else "Generated tests still fail after the patch.",
        "pass" if gen_after.ok else "fail",
        _summary(gen_after),
    )

    say("Regression check: full suite on the patched code, including the original tests.")
    regression = run_pytest(after)
    say(
        "Full suite passed." if regression.ok else "Full suite reported failures.",
        "pass" if regression.ok else "fail",
        _summary(regression),
    )

    per_bug = []
    if len(actionable) == 1:
        # One bug: the patched generated-test run above already is its on-its-own check.
        only = actionable[0]
        per_bug.append(
            {
                "rule_id": only.rule_id,
                "symbol": only.symbol,
                "file": only.file,
                "passed": gen_after.ok,
                "stdout": gen_after.stdout,
                "stderr": gen_after.stderr,
            }
        )
    for finding in actionable if len(actionable) > 1 else []:
        say(f"Checking the patch for {finding.symbol or finding.rule_id} on its own.")
        scratch = scratch_root / f"bug-{finding.rule_id}-{finding.symbol}"
        shutil.copytree(workspace, scratch)
        apply_findings(scratch, [finding])
        (scratch / "_fixpilot_generated_test.py").write_text(render_tests([finding]), encoding="utf-8")
        alone = run_pytest(scratch, "_fixpilot_generated_test.py")
        passed = alone.ok
        per_bug.append(
            {
                "rule_id": finding.rule_id,
                "symbol": finding.symbol,
                "file": finding.file,
                "passed": passed,
                "stdout": alone.stdout,
                "stderr": alone.stderr,
            }
        )
        say(
            f"{finding.rule_id} ({finding.symbol}) {'passed' if passed else 'failed'} on its own.",
            "pass" if passed else "fail",
        )
    shutil.rmtree(scratch_root, ignore_errors=True)
    return {
        "existing_before": _summary(existing),
        "generated_before": _summary(gen_before),
        "generated_after": _summary(gen_after),
        "regression_after": _summary(regression),
        "per_bug": per_bug,
        "generated_passed": gen_after.ok,
        "regression_passed": regression.ok,
    }
