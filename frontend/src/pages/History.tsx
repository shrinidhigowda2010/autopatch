import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ListSkeleton } from "../components/Skeleton";
import { eventLabel, friendlyTime } from "../lib/format";

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
      <p className="mt-2 text-mist">Everything that happened to this project, from upload to the last test run. Download it as a report anytime.</p>
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        <a className="rounded-lg border border-line px-3 py-1.5" href={`/api/projects/${projectId}/export/json`}>Download JSON</a>
        <a className="rounded-lg border border-line px-3 py-1.5" href={`/api/projects/${projectId}/export/pdf`}>Download PDF report</a>
        <a className="rounded-lg border border-line px-3 py-1.5" href={`/api/projects/${projectId}/export/zip`}>Download fixed code (.zip)</a>
      </div>
      {error && <p className="mt-4 text-bug">{error}</p>}
      {!data && !error && (
        <div className="mt-6">
          <ListSkeleton />
        </div>
      )}
      {data && data.events.length === 0 && (
        <div className="mt-6">
          <EmptyState title="Nothing here yet">Run a scan and every step will be recorded on this page.</EmptyState>
        </div>
      )}
      <ol className="mt-6 space-y-3">
        {(data?.events || []).map((event, index) => (
          <li key={`${event.at}-${index}`} className="rounded-lg border border-line bg-panel px-3 py-2">
            <p className="font-mono text-xs text-mist">{friendlyTime(event.at)} · {eventLabel(event.kind)}</p>
            <p className="mt-1 text-sm">{event.message}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
