"""Merge findings that describe the same bug and drop exact duplicates."""

from __future__ import annotations

from app.analysis.catalog import needs_review
from app.analysis.findings import Finding


def merge_findings(groups: list[list[Finding]]) -> list[Finding]:
    best: dict[tuple, Finding] = {}
    order: list[tuple] = []
    for group in groups:
        for finding in group:
            key = (finding.file, finding.rule_id, finding.symbol or str(finding.line))
            if key not in best:
                best[key] = finding
                order.append(key)
                continue
            best[key] = _prefer(best[key], finding)
    return _fold_ai_duplicates([best[key] for key in order])


def _short_symbol(finding: Finding) -> str:
    return (finding.symbol or "").rsplit(".", 1)[-1].strip()


def _fold_ai_duplicates(findings: list[Finding]) -> list[Finding]:
    """Gemini often re-reports a bug the rules already caught, in its own words and on a nearby line.

    When a Gemini-only finding sits in the same function of the same file as a rule finding of the
    same category, keep one card: the rule finding (it has a tested patch) credited to both sources.
    """
    kept: list[Finding] = []
    for finding in findings:
        sources = finding.source.split("+")
        symbol = _short_symbol(finding)
        twin = None
        if sources == ["gemini"] and symbol and finding.category != "style":
            twin = next(
                (
                    other
                    for other in kept
                    if "gemini" not in other.source.split("+")
                    and other.file == finding.file
                    and _short_symbol(other) == symbol
                    and other.category == finding.category
                ),
                None,
            )
        if twin is None:
            kept.append(finding)
            continue
        twin.source = twin.source + "+gemini"
        twin.confidence = max(twin.confidence, finding.confidence)
        twin.needs_human_review = needs_review(twin.confidence, twin.rule_id)
    return kept


def _prefer(left: Finding, right: Finding) -> Finding:
    primary, secondary = (left, right) if _rank(left) >= _rank(right) else (right, left)
    sources = []
    for piece in (primary.source + "+" + secondary.source).split("+"):
        if piece and piece not in sources:
            sources.append(piece)
    primary.source = "+".join(sources)
    primary.confidence = max(primary.confidence, secondary.confidence)
    primary.needs_human_review = needs_review(primary.confidence, primary.rule_id)
    if secondary.demo_cache_used or primary.demo_cache_used:
        primary.demo_cache_used = True
    if len(secondary.root_cause) > len(primary.root_cause):
        primary.root_cause = secondary.root_cause
        primary.trigger = secondary.trigger or primary.trigger
        primary.student_explanation = secondary.student_explanation or primary.student_explanation
    return primary


def _rank(finding: Finding) -> tuple:
    origin = 2 if "ast" in finding.source.split("+") else 1 if "cached_demo" not in finding.source else 0
    return (origin, len(finding.root_cause), finding.confidence)
