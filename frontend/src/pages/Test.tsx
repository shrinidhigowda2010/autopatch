import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

interface EventRow {
  id?: number;
  message: string;
  status: string;
}

export default function TestPage() {
  const { projectId = "" } = useParams();
  const [events, setEvents] = useState<EventRow[]>([]);
  const [status, setStatus] = useState("idle");
  const [summary, setSummary] = useState<Record<string, { passed?: boolean; stdout?: string }> | null>(null);
  const [error, setError] = useState("");

  async function start() {
    setError("");
    setEvents([]);
    setSummary(null);
    setStatus("queued");
    try {
      const run = await api<{ id: string }>(`/api/projects/${projectId}/tests`, { method: "POST" });
      const source = new EventSource(`/api/test-runs/${run.id}/events`);
      let finished = false;
      source.onmessage = (message) => {
        const row = JSON.parse(message.data) as EventRow;
        setEvents((current) => [...current, row]);
      };
      source.addEventListener("done", async () => {
        finished = true;
        source.close();
        const full = await api<{ status: string; summary: Record<string, { passed?: boolean; stdout?: string }> }>(
          `/api/test-runs/${run.id}`,
        );
        setStatus(full.status);
        setSummary(full.summary);
      });
      source.onerror = () => {
        if (finished) return;
        source.close();
        setError("The live test stream closed early. Open History if the tests are still going.");
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start tests.");
      setStatus("idle");
    }
  }

  const tone: Record<string, string> = {
    pass: "text-fixed",
    fail: "text-bug",
    info: "text-paper",
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">Test</h1>
      <p className="mt-2 text-mist">
        Existing tests run first. Then Fixpilot writes edge-case tests — a normal value, a minimum, a maximum, and an invalid value —
        and runs them before and after the patch. The full suite runs again as a regression check. The program runs in a temp folder with time and memory limits.
      </p>
      <button onClick={() => void start()} className="mt-5 btn-primary">
        {status === "queued" || status === "running" ? "Running…" : "Run before and after"}
      </button>
      {error && <p className="mt-4 text-bug">{error}</p>}
      <ol className="mt-6 space-y-2">
        {events.map((event, index) => (
          <li key={event.id ?? index} className={tone[event.status] || "text-paper"}>
            {event.message}
          </li>
        ))}
      </ol>
      {summary && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {(["existing_before", "generated_before", "generated_after", "regression_after"] as const).map((key) => (
            <div key={key} className="rounded-xl border border-line bg-panel p-3">
              <p className="text-sm font-medium">{key.replaceAll("_", " ")}</p>
              <p className={summary[key]?.passed ? "text-fixed" : "text-bug"}>{summary[key]?.passed ? "passed" : "failed"}</p>
              {summary[key]?.stdout && <pre className="mt-2 max-h-32 overflow-auto font-mono text-xs text-mist">{summary[key]?.stdout}</pre>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
