import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { EmptyState } from "../components/Skeleton";
import { eventLabel, friendlyTime } from "../lib/format";

interface DecisionRow {
  id: string;
  fix_id: string;
  decision: string;
  note: string;
  who: string;
  coder_id: string | null;
  file: string | null;
  timestamp: string;
}

export default function DecisionLog() {
  const { projectId = "" } = useParams();
  const [rows, setRows] = useState<DecisionRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ decisions: DecisionRow[] }>(`/api/projects/${projectId}/decision-log`)
      .then((body) => setRows(body.decisions))
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">Decision Log</h1>
      <p className="mt-2 text-mist">
        Every fix you approve, reject, edit, skip or roll back is written down here, with who did it and when.
      </p>
      {error && <p className="mt-4 text-bug">{error}</p>}
      <ol className="mt-6 space-y-3">
        {rows.length === 0 && !error && (
          <li>
            <EmptyState title="No decisions yet">
              Open the <Link to={`/p/${projectId}/fix`} className="font-medium text-ink underline">Fix</Link> step and approve or
              reject a fix. Each choice shows up here.
            </EmptyState>
          </li>
        )}
        {rows.map((row) => (
          <li key={row.id} className="rounded-lg border border-line bg-panel px-3 py-2">
            <p className="font-mono text-xs text-mist">
              {friendlyTime(row.timestamp)} · {eventLabel(row.decision)} · {row.who}
              {row.coder_id ? ` (${row.coder_id})` : ""}
            </p>
            <p className="mt-1 text-sm">
              Fix {row.fix_id}
              {row.file ? ` · ${row.file}` : ""}
            </p>
            {row.note && <p className="mt-1 text-sm text-mist">{row.note}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}
