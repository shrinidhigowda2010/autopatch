import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth, type AuthUser } from "../auth";

export default function Profile() {
  const { user, refresh, isGuest } = useAuth();
  const [copied, setCopied] = useState(false);
  const [profile, setProfile] = useState<AuthUser | null>(user);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isGuest || !user) return;
    api<AuthUser>("/api/auth/me")
      .then((me) => {
        setProfile(me);
        void refresh();
      })
      .catch((err: Error) => setError(err.message));
  }, [user, isGuest, refresh]);

  if (isGuest || !user) {
    return (
      <div className="mx-auto max-w-lg">
        <h1 className="text-3xl font-semibold">Profile</h1>
        <p className="mt-2 text-mist">You are browsing without an account. Sign in to keep a Coder ID and personal history.</p>
        <Link to="/login" className="btn-primary mt-4 inline-block">
          Sign in
        </Link>
      </div>
    );
  }

  const stats = profile?.stats || user.stats;

  async function copyCoderId() {
    if (!user) return;
    try {
      await navigator.clipboard.writeText(user.coder_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">Profile</h1>
      <p className="mt-2 text-mist">Your Coder ID links every scan and patch decision to you.</p>
      {error && <p className="mt-4 text-bug">{error}</p>}

      <div className="mt-6 rounded-xl border border-lime/40 bg-panel p-5">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-mist">Coder ID card</p>
        <p className="mt-3 text-2xl font-semibold">{user.full_name}</p>
        <p className="mt-1 font-mono text-xl text-ink">{user.coder_id}</p>
        <p className="mt-2 text-sm text-mist">
          {user.email} · {user.role}
        </p>
        <button
          type="button"
          onClick={() => void copyCoderId()}
          className="mt-4 rounded-lg border border-line px-3 py-1.5 text-sm"
        >
          {copied ? "Copied!" : "Copy Coder ID"}
        </button>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Total scans", stats?.total_scans ?? 0],
          ["Bugs found", stats?.bugs_found ?? 0],
          ["Patches accepted", stats?.patches_accepted ?? 0],
          ["Patches rejected", stats?.patches_rejected ?? 0],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded-xl border border-line bg-panel p-4">
            <p className="text-sm text-mist">{label}</p>
            <p className="mt-2 text-3xl font-semibold">{value as number}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-mist">
        Member since {new Date(stats?.member_since || user.created_at).toLocaleDateString()}
      </p>
      <Link to="/my-history" className="mt-4 inline-block font-medium text-ink underline-offset-2 hover:underline">
        View my history →
      </Link>
    </div>
  );
}
