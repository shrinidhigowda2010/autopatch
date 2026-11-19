"""Break-It Attack Mode: throw hostile inputs at a function before and after its fix.

Inputs come from Gemini (when it is reachable) and from a rule-based generator.
Both versions run in the sandbox, never in the server process.
"""

from __future__ import annotations

import ast
import json
import logging
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from app.arena.context import PatchContext, Target, find_target
from app.ingest.files import IngestError
from app.sandbox.runner import run_in_sandbox

log = logging.getLogger(__name__)

MIN_CASES = 10
MAX_CASES = 15
HARNESS = Path(__file__).with_name("harness.py")
MARKER = "FIXPILOT_RESULTS "


@dataclass
class AttackCase:
    label: str
    args: list[str]  # Python literal expressions, one per parameter
    origin: str = "rules"  # rules | gemini
    wrong_type: bool = False  # a TypeError here is Python refusing bad input, not a crash


# ---------------------------------------------------------------- input generation

# Labels whose input has the wrong type for the parameter.
_WRONG_TYPE = {
    "None instead of a list",
    "strings instead of numbers",
    "mixed types",
    "nested lists",
    "unicode text",
    "None",
    "number as text",
    "number instead of text",
    "empty list",
    "empty string",
    "empty dict",
    "unicode",
}

_HOSTILE = {
    "collection": [
        ("empty list", "[]"),
        ("None instead of a list", "None"),
        ("negative values", "[-5, -10]"),
        ("values over the maximum", "[150, 200]"),
        ("huge numbers", "[10**18, 10**18]"),
        ("strings instead of numbers", "['a', 'b']"),
        ("mixed types", "[1, 'two', 3]"),
        ("NaN inside", "[float('nan')]"),
        ("a single zero", "[0]"),
        ("ten thousand items", "list(range(10000))"),
        ("nested lists", "[[1, 2], [3]]"),
        ("unicode text", "['ಕನ್ನಡ', '🙂']"),
    ],
    "number": [
        ("zero", "0"),
        ("negative", "-1"),
        ("very negative", "-10**9"),
        ("huge", "10**18"),
        ("infinity", "float('inf')"),
        ("NaN", "float('nan')"),
        ("None", "None"),
        ("number as text", "'5'"),
        ("boolean", "True"),
        ("tiny float", "1e-308"),
    ],
    "text": [
        ("empty string", "''"),
        ("None", "None"),
        ("SQL injection", "\"' OR '1'='1\""),
        ("unicode", "'ಕನ್ನಡ 🙂 ü'"),
        ("very long text", "'a' * 100000"),
        ("number instead of text", "123"),
        ("only spaces", "'   '"),
        ("newline and NUL byte", "'a\\n\\x00b'"),
    ],
    "unknown": [
        ("None", "None"),
        ("empty list", "[]"),
        ("empty string", "''"),
        ("zero", "0"),
        ("negative", "-1"),
        ("huge", "10**18"),
        ("NaN", "float('nan')"),
        ("unicode", "'ಕನ್ನಡ🙂'"),
        ("empty dict", "{}"),
    ],
}
_NORMAL = {"collection": "[70, 80, 90]", "number": "10", "text": "'alice'", "unknown": "1"}
_COLLECTION_NAMES = ("items", "values", "nums", "numbers", "marks", "scores", "list", "rows", "data", "cart", "prices")
_NUMBER_NAMES = ("amount", "value", "count", "num", "price", "qty", "total", "whole", "part", "percent", "age", "n", "x", "y")
_TEXT_NAMES = ("name", "user", "username", "password", "text", "query", "path", "email", "word", "title", "s")


def param_kinds(target: Target) -> dict[str, str]:
    """Guess what each parameter is meant to hold from how the function uses it."""
    kinds = {name: "unknown" for name in target.params}
    try:
        tree = ast.parse(target.source)
    except SyntaxError:
        tree = None
    for node in ast.walk(tree) if tree else []:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"len", "sum", "sorted", "max", "min"}:
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id in kinds:
                    kinds[arg.id] = "collection"
        elif isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.iter, ast.Name) and node.iter.id in kinds:
            kinds[node.iter.id] = "collection"
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in kinds:
            kinds[node.value.id] = "collection"
        elif isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                if isinstance(side, ast.Name) and kinds.get(side.id) == "unknown":
                    kinds[side.id] = "number"
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in kinds
            and node.attr in {"lower", "upper", "strip", "split", "startswith", "endswith", "encode", "replace"}
        ):
            kinds[node.value.id] = "text"
    for name, kind in kinds.items():
        if kind != "unknown":
            continue
        lowered = name.lower()
        if lowered.endswith("s") and len(lowered) > 2 or any(hint in lowered for hint in _COLLECTION_NAMES):
            kinds[name] = "collection"
        elif lowered in _NUMBER_NAMES or any(hint in lowered for hint in _NUMBER_NAMES if len(hint) > 2):
            kinds[name] = "number"
        elif lowered in _TEXT_NAMES or any(hint in lowered for hint in _TEXT_NAMES if len(hint) > 2):
            kinds[name] = "text"
    return kinds


def rule_cases(target: Target) -> list[AttackCase]:
    if not target.params:
        return [AttackCase("call with no arguments", [])]
    kinds = param_kinds(target)
    normal = [_NORMAL[kinds[name]] for name in target.params]
    pools = {name: list(_HOSTILE[kinds[name]]) for name in target.params}
    if len(target.params) == 1 and len(pools[target.params[0]]) < MAX_CASES:
        extra = [item for item in _HOSTILE["unknown"] if item[1] not in {expr for _l, expr in pools[target.params[0]]}]
        pools[target.params[0]].extend(extra)
    cases: list[AttackCase] = []
    # Change one parameter at a time, taking turns, so every parameter gets attacked.
    while len(cases) < MAX_CASES and any(pools.values()):
        for index, name in enumerate(target.params):
            if not pools[name] or len(cases) >= MAX_CASES:
                continue
            label, expr = pools[name].pop(0)
            args = list(normal)
            args[index] = expr
            prefix = f"{name}: " if len(target.params) > 1 else ""
            wrong = label in _WRONG_TYPE and not (kinds[name] == "collection" and label == "empty list")
            wrong = wrong and not (kinds[name] == "text" and label in {"empty string", "unicode"})
            cases.append(AttackCase(prefix + label, args, wrong_type=wrong))
    return cases


_ALLOWED_CALLS = {"float", "int", "str", "list", "range", "dict", "set", "tuple", "bytes"}


def safe_expression(expr: str) -> bool:
    """Only literals and a few harmless constructors, with no huge powers or repeats."""
    if not isinstance(expr, str) or len(expr) > 200:
        return False
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict, ast.Load)):
            continue
        if isinstance(node, (ast.UnaryOp, ast.USub, ast.UAdd, ast.Not, ast.Add, ast.Sub, ast.Div)):
            continue
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, int) and 0 <= node.right.value <= 400):
                    return False
            elif isinstance(node.op, ast.Mult):
                sizes = [side.value for side in (node.left, node.right) if isinstance(side, ast.Constant) and isinstance(side.value, int)]
                if not sizes or max(abs(size) for size in sizes) > 1_000_000:
                    return False
            elif not isinstance(node.op, (ast.Add, ast.Sub, ast.Div)):
                return False
            continue
        if isinstance(node, (ast.Pow, ast.Mult)):
            continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_CALLS and not node.keywords:
            continue
        if isinstance(node, ast.Name) and node.id in _ALLOWED_CALLS:
            continue
        return False
    return True


_GEMINI_PROMPT = """You are a penetration tester for Python functions.
Write hostile inputs that could crash, hang or fool this function: empty values,
None, negatives, huge numbers, unicode, wrong types, boundary values.

Function `{name}` takes these positional parameters: {params}.

{source}

Return JSON: {{"cases": [{{"label": "short description", "args": ["python literal", ...], "wrong_type": false}}]}}
Set wrong_type to true when an argument has the wrong type for its parameter.
Each args item must be a Python literal expression (like [], None, -1, 10**18,
float('nan'), 'ಕನ್ನಡ'), one per parameter, in order. Give at most 8 cases.
"""


def gemini_cases(target: Target) -> list[AttackCase]:
    from app.llm.gemini import GeminiError, ask_gemini, strip_fences

    if not target.params:
        return []
    prompt = _GEMINI_PROMPT.format(name=target.name, params=", ".join(target.params), source=target.source[:6000])
    try:
        payload = json.loads(strip_fences(ask_gemini(prompt, json_output=True, timeout=15, prefer_fast=True)))
    except (GeminiError, json.JSONDecodeError, ValueError) as exc:
        log.info("gemini attack generation skipped: %s", exc)
        return []
    cases = []
    for item in (payload.get("cases") if isinstance(payload, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        args = item.get("args")
        if not isinstance(args, list) or len(args) != len(target.params):
            continue
        if not all(safe_expression(arg) for arg in args):
            continue
        label = str(item.get("label") or "AI attack")[:80]
        cases.append(AttackCase(label, [str(arg) for arg in args], "gemini", bool(item.get("wrong_type"))))
    return cases[:8]


def build_cases(target: Target, use_gemini: bool = True) -> list[AttackCase]:
    chosen: list[AttackCase] = []
    seen: set[tuple[str, ...]] = set()
    for case in (gemini_cases(target) if use_gemini else []) + rule_cases(target):
        key = tuple(case.args)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(case)
        if len(chosen) >= MAX_CASES:
            break
    return chosen


# ---------------------------------------------------------------- running


def _run_version(workspace: Path, rel_file: str, code: str, target: Target, cases: list[AttackCase], label: str) -> dict:
    scratch = Path(tempfile.mkdtemp(prefix=f"fixpilot-attack-{label}-"))
    try:
        shutil.copytree(workspace, scratch / "project", ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"))
        root = scratch / "project"
        module_path = root / rel_file
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text(code, encoding="utf-8")
        shutil.copy(HARNESS, root / "_fixpilot_attack.py")
        (root / "_fixpilot_cases.json").write_text(json.dumps([asdict(case) for case in cases]), encoding="utf-8")
        timeout = min(60, 2 * len(cases) + 10)
        result = run_in_sandbox(
            [sys.executable, "_fixpilot_attack.py", str(module_path), target.class_name, target.name],
            root,
            timeout=timeout,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    line = next((row for row in reversed(result.stdout.splitlines()) if row.startswith(MARKER)), "")
    if not line:
        detail = "timed out" if result.timed_out else (result.stderr.strip().splitlines() or ["no output"])[-1]
        return {"error": f"The {label} code could not be attacked: {detail}"[:300]}
    payload = json.loads(line[len(MARKER):])
    if "import_error" in payload:
        return {"error": f"The {label} code failed to import: {payload['import_error']}"}
    return payload


def run_attack(context: PatchContext, use_gemini: bool = True) -> dict:
    if not context.patch.file.endswith(".py"):
        raise IngestError("Break-It mode works on Python files.", 400)
    target = find_target(context.new_source, context.bug.symbol, context.bug.line)
    if target is None:
        raise IngestError("FixPilot couldn't find the function this patch changes.", 422)
    cases = build_cases(target, use_gemini=use_gemini)
    from app.services import workspace_for

    workspace = workspace_for(context.project)
    with ThreadPoolExecutor(max_workers=2) as pool:
        old_job = pool.submit(_run_version, workspace, context.patch.file, context.old_source, target, cases, "old")
        new_job = pool.submit(_run_version, workspace, context.patch.file, context.new_source, target, cases, "new")
        old, new = old_job.result(), new_job.result()
    for side in (old, new):
        if "error" in side:
            raise IngestError(side["error"], 422)
    return score(target, cases, old["results"], new["results"])


def _refused(case: AttackCase, outcome: dict) -> dict:
    """A TypeError on a wrong-type input is Python refusing it, which is fine behaviour."""
    if case.wrong_type and outcome.get("status") == "crashed" and str(outcome.get("detail", "")).startswith("TypeError"):
        return {**outcome, "status": "rejected", "detail": outcome["detail"] + " (wrong type refused)"}
    return outcome


def score(target: Target, cases: list[AttackCase], old: list[dict], new: list[dict]) -> dict:
    rows = []
    for case, before, after in zip(cases, old, new, strict=False):
        before, after = _refused(case, before), _refused(case, after)
        if before["status"] == "ok" and after["status"] == "rejected":
            # The old code returned a value for input the fix now refuses: a silent wrong answer.
            before = {**before, "status": "accepted"}
        old_broke = before["status"] in {"crashed", "hung", "accepted"}
        new_held = after["status"] in {"ok", "rejected"}
        if old_broke and new_held:
            verdict = "blocked"
        elif not new_held:
            verdict = "still breaks"
        else:
            verdict = "both fine"
        rows.append({**asdict(case), "old": before, "new": after, "verdict": verdict})
    counted = [row for row in rows if row["old"]["status"] != "skipped"]
    total = len(counted)
    old_crashed = sum(1 for row in counted if row["old"]["status"] in {"crashed", "hung"})
    old_accepted = sum(1 for row in counted if row["old"]["status"] == "accepted")
    old_failed = old_crashed + old_accepted
    new_survived = sum(1 for row in counted if row["new"]["status"] in {"ok", "rejected"})
    origins = {case.origin for case in cases}
    return {
        "function": f"{target.class_name}.{target.name}" if target.class_name else target.name,
        "params": target.params,
        "engine": "gemini+rules" if "gemini" in origins else "rules",
        "total": total,
        "old_failed": old_failed,
        "old_crashed": old_crashed,
        "old_accepted_bad_input": old_accepted,
        "new_survived": new_survived,
        "blocked": sum(1 for row in rows if row["verdict"] == "blocked"),
        "headline": f"Old code failed {old_failed}/{total} · New code survived {new_survived}/{total}",
        "cases": rows,
    }
