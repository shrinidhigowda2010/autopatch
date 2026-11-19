import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import DiffView from "../components/DiffView";
import { usePrefs } from "../components/Shell";
import type { Bug, Scan } from "../types";

type FixMode = "manual" | "ask" | "auto_safe";

interface Progress {
  total: number;
  approved: number;
  rejected: number;
  skipped: number;
  remaining: number;
  current: number;
  label: string;
  health?: { before: number; after: number };
}

interface VersionRow {
  version: number;
  label: string;
  at: string;
}

export default function Fix() {
  const { projectId = "" } = useParams();
  const { studentMode } = usePrefs();
  const [scan, setScan] = useState<Scan | null>(null);
  const [mode, setMode] = useState<FixMode>("ask");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<Progress | null>(null);
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [editing, setEditing] = useState(false);
  const [editCode, setEditCode] = useState("");
  const [rejectNote, setRejectNote] = useState("");
  const [askOpen, setAskOpen] = useState(false);
  const [askQuestion, setAskQuestion] = useState("");
  const [askAnswer, setAskAnswer] = useState("");
  const [alternative, setAlternative] = useState<{ explanation: string; after_code: string } | null>(null);
  const [preflight, setPreflight] = useState<{ title: string; file: string; confidence: number }[] | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const scans = await api<{ id: string }[]>(`/api/projects/${projectId}/scans`);
    if (!scans[0]) return;
    const next = await api<Scan & { fix_progress?: Progress }>(`/api/scans/${scans[0].id}`);
    setScan(next);
    const prog = await api<Progress>(`/api/scans/${scans[0].id}/fix-progress`);
    setProgress(prog);
    const vers = await api<{ versions: VersionRow[] }>(`/api/projects/${projectId}/versions`);
    setVersions(vers.versions);
    if (prog.remaining === 0 && prog.total > 0) {
      const done = await api<Record<string, unknown>>(`/api/scans/${scans[0].id}/summary`);
      setSummary(done);
    } else {
      setSummary(null);
    }
  }, [projectId]);

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [load]);

  const queue = useMemo(() => {
    const bugs = (scan?.bugs || []).filter((bug) => bug.suggested_patch.length > 0);
    if (mode === "manual") return bugs;
    return bugs.filter((bug) => bug.suggested_patch[0]?.status === "proposed");
  }, [scan, mode]);

  const current = mode === "manual" ? null : queue[0] || null;
  const currentPatch = current?.suggested_patch[0];

  useEffect(() => {
    if (currentPatch) {
      setEditCode(currentPatch.after_code);
      setEditing(false);
      setRejectNote("");
      setAskOpen(false);
      setAskAnswer("");
      setAlternative(null);
    }
  }, [currentPatch?.id]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (mode === "manual" || !currentPatch || editing || askOpen) return;
      const tag = (event.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const key = event.key.toLowerCase();
      if (key === "a") void act("approve");
      if (key === "r") void act("reject");
      if (key === "s") void act("skip");
      if (key === "e") {
        setEditing(true);
        setEditCode(currentPatch.after_code);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function act(kind: "approve" | "reject" | "skip" | "edit") {
    if (!currentPatch) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (kind === "approve") {
        const result = await api<{ status: string; rolled_back?: boolean; message?: string }>(
          `/api/patches/${currentPatch.id}/approve`,
          { method: "POST" },
        );
        setMessage(
          result.rolled_back
            ? result.message || "Auto-rolled back because tests failed."
            : "Approved and applied. Tests re-checked.",
        );
      } else if (kind === "reject") {
        const result = await api<{
          status: string;
          alternative?: { available: boolean; alternative?: { explanation: string; after_code: string } };
        }>(`/api/patches/${currentPatch.id}/reject`, {
          method: "POST",
          body: JSON.stringify({ note: rejectNote, try_another: Boolean(rejectNote.trim()) }),
        });
        setMessage("Rejected. The workspace was left alone.");
        const alt = result.alternative?.alternative;
        if (alt) setAlternative(alt);
      } else if (kind === "skip") {
        await api(`/api/patches/${currentPatch.id}/skip`, { method: "POST" });
        setMessage("Skipped for now.");
      } else if (kind === "edit") {
        await api(`/api/patches/${currentPatch.id}/edit`, {
          method: "POST",
          body: JSON.stringify({ edited_code: editCode, note: "Edited before applying", verify_tests: true }),
        });
        setMessage("Edited fix applied.");
        setEditing(false);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the decision.");
    } finally {
      setBusy(false);
    }
  }

  async function decideManual(patchId: string, action: "accept" | "reject") {
    setError("");
    try {
      await api(`/api/patches/${patchId}/decision`, { method: "POST", body: JSON.stringify({ action }) });
      setMessage(action === "accept" ? "Patch applied to the workspace." : "Patch rejected. The file was left alone.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the decision.");
    }
  }

  async function openPreflight() {
    if (!scan) return;
    setError("");
    try {
      const result = await api<{
        planned: { title: string; file: string; confidence: number }[];
      }>(`/api/scans/${scan.id}/apply-safe`, {
        method: "POST",
        body: JSON.stringify({ dry_run: true, mode: mode === "auto_safe" ? "auto_safe" : "safe" }),
      });
      setPreflight(result.planned);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not prepare safe fixes.");
    }
  }

  async function confirmSafe() {
    if (!scan) return;
    setPreflight(null);
    setBusy(true);
    try {
      const result = await api<{ applied: { title: string }[]; skipped: { title: string }[] }>(
        `/api/scans/${scan.id}/apply-safe`,
        {
          method: "POST",
          body: JSON.stringify({ dry_run: false, mode: mode === "auto_safe" ? "auto_safe" : "safe", confirm: true }),
        },
      );
      setMessage(`Applied ${result.applied.length} safe fix(es). Skipped ${result.skipped.length}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nothing was applied.");
    } finally {
      setBusy(false);
    }
  }

  async function undoLast() {
    setBusy(true);
    try {
      const result = await api<{ message: string }>(`/api/projects/${projectId}/rollback-last`, { method: "POST" });
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Undo failed.");
    } finally {
      setBusy(false);
    }
  }

  async function rollbackEverything() {
    setBusy(true);
    try {
      const result = await api<{ message: string }>(`/api/projects/${projectId}/rollback-all`, { method: "POST" });
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed.");
    } finally {
      setBusy(false);
    }
  }

  async function askAi() {
    if (!currentPatch || !askQuestion.trim()) return;
    setBusy(true);
    try {
      const result = await api<{ answer: string }>(`/api/patches/${currentPatch.id}/ask-ai`, {
        method: "POST",
        body: JSON.stringify({ question: askQuestion }),
      });
      setAskAnswer(result.answer);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ask AI failed.");
    } finally {
      setBusy(false);
    }
  }

  async function tryAlternative() {
    if (!alternative?.after_code || !currentPatch) return;
    setEditCode(alternative.after_code);
    setEditing(true);
    setMessage("Loaded alternative into the editor. Review, then apply.");
  }

  const pct = progress && progress.total ? Math.round(((progress.approved + progress.rejected + progress.skipped) / progress.total) * 100) : 0;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Fix</h1>
          <p className="mt-2 max-w-2xl text-mist">
            Auto-Correct Mode walks through each fix and asks before changing anything. The original upload stays
            untouched — only the working copy is patched.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void openPreflight()}
            className="btn-secondary disabled:opacity-60"
            disabled={busy}
          >
            Apply all safe fixes
          </button>
          <Link to={`/p/${projectId}/decisions`} className="rounded-lg border border-line px-4 py-2 text-sm">
            Decision Log
          </Link>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {(
          [
            ["manual", "Manual"],
            ["ask", "Ask Every Fix"],
            ["auto_safe", "Auto for Safe Fixes"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setMode(value)}
            className={`rounded-2xl px-3 py-1.5 text-sm ${mode === value ? "bg-ink text-cream shadow-emboss" : "border border-line"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="mt-2 text-sm text-mist">
        {mode === "ask" && "Default: one permission card at a time. Shortcuts: A approve · R reject · S skip · E edit."}
        {mode === "auto_safe" && "Low-risk fixes with confidence ≥ 90% and passing tests can auto-apply; everything else still asks."}
        {mode === "manual" && "Classic list of Accept / Reject for every proposed patch."}
      </p>

      {progress && progress.total > 0 && (
        <div className="mt-5 rounded-xl border border-line bg-panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="font-mono text-ink">{progress.label}</span>
            <span className="text-mist">
              ✓ {progress.approved} · ✕ {progress.rejected} · ⏭ {progress.skipped}
            </span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-line">
            <div className="h-full bg-ink transition-all" style={{ width: `${pct}%` }} />
          </div>
          {progress.health && (
            <p className="mt-2 text-sm text-mist">
              Health score {progress.health.before} → {progress.health.after}
            </p>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        <button type="button" onClick={() => void undoLast()} disabled={busy} className="rounded-lg border border-line px-3 py-1.5">
          Undo last fix
        </button>
        <button type="button" onClick={() => void rollbackEverything()} disabled={busy} className="rounded-lg border border-line px-3 py-1.5">
          Rollback all
        </button>
      </div>

      {versions.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <p className="mb-2 font-mono text-xs uppercase tracking-[0.2em] text-mist">Version timeline</p>
          <div className="flex gap-2">
            {versions.map((row) => (
              <div key={row.version} className="min-w-[140px] rounded-lg border border-line bg-panel px-3 py-2 text-xs">
                <p className="font-mono text-ink">v{row.version}</p>
                <p className="mt-1 text-mist">{row.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {message && <p className="mt-4 text-fixed">{message}</p>}
      {error && <p className="mt-4 text-bug">{error}</p>}

      {summary && (
        <section className="mt-6 rounded-xl border border-fixed/30 bg-panel p-5">
          <h2 className="text-xl font-semibold">Repair summary</h2>
          <p className="mt-2 text-mist">Walkthrough complete for this scan.</p>
          <ul className="mt-3 space-y-1 text-sm">
            <li>Bugs fixed: {(summary.progress as Progress)?.approved ?? 0}</li>
            <li>
              Health: {(summary.health as { before: number; after: number })?.before} →{" "}
              {(summary.health as { before: number; after: number })?.after}
            </li>
          </ul>
          <a
            className="mt-4 inline-block btn-primary"
            href={`/api/projects/${projectId}/export/zip`}
          >
            Download fixed zip
          </a>
        </section>
      )}

      {mode !== "manual" && current && currentPatch && (
        <PermissionCard
          projectId={projectId}
          bug={current}
          studentMode={studentMode}
          editing={editing}
          editCode={editCode}
          setEditCode={setEditCode}
          setEditing={setEditing}
          rejectNote={rejectNote}
          setRejectNote={setRejectNote}
          askOpen={askOpen}
          setAskOpen={setAskOpen}
          askQuestion={askQuestion}
          setAskQuestion={setAskQuestion}
          askAnswer={askAnswer}
          alternative={alternative}
          busy={busy}
          onApprove={() => void act("approve")}
          onReject={() => void act("reject")}
          onSkip={() => void act("skip")}
          onEdit={() => void act("edit")}
          onAsk={() => void askAi()}
          onTryAlternative={() => void tryAlternative()}
        />
      )}

      {mode !== "manual" && !current && !summary && (
        <p className="mt-6 text-mist">No proposed patches left. Run a scan, or switch to Manual to review history.</p>
      )}

      {mode === "manual" && (
        <div className="mt-6 space-y-6">
          {queue.length === 0 && <p className="text-mist">No patches yet. Run a scan first.</p>}
          {queue.map((bug: Bug) => {
            const patch = bug.suggested_patch[0];
            return (
              <section key={bug.id} className="rounded-xl border border-line bg-panel p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link to={`/p/${projectId}/explain/${bug.id}`} className="font-medium hover:underline">
                    {bug.bug_details.title}
                  </Link>
                  <span className="font-mono text-xs text-mist">{patch.status}</span>
                </div>
                <div className="mt-3">
                  <DiffView before={patch.before_code} after={patch.after_code} diff={patch.diff} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {patch.status === "proposed" && (
                    <>
                      <button
                        onClick={() => void decideManual(patch.id, "accept")}
                        className="btn-primary px-3 py-1.5 text-sm"
                      >
                        Accept
                      </button>
                      <button
                        onClick={() => void decideManual(patch.id, "reject")}
                        className="rounded-lg border border-line px-3 py-1.5 text-sm"
                      >
                        Reject
                      </button>
                    </>
                  )}
                  <Link
                    to={`/p/${projectId}/assistant?bug=${bug.id}`}
                    className="rounded-lg border border-line px-3 py-1.5 text-sm"
                  >
                    Discuss with Assistant
                  </Link>
                </div>
              </section>
            );
          })}
        </div>
      )}

      {preflight && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[80vh] w-full max-w-lg overflow-auto rounded-xl border border-line bg-panel p-5">
            <h2 className="text-xl font-semibold">Confirm safe fixes</h2>
            <p className="mt-2 text-sm text-mist">These patches will be written to the working copy (not the original upload):</p>
            <ul className="mt-4 space-y-2 text-sm">
              {preflight.length === 0 && <li className="text-mist">Nothing qualifies as safe right now.</li>}
              {preflight.map((item) => (
                <li key={item.title + item.file} className="rounded-lg border border-line px-3 py-2">
                  <p className="font-medium">{item.title}</p>
                  <p className="font-mono text-xs text-mist">
                    {item.file} · {(item.confidence * 100).toFixed(0)}%
                  </p>
                </li>
              ))}
            </ul>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                disabled={busy || preflight.length === 0}
                onClick={() => void confirmSafe()}
                className="btn-primary disabled:opacity-60"
              >
                Apply listed fixes
              </button>
              <button type="button" onClick={() => setPreflight(null)} className="rounded-lg border border-line px-4 py-2">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PermissionCard({
  projectId,
  bug,
  studentMode,
  editing,
  editCode,
  setEditCode,
  setEditing,
  rejectNote,
  setRejectNote,
  askOpen,
  setAskOpen,
  askQuestion,
  setAskQuestion,
  askAnswer,
  alternative,
  busy,
  onApprove,
  onReject,
  onSkip,
  onEdit,
  onAsk,
  onTryAlternative,
}: {
  projectId: string;
  bug: Bug;
  studentMode: boolean;
  editing: boolean;
  editCode: string;
  setEditCode: (v: string) => void;
  setEditing: (v: boolean) => void;
  rejectNote: string;
  setRejectNote: (v: string) => void;
  askOpen: boolean;
  setAskOpen: (v: boolean) => void;
  askQuestion: string;
  setAskQuestion: (v: string) => void;
  askAnswer: string;
  alternative: { explanation: string; after_code: string } | null;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onSkip: () => void;
  onEdit: () => void;
  onAsk: () => void;
  onTryAlternative: () => void;
}) {
  const patch = bug.suggested_patch[0];
  const risk = bug.risk_level || "review carefully";
  const why = studentMode ? bug.student_explanation || bug.root_cause : bug.root_cause;
  const what =
    studentMode
      ? "This change replaces the buggy lines with a safer version so the bad input cannot break the program."
      : `The patch rewrites ${bug.bug_details.file} around line ${bug.bug_details.line} to address “${bug.bug_details.title}”.`;

  const riskClass =
    risk === "safe" ? "text-fixed border-fixed/30" : risk === "risky" ? "text-bug border-bug/30" : "text-amber border-amber/40";

  const tests = bug.test_results?.[bug.test_results.length - 1];
  const beforeFail = tests?.for_this_bug?.some((item) => item.passed === false);
  const afterPass = tests?.for_this_bug?.some((item) => item.passed === true);

  return (
    <section className="mt-6 rounded-xl border border-line bg-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-mist">
            {bug.bug_details.file}:{bug.bug_details.line}
          </p>
          <h2 className="mt-1 text-xl font-semibold">{bug.bug_details.title}</h2>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-md border border-line px-2 py-1 uppercase">{bug.severity_and_confidence.severity}</span>
          <span className="rounded-md border border-line px-2 py-1">
            {(bug.severity_and_confidence.confidence * 100).toFixed(0)}% confidence
          </span>
          <span className={`rounded-md border px-2 py-1 capitalize ${riskClass}`}>{risk}</span>
        </div>
      </div>

      <div className="mt-4">
        <DiffView before={patch.before_code} after={editing ? editCode : patch.after_code} diff={patch.diff} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-line bg-cream p-3">
          <p className="font-mono text-xs uppercase tracking-[0.15em] text-mist">Why this is a bug</p>
          <p className="mt-2 text-sm">{why}</p>
        </div>
        <div className="rounded-lg border border-line bg-cream p-3">
          <p className="font-mono text-xs uppercase tracking-[0.15em] text-mist">What the fix does</p>
          <p className="mt-2 text-sm">{what}</p>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-line px-3 py-2 text-sm">
        <span className="text-mist">Test proof: </span>
        <span className={beforeFail ? "text-bug" : "text-mist"}>before {beforeFail ? "failing" : "unknown"}</span>
        <span className="text-mist"> → </span>
        <span className={afterPass ? "text-fixed" : "text-mist"}>after {afterPass ? "passing" : "run tests to prove"}</span>
      </div>

      {editing && (
        <div className="mt-4">
          <p className="mb-2 text-sm text-mist">Edit the after-code, then apply.</p>
          <textarea
            value={editCode}
            onChange={(e) => setEditCode(e.target.value)}
            rows={10}
            className="w-full rounded-lg border border-line bg-cream p-3 font-mono text-xs"
          />
        </div>
      )}

      <div className="mt-4">
        <label className="block text-sm text-mist">
          Reject reason (optional — helps regenerate an alternative)
          <input
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
            className="mt-1 w-full rounded-lg border border-line bg-cream px-3 py-2 text-sm"
            placeholder="e.g. Prefer early return instead of nested if"
          />
        </label>
      </div>

      {alternative && (
        <div className="mt-4 rounded-lg border border-line bg-panel p-3 text-sm">
          <p className="font-medium">Alternative from AI</p>
          <p className="mt-1 text-mist">{alternative.explanation}</p>
          <button type="button" onClick={onTryAlternative} className="mt-2 rounded-lg border border-line px-3 py-1.5 text-mist">
            Try another fix
          </button>
        </div>
      )}

      {askOpen && (
        <div className="mt-4 rounded-lg border border-line p-3">
          <input
            value={askQuestion}
            onChange={(e) => setAskQuestion(e.target.value)}
            placeholder="Ask why this fix is safe…"
            className="w-full rounded-lg border border-line bg-cream px-3 py-2 text-sm"
          />
          <button type="button" onClick={onAsk} disabled={busy} className="mt-2 rounded-lg border border-line px-3 py-1.5 text-sm">
            Send
          </button>
          {askAnswer && <p className="mt-3 whitespace-pre-wrap text-sm text-mist">{askAnswer}</p>}
        </div>
      )}

      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={onApprove} className="btn-primary px-3 py-1.5 text-sm">
          ✅ Approve
        </button>
        <button type="button" disabled={busy} onClick={onReject} className="rounded-lg border border-line px-3 py-1.5 text-sm">
          ❌ Reject
        </button>
        {!editing ? (
          <button type="button" disabled={busy} onClick={() => setEditing(true)} className="rounded-lg border border-line px-3 py-1.5 text-sm">
            ✏️ Edit before applying
          </button>
        ) : (
          <button type="button" disabled={busy} onClick={onEdit} className="btn-secondary px-3 py-1.5 text-sm">
            Apply edited fix
          </button>
        )}
        <button type="button" disabled={busy} onClick={onSkip} className="rounded-lg border border-line px-3 py-1.5 text-sm">
          ⏭️ Skip for now
        </button>
        <button type="button" disabled={busy} onClick={() => setAskOpen(!askOpen)} className="rounded-lg border border-line px-3 py-1.5 text-sm">
          💬 Ask AI why
        </button>
        <Link
          to={`/p/${projectId}/assistant?bug=${bug.id}`}
          className="rounded-lg border border-line px-3 py-1.5 text-sm"
        >
          Discuss with Assistant
        </Link>
      </div>
    </section>
  );
}
