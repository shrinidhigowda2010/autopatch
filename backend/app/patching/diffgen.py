"""Unified diffs for the review screen."""

from __future__ import annotations

import difflib


def unified_diff(path: str, before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def changed_region(before: str, after: str, context: int = 8) -> tuple[str, str]:
    """Return the hunk of each file that actually changed, with a little context."""
    old_lines = before.splitlines()
    new_lines = after.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    spans = [block for block in matcher.get_opcodes() if block[0] != "equal"]
    if not spans:
        return before, after
    start = max(0, min(block[1] for block in spans) - context)
    old_end = min(len(old_lines), max(block[2] for block in spans) + context)
    new_start = max(0, min(block[3] for block in spans) - context)
    new_end = min(len(new_lines), max(block[4] for block in spans) + context)
    return "\n".join(old_lines[start:old_end]) + "\n", "\n".join(new_lines[new_start:new_end]) + "\n"
