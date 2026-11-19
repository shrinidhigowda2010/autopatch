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
