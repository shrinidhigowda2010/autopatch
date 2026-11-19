import type { Severity } from "../types";

const styles: Record<Severity, string> = {
  critical: "bg-bug/10 text-bug border-bug/30",
  high: "bg-review/10 text-review border-review/30",
  medium: "bg-ink/5 text-ink border-line",
  low: "bg-panel text-mist border-line",
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`badge-emboss ${styles[severity]}`}>
      {severity}
    </span>
  );
}
