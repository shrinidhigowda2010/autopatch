import { useEffect, useState } from "react";
import { api } from "../api";

type Status = "checking" | "online" | "busy" | "key_rejected" | "off" | "unknown";

const LABELS: Record<Status, { text: string; hint: string; color: string }> = {
  checking: { text: "Checking Gemini…", hint: "", color: "bg-mist" },
  online: { text: "Gemini connected", hint: "Scans use static analysis and Gemini together.", color: "bg-fixed" },
  busy: {
    text: "Gemini busy · static analysis on",
    hint: "Google's models are overloaded for a moment. Scans, fixes and tests keep working with static analysis.",
    color: "bg-review",
  },
  key_rejected: {
    text: "Gemini unavailable · static analysis on",
    hint: "Google didn't accept this server's API key, so FixPilot is using static analysis, rules and tests for now.",
    color: "bg-review",
  },
  off: {
    text: "Static analysis only",
    hint: "No Gemini key is set on this server. Scans, fixes and tests still work.",
    color: "bg-review",
  },
  unknown: { text: "Server not reachable", hint: "The server may be waking up. Give it a few seconds.", color: "bg-mist" },
};

export default function AiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let alive = true;
    const check = () =>
      api<{ gemini_configured?: boolean; ai_engine?: string; gemini_status?: string }>("/api/health")
        .then((body) => {
          if (!alive) return;
          const live = body.gemini_status as Status | undefined;
          if (live && live in LABELS) setStatus(live);
          else setStatus(body.gemini_configured ? "online" : "off");
        })
        .catch(() => alive && setStatus("unknown"));
    void check();
    const timer = window.setInterval(check, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const label = LABELS[status];
  return (
    <p className="flex items-center gap-2 text-sm text-mist" title={label.hint}>
      <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${label.color}`} aria-hidden />
      {label.text}
    </p>
  );
}
