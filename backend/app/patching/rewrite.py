"""Small helpers for editing Python source without reformatting the file."""

from __future__ import annotations

import ast


def node_span(source: str, node: ast.AST) -> tuple[int, int]:
    lines = source.splitlines(keepends=True)

    def offset(lineno: int, col: int) -> int:
        passed = sum(len(lines[i]) for i in range(lineno - 1))
        line = lines[lineno - 1]
        fragment = line.encode("utf-8")[:col].decode("utf-8", errors="ignore")
        return passed + len(fragment)

    return (
        offset(node.lineno, node.col_offset),
        offset(node.end_lineno or node.lineno, node.end_col_offset or 0),
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
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], "value", None), ast.Constant):
        if isinstance(tree.body[0].value.value, str):
            insert_at = tree.body[0].end_lineno or 1
    lines = source.splitlines(keepends=True)
    lines.insert(insert_at, f"import {module}\n")
    if insert_at == 0 or not lines[insert_at].endswith("\n"):
        pass
    return "".join(lines)
