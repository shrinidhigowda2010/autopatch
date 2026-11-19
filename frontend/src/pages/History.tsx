import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

interface HistoryPayload {
  events: { kind: string; message: string; at: string; bug_id: string | null }[];
}

export default function History() {
  const { projectId = "" } = useParams();
  const [data, setData] = useState<HistoryPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<HistoryPayload>(`/api/projects/${projectId}/history`).then(setData).catch((err: Error) => setError(err.message));
  }, [projectId]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">History</h1>
      <p className="mt-2 text-mist">Scans, bugs, patches, test runs and accept or reject decisions are stored for this project.</p>
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        <a className="rounded-lg border border-line px-3 py-1.5" href={`/api/projects/${projectId}/export/json`}>Export JSON</a>
        <a className="rounded-lg border border-line px-3 py-1.5" href={`/api/projects/${projectId}/export/pdf`}>Export PDF</a>
        <a className="rounded-lg border border-line px-3 py-1.5" href={`/api/projects/${projectId}/export/zip`}>Export fixed zip</a>
      </div>
      {error && <p className="mt-4 text-bug">{error}</p>}
      <ol className="mt-6 space-y-3">
        {(data?.events || []).map((event) => (
          <li key={event.at + event.message} className="rounded-lg border border-line bg-panel px-3 py-2">
            <p className="font-mono text-xs text-mist">{event.at} · {event.kind}</p>
            <p className="mt-1 text-sm">{event.message}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
