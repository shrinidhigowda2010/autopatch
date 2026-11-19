import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth, type AuthUser } from "../auth";
import Logo from "../components/Logo";

export default function Register() {
  const { setSession } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("student");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [welcome, setWelcome] = useState<{ coderId: string } | null>(null);
  const [copied, setCopied] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      const body = await api<{ access_token: string; coder_id: string; user: AuthUser }>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ full_name: fullName, email, password, role }),
      });
      setSession(body.access_token, body.user);
      setWelcome({ coderId: body.coder_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not register.");
    } finally {
      setBusy(false);
    }
  }

  async function copyCoderId() {
    if (!welcome) return;
    try {
      await navigator.clipboard.writeText(welcome.coderId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  if (welcome) {
    return (
      <div className="mx-auto flex min-h-[80vh] max-w-lg flex-col justify-center py-10">
        <div className="card-3d p-8">
          <Logo className="h-10 w-auto" />
          <h1 className="mt-6 text-3xl font-semibold">Welcome to FixPilot</h1>
          <p className="mt-2 text-mist">
            Save your Coder ID — you can sign in with it or your email. Scans and patch decisions stay linked to it.
          </p>
          <div className="mt-6 rounded-2xl border border-line bg-cream px-4 py-5 text-center shadow-emboss">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-mist">Coder ID</p>
            <p className="mt-2 font-mono text-2xl font-semibold text-ink">{welcome.coderId}</p>
            <button type="button" onClick={() => void copyCoderId()} className="btn-secondary mt-4">
              {copied ? "Copied!" : "Copy Coder ID"}
            </button>
          </div>
          <button type="button" onClick={() => navigate("/")} className="btn-primary mt-6 w-full">
            Go to FixPilot
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center py-10">
      <Logo className="h-11 w-auto" />
      <h1 className="mt-6 text-3xl font-semibold">Create your FixPilot account</h1>
      <p className="mt-2 text-mist">You will receive a unique Coder ID after signing up.</p>
      <form onSubmit={onSubmit} className="card-3d mt-6 space-y-4 p-6">
        <label className="block text-sm">
          <span className="text-mist">Full name</span>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            className="mt-1 w-full rounded-2xl border border-line bg-cream px-3 py-2.5"
          />
        </label>
        <label className="block text-sm">
          <span className="text-mist">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mt-1 w-full rounded-2xl border border-line bg-cream px-3 py-2.5"
          />
        </label>
        <label className="block text-sm">
          <span className="text-mist">Password (min 8 characters)</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            className="mt-1 w-full rounded-2xl border border-line bg-cream px-3 py-2.5"
          />
        </label>
        <label className="block text-sm">
          <span className="text-mist">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 w-full rounded-2xl border border-line bg-cream px-3 py-2.5"
          >
            <option value="student">Student</option>
            <option value="developer">Developer</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        {error && <p className="text-sm text-bug">{error}</p>}
        <button type="submit" disabled={busy} className="btn-primary w-full disabled:opacity-60">
          {busy ? "Creating…" : "Register"}
        </button>
      </form>
      <p className="mt-4 text-sm text-mist">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-ink underline-offset-2 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
