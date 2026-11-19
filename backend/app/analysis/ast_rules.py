"""Syntax-tree rules for the bug classes in the bundled samples.

The rules are deliberately narrow. A withdrawal that never looks at the
balance is reported. A random subtraction is not.
"""

from __future__ import annotations

import ast
import re

from app.analysis.catalog import needs_review, text_for
from app.analysis.findings import Finding, snippet_around

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

_MARK_NAME = re.compile(r"\b(marks?|scores?|grades?)\b", re.I)
_SECRET_NAME = re.compile(
    r"(password|passwd|secret|api_key|apikey|access_key|private_key|token)",
    re.I,
)
_PLACEHOLDERS = {
    "changeme",
    "password",
    "secret",
    "todo",
    "xxx",
    "your-password",
    "your_password",
    "insert-key",
    "redacted",
    "example",
}


def scan_source(relpath: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            _make(
                "syntax_error",
                relpath,
                exc.lineno or 1,
                exc.lineno or 1,
                "",
                source,
                confidence=0.99,
                title="Python file does not parse",
                description=exc.msg or "syntax error",
                category="crash",
                severity="high",
                impact="The file cannot be imported, so every caller fails.",
                root_cause=f"Python stopped while reading the file: {exc.msg}.",
                trigger="Import the module or run it.",
                student="The file has a typing mistake in the Python itself, so it cannot even start.",
                kn="ಫೈಲಿನಲ್ಲಿನ ಪೈಥಾನ್ ಬರವಣಿಗೆಯಲ್ಲಿ ತಪ್ಪಿದೆ, ಅದು ಶುರುವಾಗುವುದೇ ಇಲ್ಲ.",
                hi="फ़ाइल के पायथन लेखन में गलती है, इसलिए वह शुरू ही नहीं होती।",
            )
        ]
    found: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend(_scan_function(relpath, source, node))
        elif isinstance(node, ast.Assign):
            found.extend(_scan_secret_assign(relpath, source, node))
    found.extend(_scan_module_sql(relpath, source, tree))
    return found


def _make(
    rule_id: str,
    relpath: str,
    line: int,
    end_line: int,
    symbol: str,
    source: str,
    extra: dict | None = None,
    confidence: float | None = None,
    **overrides: str,
) -> Finding:
    spec = text_for(rule_id)
    merged = {**spec, **overrides}
    conf = float(confidence if confidence is not None else merged["confidence"])
    return Finding(
        rule_id=rule_id,
        file=relpath,
        line=line,
        end_line=end_line,
        symbol=symbol,
        title=str(merged["title"]),
        description=str(merged["description"]),
        category=str(merged["category"]),
        severity=str(merged["severity"]),
        confidence=conf,
        impact=str(merged["impact"]),
        root_cause=str(merged["root_cause"]),
        trigger=str(merged["trigger"]),
        student_explanation=str(merged["student"]),
        explanation_kn=str(merged["kn"]),
        explanation_hi=str(merged["hi"]),
        source="ast",
        needs_human_review=needs_review(conf, rule_id),
        snippet=snippet_around(source, line),
        extra=extra or {},
    )


def _scan_function(relpath: str, source: str, fn: FunctionNode) -> list[Finding]:
    found: list[Finding] = []
    found.extend(_mutable_defaults(relpath, source, fn))
    found.extend(_divisions(relpath, source, fn))
    found.extend(_marks_range(relpath, source, fn))
    found.extend(_balance_methods(relpath, source, fn))
    found.extend(_off_by_one(relpath, source, fn))
    return found


def _mutable_defaults(relpath: str, source: str, fn: FunctionNode) -> list[Finding]:
    found = []
    args = fn.args.args[-len(fn.args.defaults) :] if fn.args.defaults else []
    for arg, default in zip(args, fn.args.defaults, strict=False):
        kind = _mutable_kind(default)
        if not kind:
            continue
        found.append(
            _make(
                "mutable_default_argument",
                relpath,
                default.lineno,
                default.end_lineno or default.lineno,
                fn.name,
                source,
                extra={"arg": arg.arg, "kind": kind},
            )
        )
    return found


def _mutable_kind(node: ast.AST) -> str:
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Set):
        return "set"
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"list", "dict", "set"}
        and not node.args
        and not node.keywords
    ):
        return node.func.id
    return ""


def _divisions(relpath: str, source: str, fn: FunctionNode) -> list[Finding]:
    params = {arg.arg for arg in fn.args.args if arg.arg != "self"}
    found = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, (ast.Div, ast.FloorDiv)):
            continue
        collection = _len_target(node.right)
        if collection and not _empty_guard(fn, collection):
            found.append(
                _make(
                    "empty_collection_divisor",
                    relpath,
                    node.lineno,
                    node.end_lineno or node.lineno,
                    fn.name,
                    source,
                    extra={"collection": collection},
                )
            )
            continue
        if isinstance(node.right, ast.Name) and node.right.id in params and not _zero_guard(fn, node.right.id):
            found.append(
                _make(
                    "parameter_divisor",
                    relpath,
                    node.lineno,
                    node.end_lineno or node.lineno,
                    fn.name,
                    source,
                    extra={"divisor": node.right.id},
                )
            )
    return _unique_rules(found)


def _len_target(node: ast.AST) -> str:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and node.args
        and isinstance(node.args[0], ast.Name)
    ):
        return node.args[0].id
    return ""


def _empty_guard(fn: ast.AST, name: str) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        mentions = name in test and ("not " in test or "len(" in test or "== 0" in test or "< 1" in test)
        if mentions and _raises_or_returns(node):
            return True
    return False


def _zero_guard(fn: ast.AST, name: str) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if name in test and ("== 0" in test or "<= 0" in test or "is 0" in test) and _raises_or_returns(node):
            return True
    return False


def _raises_or_returns(node: ast.If) -> bool:
    return any(isinstance(child, (ast.Raise, ast.Return)) for child in ast.walk(node))


def _marks_range(relpath: str, source: str, fn: FunctionNode) -> list[Finding]:
    blob = " ".join([fn.name, relpath, *[arg.arg for arg in fn.args.args]])
    if not _MARK_NAME.search(blob):
        return []
    for loop in _for_loops(fn):
        if not isinstance(loop.target, ast.Name) or not isinstance(loop.iter, ast.Name):
            continue
        if not _loop_adds_target(loop):
            continue
        if _target_is_compared(fn, loop.target.id):
            continue
        return [
            _make(
                "marks_out_of_range",
                relpath,
                loop.lineno,
                loop.end_lineno or loop.lineno,
                fn.name,
                source,
                extra={"variable": loop.target.id},
            )
        ]
    return []


def _for_loops(fn: ast.AST) -> list[ast.For]:
    return [node for node in ast.walk(fn) if isinstance(node, ast.For)]


def _loop_adds_target(loop: ast.For) -> bool:
    target = loop.target.id if isinstance(loop.target, ast.Name) else ""
    for node in ast.walk(loop):
        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Add)
            and isinstance(node.value, ast.Name)
            and node.value.id == target
        ):
            return True
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add):
            names = _names(node.value)
            if target in names:
                return True
    return False


def _target_is_compared(fn: ast.AST, name: str) -> bool:
    return any(isinstance(node, ast.Compare) and name in _names(node) for node in ast.walk(fn))


def _names(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def _balance_methods(relpath: str, source: str, fn: FunctionNode) -> list[Finding]:
    amount = _amount_arg(fn)
    if fn.name in {"deposit", "credit"} and _balance_update(fn, ast.Add) and not _amount_guard(fn, amount):
        return [
            _make(
                "deposit_non_positive",
                relpath,
                fn.lineno,
                fn.end_lineno or fn.lineno,
                fn.name,
                source,
                extra={"amount": amount},
            )
        ]
    if fn.name in {"withdraw", "debit"} and _balance_update(fn, ast.Sub) and not _overdraft_guard(fn, amount):
        return [
            _make(
                "withdraw_overdraft",
                relpath,
                fn.lineno,
                fn.end_lineno or fn.lineno,
                fn.name,
                source,
                extra={"amount": amount},
            )
        ]
    return []


def _amount_arg(fn: FunctionNode) -> str:
    for arg in fn.args.args:
        if arg.arg != "self":
            return arg.arg
    return "amount"


def _balance_update(fn: FunctionNode, op: type) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.AugAssign) and isinstance(node.op, op) and _is_balance(node.target):
            return True
        if (
            isinstance(node, ast.Assign)
            and _is_balance(node.targets[0] if node.targets else None)
            and isinstance(node.value, ast.BinOp)
            and isinstance(node.value.op, op)
        ):
            return True
    return False


def _is_balance(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "balance"


def _amount_guard(fn: FunctionNode, amount: str) -> bool:
    return any(isinstance(node, ast.Compare) and amount in _names(node) for node in ast.walk(fn))


def _overdraft_guard(fn: FunctionNode, amount: str) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare):
            continue
        text = ast.unparse(node)
        if amount in text and "balance" in text:
            return True
    return False


def _off_by_one(relpath: str, source: str, fn: FunctionNode) -> list[Finding]:
    found = []
    for loop in _for_loops(fn):
        if not isinstance(loop.target, ast.Name):
            continue
        index = loop.target.id
        seq = _range_len_name(loop.iter)
        if seq and _indexes_offset(loop, seq, index, 1):
            found.append(
                _make(
                    "off_by_one_neighbor",
                    relpath,
                    loop.lineno,
                    loop.end_lineno or loop.lineno,
                    fn.name,
                    source,
                    extra={"sequence": seq, "index": index},
                )
            )
            continue
        skipped = _range_skip_first(loop.iter)
        if skipped and _indexes_name(loop, skipped, index):
            found.append(
                _make(
                    "off_by_one_skip_first",
                    relpath,
                    loop.lineno,
                    loop.end_lineno or loop.lineno,
                    fn.name,
                    source,
                    extra={"sequence": skipped, "index": index},
                )
            )
    return found


def _range_len_name(node: ast.AST) -> str:
    if not isinstance(node, ast.Call) or not _is_name(node.func, "range") or len(node.args) != 1:
        return ""
    return _len_target(node.args[0])


def _range_skip_first(node: ast.AST) -> str:
    if not isinstance(node, ast.Call) or not _is_name(node.func, "range") or len(node.args) != 2:
        return ""
    start, end = node.args
    if not (isinstance(start, ast.Constant) and start.value == 1):
        return ""
    return _len_target(end)


def _indexes_offset(loop: ast.For, seq: str, index: str, delta: int) -> bool:
    for node in ast.walk(loop):
        if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
            continue
        if node.value.id != seq or not isinstance(node.slice, ast.BinOp):
            continue
        if not isinstance(node.slice.op, ast.Add):
            continue
        left, right = node.slice.left, node.slice.right
        if isinstance(left, ast.Name) and left.id == index and isinstance(right, ast.Constant) and right.value == delta:
            return True
    return False


def _indexes_name(loop: ast.For, seq: str, index: str) -> bool:
    for node in ast.walk(loop):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == seq
            and isinstance(node.slice, ast.Name)
            and node.slice.id == index
        ):
            return True
    return False


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _scan_secret_assign(relpath: str, source: str, node: ast.Assign) -> list[Finding]:
    found: list[Finding] = []
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return found
    name = node.targets[0].id
    if not _SECRET_NAME.search(name):
        return found
    if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
        return found
    value = node.value.value.strip()
    if len(value) < 8 or value.lower() in _PLACEHOLDERS:
        return found
    found.append(
        _make(
            "hardcoded_secret",
            relpath,
            node.lineno,
            node.end_lineno or node.lineno,
            name,
            source,
            extra={"var": name},
        )
    )
    return found


def _scan_module_sql(relpath: str, source: str, tree: ast.AST) -> list[Finding]:
    found = []
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    scopes: list[tuple[str, ast.AST]] = [(fn.name, fn) for fn in functions]
    scopes.append(("", tree))
    for symbol, scope in scopes:
        dynamic = _dynamic_sql_assignments(scope)
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call) or not _is_execute(node) or not node.args:
                continue
            expr = _resolved_sql(node.args[0], dynamic)
            if expr is None:
                continue
            owner = symbol or _enclosing_function(tree, node)
            found.append(
                _make(
                    "sql_injection",
                    relpath,
                    node.lineno,
                    node.end_lineno or node.lineno,
                    owner,
                    source,
                    extra={"names": _formatted_names(expr)},
                )
            )
    return _unique_rules(found)


def _is_execute(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in {"execute", "executemany", "executescript"}:
        return True
    return isinstance(func, ast.Name) and func.id in {"execute", "executemany"}


def _dynamic_sql_assignments(scope: ast.AST) -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for node in ast.walk(scope):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and _expr_is_dynamic_sql(node.value):
            found[target.id] = node.value
    return found


def _resolved_sql(node: ast.AST, dynamic: dict[str, ast.AST]) -> ast.AST | None:
    if isinstance(node, ast.Name) and node.id in dynamic:
        return dynamic[node.id]
    if _expr_is_dynamic_sql(node):
        return node
    return None


def _expr_is_dynamic_sql(node: ast.AST) -> bool:
    text = ast.unparse(node).lower()
    if not any(word in text for word in ("select", "insert", "update", "delete")):
        return False
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(part, ast.FormattedValue) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    return bool(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format")


def _formatted_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if (
            isinstance(child, ast.FormattedValue)
            and isinstance(child.value, ast.Name)
            and child.value.id not in names
        ):
            names.append(child.value.id)
    return names


def _enclosing_function(tree: ast.AST, target: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _contains(node, target):
            return node.name
    return ""


def _contains(parent: ast.AST, target: ast.AST) -> bool:
    return any(child is target for child in ast.walk(parent))


def _unique_rules(found: list[Finding]) -> list[Finding]:
    seen = set()
    out = []
    for item in found:
        key = (item.rule_id, item.symbol, item.line)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
