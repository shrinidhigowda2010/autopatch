import type { Severity } from "../types";

const styles: Record<Severity, string> = {
  critical: "bg-coral/15 text-coral border-coral/40",
  high: "bg-amber/15 text-amber border-amber/40",
  medium: "bg-sky/15 text-sky border-sky/40",
  low: "bg-white/5 text-mist border-line",
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide ${styles[severity]}`}>
      {severity}
    </span>
  );
}
