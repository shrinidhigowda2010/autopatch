import { AnimatePresence, motion } from "framer-motion";
import { useRef, useState } from "react";
import { api } from "../api";
import { streamEvents } from "../lib/sse";
import CountUp from "./CountUp";

type Outcome = { status: "ok" | "rejected" | "crashed" | "hung" | "accepted" | "skipped"; detail: string };

type AttackRow = {
  label: string;
  args: string[];
  origin: "rules" | "gemini";
  old: Outcome;
  new: Outcome;
  verdict: "blocked" | "still breaks" | "both fine";
};

export type AttackResult = {
  function: string;
  engine: string;
  total: number;
  old_failed: number;
  old_crashed: number;
  old_accepted_bad_input: number;
  new_survived: number;
  blocked: number;
  headline: string;
  cases: AttackRow[];
};

type Turn = { round: number; role: "fixer" | "breaker"; text: string; engine: string };
type Verdict = { verdict: "safe" | "needs_changes"; confidence: number; reason: string; engine: string };

const STATUS_STYLE: Record<Outcome["status"], string> = {
  ok: "text-fixed",
  rejected: "text-fixed",
  crashed: "text-bug",
  hung: "text-bug",
  accepted: "text-bug",
  skipped: "text-mist",
};

const STATUS_WORD: Record<Outcome["status"], string> = {
  ok: "handled",
  rejected: "refused safely",
  crashed: "crashed",
  hung: "hung",
  accepted: "accepted bad input",
  skipped: "skipped",
};

export default function ProofArena({ patchId }: { patchId: string }) {
  const [panel, setPanel] = useState<"none" | "attack" | "debate">("none");
  const [attack, setAttack] = useState<AttackResult | null>(null);

  return (
    <div className="mt-4 rounded-xl border border-line bg-cream/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 font-mono text-xs uppercase tracking-[0.15em] text-mist">Prove it</span>
        <button
          type="button"
          onClick={() => setPanel(panel === "attack" ? "none" : "attack")}
          className={panel === "attack" ? "btn-primary px-3 py-1.5 text-sm" : "btn-secondary px-3 py-1.5 text-sm"}
        >
          🛡 Break-It attack
        </button>
        <button
          type="button"
          onClick={() => setPanel(panel === "debate" ? "none" : "debate")}
          className={panel === "debate" ? "btn-primary px-3 py-1.5 text-sm" : "btn-secondary px-3 py-1.5 text-sm"}
        >
          ⚖️ AI Debate Room
        </button>
      </div>
      <AnimatePresence mode="wait">
        {panel === "attack" && (
          <motion.div key="attack" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <AttackPanel patchId={patchId} result={attack} onResult={setAttack} />
          </motion.div>
        )}
        {panel === "debate" && (
          <motion.div key="debate" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <DebatePanel patchId={patchId} attack={attack} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AttackPanel({
  patchId,
  result,
  onResult,
}: {
  patchId: string;
  result: AttackResult | null;
  onResult: (result: AttackResult) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function launch() {
    setBusy(true);
    setError("");
    try {
      onResult(await api<AttackResult>(`/api/patches/${patchId}/attack`, { method: "POST" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The attack could not run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3">
      <p className="text-sm text-mist">
        FixPilot throws 10–15 hostile inputs at the function (empty, None, negative, huge, unicode, wrong types) and
        runs the old and new code side by side in the sandbox.
      </p>
      <button type="button" onClick={() => void launch()} disabled={busy} className="btn-primary mt-3 px-4 py-2 text-sm">
        {busy ? "Attacking…" : result ? "Attack again" : "Launch attack"}
      </button>
      {error && <p className="mt-3 text-sm text-bug">{error}</p>}
      {busy && <AttackSkeleton />}
      {result && !busy && <Scoreboard result={result} />}
    </div>
  );
}

function AttackSkeleton() {
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      {[0, 1].map((index) => (
        <div key={index} className="h-24 animate-pulse rounded-xl border border-line bg-panel" />
      ))}
    </div>
  );
}

function Scoreboard({ result }: { result: AttackResult }) {
  const failedShare = result.total ? result.old_failed / result.total : 0;
  const survivedShare = result.total ? result.new_survived / result.total : 0;
  return (
    <div className="mt-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <ScoreCard
          title="Old code failed"
          value={result.old_failed}
          total={result.total}
          share={failedShare}
          tone="bg-bug"
          text="text-bug"
          note={`${result.old_crashed} crashed · ${result.old_accepted_bad_input} accepted bad input`}
        />
        <ScoreCard
          title="New code survived"
          value={result.new_survived}
          total={result.total}
          share={survivedShare}
          tone="bg-fixed"
          text="text-fixed"
          note="handled or refused safely"
        />
      </div>
      <p className="mt-3 font-mono text-xs text-mist">
        {result.function}() · {result.blocked} attack{result.blocked === 1 ? "" : "s"} blocked by the fix ·{" "}
        {result.engine === "gemini+rules" ? "inputs from Gemini + rules" : "rule-based inputs"}
      </p>
      <ul className="mt-3 divide-y divide-line overflow-hidden rounded-xl border border-line bg-panel">
        {result.cases.map((row, index) => (
          <motion.li
            key={`${row.label}-${index}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.08 * index }}
            className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-[1.4fr_1fr_1fr_auto] sm:items-center"
          >
            <span>
              <span className="font-medium">{row.label}</span>
              <code className="ml-2 font-mono text-xs text-mist">{row.args.join(", ") || "()"}</code>
            </span>
            <span className={STATUS_STYLE[row.old.status]} title={row.old.detail}>
              old: {STATUS_WORD[row.old.status]}
            </span>
            <span className={STATUS_STYLE[row.new.status]} title={row.new.detail}>
              new: {STATUS_WORD[row.new.status]}
            </span>
            <span className="text-right text-xs">
              {row.verdict === "blocked" ? "🛡 blocked" : row.verdict === "still breaks" ? "⚠️ still breaks" : "✓"}
            </span>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

function ScoreCard({
  title,
  value,
  total,
  share,
  tone,
  text,
  note,
}: {
  title: string;
  value: number;
  total: number;
  share: number;
  tone: string;
  text: string;
  note: string;
}) {
  return (
    <div className="card-3d p-4">
      <p className="font-mono text-xs uppercase tracking-[0.15em] text-mist">{title}</p>
      <p className={`mt-1 text-4xl font-semibold ${text}`}>
        <CountUp value={value} />
        <span className="text-xl text-mist">/{total}</span>
      </p>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-line">
        <motion.div
          className={`h-full ${tone}`}
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(share * 100)}%` }}
          transition={{ duration: 1.1, ease: "easeOut" }}
        />
      </div>
      <p className="mt-2 text-xs text-mist">{note}</p>
    </div>
  );
}

function DebatePanel({ patchId, attack }: { patchId: string; attack: AttackResult | null }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const abort = useRef<AbortController | null>(null);

  async function start() {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setTurns([]);
    setVerdict(null);
    setNotice("");
    setError("");
    setRunning(true);
    const summary = attack
      ? { headline: attack.headline, total: attack.total, new_survived: attack.new_survived }
      : null;
    try {
      await streamEvents<Record<string, unknown>>(
        `/api/patches/${patchId}/debate`,
        { attack: summary },
        (event) => {
          if (event.type === "turn") setTurns((prev) => [...prev, event as unknown as Turn]);
          else if (event.type === "verdict") setVerdict(event as unknown as Verdict);
          else if (event.type === "notice") setNotice(String(event.text || ""));
          else if (event.type === "error") setError(String(event.detail || "The debate stopped."));
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "The debate stopped.");
    } finally {
      setRunning(false);
    }
  }

  const nextRole = turns.length % 2 === 0 ? "breaker" : "fixer";

  return (
    <div className="mt-3">
      <p className="text-sm text-mist">
        Breaker attacks the fix with edge cases, Fixer defends it, three rounds, then the Judge rules.
        {attack ? " The Break-It scoreboard is shared as evidence." : ""}
      </p>
      <button type="button" onClick={() => void start()} disabled={running} className="btn-primary mt-3 px-4 py-2 text-sm">
        {running ? "Debating…" : turns.length ? "Run the debate again" : "Start the debate"}
      </button>
      {error && <p className="mt-3 text-sm text-bug">{error}</p>}
      {notice && <p className="mt-3 text-sm text-review">{notice}</p>}
      <div className="mt-4 space-y-3">
        {turns.map((turn, index) => (
          <DebateBubble key={index} turn={turn} />
        ))}
        {running && !verdict && <Typing role={turns.length >= 6 ? "judge" : nextRole} />}
      </div>
      {verdict && <VerdictCard verdict={verdict} />}
    </div>
  );
}

function Avatar({ role }: { role: "fixer" | "breaker" | "judge" }) {
  const style =
    role === "fixer"
      ? "bg-ink text-cream"
      : role === "breaker"
        ? "border-2 border-bug bg-cream text-bug"
        : "border-2 border-ink bg-panel text-ink";
  const letter = role === "fixer" ? "F" : role === "breaker" ? "B" : "J";
  return (
    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-semibold shadow-emboss ${style}`}>
      {letter}
    </span>
  );
}

function DebateBubble({ turn }: { turn: Turn }) {
  const fixer = turn.role === "fixer";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex items-start gap-3 ${fixer ? "flex-row-reverse text-right" : ""}`}
    >
      <Avatar role={turn.role} />
      <div className={`max-w-[80%] rounded-2xl border px-4 py-2 text-sm ${fixer ? "border-ink bg-panel" : "border-bug/40 bg-cream"}`}>
        <p className="font-mono text-[11px] uppercase tracking-[0.15em] text-mist">
          Round {turn.round} · {fixer ? "Fixer" : "Breaker"}
          {turn.engine === "rules" ? " · from test evidence" : ""}
        </p>
        <p className="mt-1 whitespace-pre-wrap text-left">{turn.text}</p>
      </div>
    </motion.div>
  );
}

function Typing({ role }: { role: "fixer" | "breaker" | "judge" }) {
  return (
    <div className={`flex items-center gap-3 ${role === "fixer" ? "flex-row-reverse" : ""}`}>
      <Avatar role={role} />
      <span className="animate-pulse text-sm text-mist">
        {role === "judge" ? "The Judge is deciding…" : role === "fixer" ? "Fixer is answering…" : "Breaker is looking for a hole…"}
      </span>
    </div>
  );
}

function VerdictCard({ verdict }: { verdict: Verdict }) {
  const safe = verdict.verdict === "safe";
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`card-3d mt-5 flex items-start gap-4 p-4 ${safe ? "border-fixed/50" : "border-review/60"}`}
    >
      <Avatar role="judge" />
      <div className="flex-1">
        <p className="font-mono text-xs uppercase tracking-[0.15em] text-mist">Judge's verdict</p>
        <p className={`mt-1 text-2xl font-semibold ${safe ? "text-fixed" : "text-review"}`}>
          {safe ? "Safe" : "Needs changes"} · <CountUp value={verdict.confidence} suffix="%" /> confident
        </p>
        <p className="mt-2 text-sm">{verdict.reason}</p>
      </div>
    </motion.div>
  );
}
