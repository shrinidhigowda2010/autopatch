"""Turn a rule hit into a small source change. Each fixer re-reads the
syntax tree, so applying two fixes to the same file still works.
"""

from __future__ import annotations

import ast

from app.patching.rewrite import body_indent, ensure_import, insert_before, replace_node

_EMPTY = {
    "list": "[]",
    "dict": "{}",
    "set": "set()",
}


def propose_fix(source: str, rule_id: str, symbol: str = "", extra: dict | None = None) -> str | None:
    extra = extra or {}
    try:
        source = expand_one_liners(source)
        tree = ast.parse(source)
    except SyntaxError:
        return None
    dispatch = {
        "marks_out_of_range": _fix_marks,
        "empty_collection_divisor": _fix_empty,
        "parameter_divisor": _fix_zero,
        "deposit_non_positive": _fix_deposit,
        "withdraw_overdraft": _fix_withdraw,
        "sql_injection": _fix_sql,
        "hardcoded_secret": _fix_secret,
        "mutable_default_argument": _fix_mutable,
        "off_by_one_neighbor": _fix_neighbor,
        "off_by_one_skip_first": _fix_skip,
    }
    handler = dispatch.get(rule_id)
    if handler is None:
        return None
    updated = handler(source, tree, symbol, extra)
    if updated is None or updated == source:
        return None
    try:
        ast.parse(updated)
    except SyntaxError:
        return None
    return updated


def expand_one_liners(source: str) -> str:
    """Move a one-line function body onto its own line, so a guard can go above it.

    def average(x): return sum(x) / len(x)
    becomes
    def average(x):
        return sum(x) / len(x)
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    one_liners = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and len(node.body) == 1
        and node.body[0].lineno == node.lineno
        and node.body[0].end_lineno == node.lineno
    ]
    for fn in sorted(one_liners, key=lambda node: node.lineno, reverse=True):
        index = fn.lineno - 1
        line = lines[index]
        indent = line[: len(line) - len(line.lstrip())]
        head, body = line[: fn.body[0].col_offset].rstrip(), line[fn.body[0].col_offset :]
        lines[index] = f"{head}\n{indent}    {body}"
    return "".join(lines)


def _functions(tree: ast.AST, symbol: str) -> list[ast.FunctionDef]:
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    if symbol:
        named = [node for node in found if node.name == symbol]
        if named:
            return named
    return found


def _fix_marks(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    variable = extra.get("variable") or "mark"
    for fn in _functions(tree, symbol):
        for loop in [node for node in ast.walk(fn) if isinstance(node, ast.For)]:
            if not isinstance(loop.target, ast.Name) or loop.target.id != variable:
                continue
            indent = body_indent(source, loop)
            block = (
                f"{indent}if {variable} < 0 or {variable} > 100:\n"
                f"{indent}    raise ValueError(\"each mark must be between 0 and 100\")\n"
            )
            segment = ast.get_source_segment(source, loop) or ""
            if "each mark must be between 0 and 100" in segment:
                return None
            return insert_before(source, loop.body[0].lineno, block)
    return None


def _fix_empty(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    name = extra.get("collection") or "values"
    for fn in _functions(tree, symbol):
        if f"if not {name}:" in ast.unparse(fn):
            return None
        indent = body_indent(source, fn)
        block = f"{indent}if not {name}:\n{indent}    raise ValueError(\"{name} cannot be empty\")\n"
        return insert_before(source, _body_line(fn), block)
    return None


def _fix_zero(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    name = extra.get("divisor") or "divisor"
    for fn in _functions(tree, symbol):
        if f"if {name} == 0:" in ast.unparse(fn):
            return None
        indent = body_indent(source, fn)
        block = f"{indent}if {name} == 0:\n{indent}    raise ValueError(\"{name} cannot be zero\")\n"
        return insert_before(source, _body_line(fn), block)
    return None


def _fix_deposit(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    amount = extra.get("amount") or "amount"
    for fn in _functions(tree, symbol or "deposit"):
        if fn.name not in {"deposit", "credit"} and symbol:
            continue
        if "deposit amount must be positive" in ast.unparse(fn):
            return None
        indent = body_indent(source, fn)
        block = (
            f"{indent}if {amount} <= 0:\n"
            f"{indent}    raise ValueError(\"deposit amount must be positive\")\n"
        )
        return insert_before(source, _body_line(fn), block)
    return None


def _fix_withdraw(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    amount = extra.get("amount") or "amount"
    for fn in _functions(tree, symbol or "withdraw"):
        if "insufficient funds" in ast.unparse(fn):
            return None
        indent = body_indent(source, fn)
        block = (
            f"{indent}if {amount} <= 0:\n"
            f"{indent}    raise ValueError(\"withdrawal amount must be positive\")\n"
            f"{indent}if {amount} > self.balance:\n"
            f"{indent}    raise ValueError(\"insufficient funds\")\n"
        )
        return insert_before(source, _body_line(fn), block)
    return None


def _fix_mutable(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    arg_name = extra.get("arg")
    kind = extra.get("kind") or "list"
    for fn in _functions(tree, symbol):
        pairs = list(zip(fn.args.args[-len(fn.args.defaults) :], fn.args.defaults)) if fn.args.defaults else []
        for arg, default in pairs:
            if arg_name and arg.arg != arg_name:
                continue
            if not isinstance(default, (ast.List, ast.Dict, ast.Set, ast.Call)):
                continue
            updated = replace_node(source, default, "None")
            tree2 = ast.parse(updated)
            fn2 = next(node for node in ast.walk(tree2) if isinstance(node, ast.FunctionDef) and node.name == fn.name)
            indent = body_indent(updated, fn2)
            empty = _EMPTY.get(kind, "[]")
            block = f"{indent}if {arg.arg} is None:\n{indent}    {arg.arg} = {empty}\n"
            if f"if {arg.arg} is None:" in ast.unparse(fn2):
                return updated
            return insert_before(updated, _body_line(fn2), block)
    return None


def _fix_secret(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    var = extra.get("var") or symbol
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != var:
            continue
        if not isinstance(node.value, ast.Constant):
            continue
        updated = replace_node(source, node.value, f'os.environ.get("{var}", "")')
        return ensure_import(updated, "os")
    return None


def _fix_neighbor(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    seq = extra.get("sequence")
    for fn in _functions(tree, symbol):
        for loop in [node for node in ast.walk(fn) if isinstance(node, ast.For)]:
            call = loop.iter
            if not isinstance(call, ast.Call) or len(call.args) != 1:
                continue
            if seq and ast.unparse(call.args[0]) != f"len({seq})":
                continue
            return replace_node(source, call, f"range(len({seq or 'items'}) - 1)")
    return None


def _fix_skip(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    seq = extra.get("sequence") or "items"
    for fn in _functions(tree, symbol):
        for loop in [node for node in ast.walk(fn) if isinstance(node, ast.For)]:
            call = loop.iter
            text = ast.unparse(call)
            if text == f"range(1, len({seq}))":
                return replace_node(source, call, f"range(len({seq}))")
    return None


def _fix_sql(source: str, tree: ast.AST, symbol: str, extra: dict) -> str | None:
    from app.analysis.ast_rules import _dynamic_sql_assignments, _expr_is_dynamic_sql, _formatted_names, _is_execute

    scopes = _functions(tree, symbol) or [tree]
    for scope in scopes:
        dynamic = _dynamic_sql_assignments(scope)
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call) or not _is_execute(node) or not node.args:
                continue
            arg = node.args[0]
            expr = dynamic.get(arg.id) if isinstance(arg, ast.Name) else None
            if expr is None and _expr_is_dynamic_sql(arg):
                expr = arg
            if not isinstance(expr, ast.JoinedStr):
                continue
            query, names = _qmark(expr)
            if not query or not names:
                names = extra.get("names") or names
            if not query:
                continue
            edits: list[tuple[int, int, str]] = []
            start, end = _span(source, expr)
            edits.append((start, end, repr(query)))
            if isinstance(arg, ast.Name) and len(node.args) == 1:
                call_start, call_end = _span(source, node)
                params = ", ".join(names)
                edits.append((call_start, call_end, f"{ast.unparse(node.func)}({arg.id}, ({params}))"))
            edits.sort(reverse=True)
            updated = source
            for start, end, text in edits:
                updated = updated[:start] + text + updated[end:]
            return updated
    return None


def _qmark(node: ast.JoinedStr) -> tuple[str, list[str]]:
    parts: list[str] = []
    names: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
            parts.append("?")
            names.append(value.value.id)
        else:
            return "", []
    query = "".join(parts).replace("'?'", "?").replace('"?"', "?")
    return query, names


def _span(source: str, node: ast.AST) -> tuple[int, int]:
    from app.patching.rewrite import node_span

    return node_span(source, node)


def _body_line(fn: ast.FunctionDef) -> int:
    first = fn.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(getattr(first, "value", None), ast.Constant)
        and isinstance(first.value.value, str)
        and len(fn.body) > 1
    ):
        return fn.body[1].lineno
    return first.lineno
