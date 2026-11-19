import type { Severity } from "../types";

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function severityRank(severity: Severity): number {
  return { critical: 0, high: 1, medium: 2, low: 3 }[severity] ?? 4;
}

export function explanationFor(
  studentMode: boolean,
  language: "en" | "kn" | "hi",
  bug: { root_cause: string; student_explanation: string; explanation_kn: string; explanation_hi: string },
): string {
  if (language === "kn" && bug.explanation_kn) return bug.explanation_kn;
  if (language === "hi" && bug.explanation_hi) return bug.explanation_hi;
  if (studentMode) return bug.student_explanation || bug.root_cause;
  return bug.root_cause;
}

export function needsReview(confidence: number, flagged: boolean): boolean {
  return flagged || confidence < 0.8;
}

const SOURCE_NAMES: Record<string, string> = {
  ast: "Rule engine",
  rule: "Rule engine",
  gemini: "Gemini",
  pylint: "pylint",
  pyflakes: "pyflakes",
  bandit: "bandit",
  secrets: "Secret scanner",
  secret_scan: "Secret scanner",
  cached_demo: "Project knowledge",
};

// "ast+cached_demo" -> "Rule engine + Project knowledge"
export function sourceLabel(source: string): string {
  const names = source
    .split("+")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => SOURCE_NAMES[part] ?? part);
  return Array.from(new Set(names)).join(" + ");
}

// Server timestamps are UTC. Older rows may lack a zone suffix, so treat those as UTC too.
function parseServerTime(iso: string): Date | null {
  if (!iso) return null;
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  const date = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

// "2026-11-19T16:51:00+00:00" -> "10:21 PM, 19 Nov" in the viewer's own time zone.
export function friendlyTime(iso: string): string {
  const date = parseServerTime(iso);
  if (!date) return iso;
  const time = date.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true }).toUpperCase();
  const day = date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return `${time}, ${day}`;
}

const EVENT_NAMES: Record<string, string> = {
  upload: "Uploaded",
  scan_started: "Scan started",
  scan_finished: "Scan finished",
  bug_found: "Bug found",
  patch_proposed: "Fix proposed",
  patch_applied: "Fix applied",
  patch_rejected: "Fix rejected",
  decision: "Decision",
  approved: "Approved",
  rejected: "Rejected",
  edited: "Edited",
  skipped: "Skipped",
  "auto-applied": "Auto-applied",
  rolled_back: "Rolled back",
  rollback: "Rolled back",
  test_started: "Tests started",
  test_finished: "Tests finished",
  attack: "Break-It",
  debate: "Debate",
  translate: "Translated",
};

// "patch_proposed" -> "Fix proposed"
export function eventLabel(kind: string): string {
  if (EVENT_NAMES[kind]) return EVENT_NAMES[kind];
  const words = kind.replace(/[_-]+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : kind;
}
