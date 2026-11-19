import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

interface HistoryRow {
  id: string;
  name: string;
  source_type: string;
  created_at: string;
  is_guest: boolean;
}

export default function MyHistory() {
  const { user, isGuest } = useAuth();
  const [projects, setProjects] = useState<HistoryRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    api<{ projects: HistoryRow[] }>("/api/auth/history")
      .then((body) => setProjects(body.projects))
      .catch((err: Error) => setError(err.message));
  }, [user]);

  if (isGuest || !user) {
    return (
      <div className="mx-auto max-w-lg">
        <h1 className="text-3xl font-semibold">My History</h1>
        <p className="mt-2 text-mist">Sign in to see projects linked to your Coder ID.</p>
        <Link to="/login" className="btn-primary mt-4 inline-block">
          Sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">My History</h1>
      <p className="mt-2 text-mist">Projects owned by {user.coder_id}. Sessions without an account are not listed here.</p>
      {error && <p className="mt-4 text-bug">{error}</p>}
      <ul className="mt-6 space-y-3">
        {projects.length === 0 && <li className="text-mist">No saved projects yet. Upload or open a sample while signed in.</li>}
        {projects.map((row) => (
          <li key={row.id} className="rounded-xl border border-line bg-panel px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-medium">{row.name}</p>
                <p className="font-mono text-xs text-mist">
                  {row.id} · {row.source_type} · {new Date(row.created_at).toLocaleString()}
                </p>
              </div>
              <Link to={`/p/${row.id}/dashboard`} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:border-lime/50">
                Open
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
