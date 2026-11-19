import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

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
        Every approve, reject, edit, skip, and auto-apply is stored against your Coder ID for this project.
      </p>
      {error && <p className="mt-4 text-bug">{error}</p>}
      <ol className="mt-6 space-y-3">
        {rows.length === 0 && <li className="text-mist">No decisions yet.</li>}
        {rows.map((row) => (
          <li key={row.id} className="rounded-lg border border-line bg-panel px-3 py-2">
            <p className="font-mono text-xs text-mist">
              {row.timestamp} · {row.decision} · {row.who}
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
