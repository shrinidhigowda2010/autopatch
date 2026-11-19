"""A finding is one bug, from a linter, a tree rule, or Gemini."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Finding:
    rule_id: str
    file: str
    line: int
    end_line: int
    symbol: str
    title: str
    description: str
    category: str
    severity: str
    confidence: float
    impact: str
    root_cause: str
    trigger: str
    student_explanation: str
    explanation_kn: str
    explanation_hi: str
    source: str
    needs_human_review: bool
    snippet: str
    extra: dict = field(default_factory=dict)
    demo_cache_used: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def snippet_around(source: str, line: int, radius: int = 2) -> str:
    rows = source.splitlines()
    if not rows:
        return ""
    start = max(1, line - radius)
    end = min(len(rows), line + radius)
    out = []
    for number in range(start, end + 1):
        marker = ">" if number == line else " "
        out.append(f"{marker} {number:4d} | {rows[number - 1]}")
    return "\n".join(out)
