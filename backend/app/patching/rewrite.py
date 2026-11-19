"""Small helpers for editing Python source without reformatting the file."""

from __future__ import annotations

import ast


def node_span(source: str, node: ast.AST) -> tuple[int, int]:
    """Character offsets of a node that carries position info (any expr or stmt)."""
    lines = source.splitlines(keepends=True)

    def offset(lineno: int, col: int) -> int:
        passed = sum(len(lines[i]) for i in range(lineno - 1))
        line = lines[lineno - 1]
        fragment = line.encode("utf-8")[:col].decode("utf-8", errors="ignore")
        return passed + len(fragment)

    start_line: int = getattr(node, "lineno", 1)
    return (
        offset(start_line, getattr(node, "col_offset", 0)),
        offset(getattr(node, "end_lineno", None) or start_line, getattr(node, "end_col_offset", None) or 0),
    )


def replace_node(source: str, node: ast.AST, text: str) -> str:
    start, end = node_span(source, node)
    return source[:start] + text + source[end:]


def insert_before(source: str, lineno: int, text: str) -> str:
    lines = source.splitlines(keepends=True)
    if text and not text.endswith("\n"):
        text += "\n"
    lines.insert(lineno - 1, text)
    return "".join(lines)


def body_indent(source: str, node: ast.AST) -> str:
    body = getattr(node, "body", None) or []
    if not body:
        return "    "
    line = source.splitlines()[body[0].lineno - 1]
    return line[: len(line) - len(line.lstrip(" "))] or "    "


def ensure_import(source: str, module: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Import) and any(alias.name == module for alias in node.names):
            return source
        if isinstance(node, ast.ImportFrom) and node.module == module:
            return source
    insert_at = 0
    first = tree.body[0] if tree.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        insert_at = first.end_lineno or 1
    lines = source.splitlines(keepends=True)
    lines.insert(insert_at, f"import {module}\n")
    if insert_at == 0 or not lines[insert_at].endswith("\n"):
        pass
    return "".join(lines)
