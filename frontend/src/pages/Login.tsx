import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth, type AuthUser } from "../auth";
import AiStatus from "../components/AiStatus";
import Logo from "../components/Logo";

export default function Login() {
  const { setSession, continueAsGuest } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const body = await api<{ access_token: string; user: AuthUser }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ identifier, password }),
      });
      setSession(body.access_token, body.user);
      navigate(params.get("next") || "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  function guest() {
    continueAsGuest();
    navigate("/");
  }

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center py-10">
      <Logo className="h-11 w-auto" />
      <p className="mt-4 font-mono text-xs uppercase tracking-[0.2em] text-mist">Find it. Fix it. Prove it.</p>
      <h1 className="mt-2 text-3xl font-semibold text-ink">Sign in to FixPilot</h1>
      <p className="mt-2 text-mist">Welcome back. Use your email or Coder ID. Just looking around? You can explore without an account.</p>
      <form onSubmit={onSubmit} className="card-3d mt-6 space-y-4 p-6">
        <label className="block text-sm">
          <span className="text-mist">Email or Coder ID</span>
          <input
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            required
            autoComplete="username"
            className="mt-1 w-full rounded-2xl border border-line bg-cream px-3 py-2.5 text-ink"
            placeholder="you@college.edu or FP-CODER-XXXXX"
          />
        </label>
        <label className="block text-sm">
          <span className="text-mist">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            className="mt-1 w-full rounded-2xl border border-line bg-cream px-3 py-2.5 text-ink"
          />
        </label>
        {error && <p className="text-sm text-bug">{error}</p>}
        <button type="submit" disabled={busy} className="btn-primary w-full disabled:opacity-60">
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <button type="button" onClick={guest} className="btn-secondary w-full">
          Explore without an account
        </button>
      </form>
      <p className="mt-4 text-sm text-mist">
        New here?{" "}
        <Link to="/register" className="font-medium text-ink underline-offset-2 hover:underline">
          Create an account
        </Link>
      </p>
      <div className="mt-8">
        <AiStatus />
      </div>
    </div>
  );
}
