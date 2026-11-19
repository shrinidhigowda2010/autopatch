import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Confetti from "../components/Confetti";
import Logo from "../components/Logo";
import { streamEvents } from "../lib/sse";

type StageId = "bug_found" | "fixed" | "verified";

type RaceEvent = {
  type: "stage" | "finish" | "error" | "done";
  stage?: "scanning" | StageId;
  t?: number;
  project_id?: string;
  bug?: { id: string; title: string; line: number; severity: string; file: string };
  count?: number;
  diff?: string;
  passed?: boolean;
  failed_before?: boolean;
  method?: string;
  summary?: string;
  result?: "verified" | "unverified" | "no_fix" | "clean";
  message?: string;
  detail?: string;
};

const STAGES: { id: StageId; label: string }[] = [
  { id: "bug_found", label: "Bug found" },
  { id: "fixed", label: "Fixed" },
  { id: "verified", label: "Verified" },
];

const EXAMPLES: { label: string; code: string }[] = [
  {
    label: "Average of an empty list",
    code: "def average(values):\n    return sum(values) / len(values)\n\n\nprint(average([72, 85, 90]))\n",
  },
  {
    label: "Marks out of range",
    code:
      "def calculate(marks):\n    total = 0\n    for mark in marks:\n        total = total + mark\n" +
      "    percentage = total / len(marks)\n    return {\"total\": total, \"percentage\": percentage}\n\n\n" +
      "print(calculate([70, 80, 90]))\n",
  },
  {
    label: "Divide by a parameter",
    code: "def ratio(part, whole):\n    return part / whole\n\n\nprint(ratio(3, 4))\n",
  },
];

function formatClock(seconds: number): string {
  return seconds.toFixed(1).padStart(4, "0");
}

export default function Race() {
  const [code, setCode] = useState(EXAMPLES[0].code);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [times, setTimes] = useState<Partial<Record<StageId, number>>>({});
  const [bug, setBug] = useState<RaceEvent["bug"] | null>(null);
  const [diff, setDiff] = useState("");
  const [finish, setFinish] = useState<RaceEvent | null>(null);
  const [projectId, setProjectId] = useState("");
  const [error, setError] = useState("");
  const [confetti, setConfetti] = useState(0);
  const startedAt = useRef(0);
  const frame = useRef(0);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  function tick() {
    setElapsed((performance.now() - startedAt.current) / 1000);
    frame.current = requestAnimationFrame(tick);
  }

  function stopClock(serverTime?: number) {
    cancelAnimationFrame(frame.current);
    if (serverTime !== undefined) setElapsed(serverTime);
  }

  async function go() {
    if (!code.trim() || running) return;
    setRunning(true);
    setTimes({});
    setBug(null);
    setDiff("");
    setFinish(null);
    setProjectId("");
    setError("");
    setElapsed(0);
    startedAt.current = performance.now();
    frame.current = requestAnimationFrame(tick);
    try {
      await streamEvents<RaceEvent>("/api/race", { code }, (event) => {
        if (event.type === "stage") {
          if (event.project_id) setProjectId(event.project_id);
          if (event.stage && event.stage !== "scanning" && event.t !== undefined) {
            setTimes((prev) => ({ ...prev, [event.stage as StageId]: event.t }));
          }
          if (event.bug) setBug(event.bug);
          if (event.diff) setDiff(event.diff);
        } else if (event.type === "finish") {
          stopClock(event.t);
          setFinish(event);
          if (event.result === "verified") setConfetti((value) => value + 1);
        } else if (event.type === "error") {
          setError(event.detail || "The race stopped.");
        }
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The race stopped.");
    } finally {
      stopClock();
      setRunning(false);
    }
  }

  const done = finish !== null;
  const won = finish?.result === "verified";

  return (
    <div className="min-h-screen bg-cream text-ink">
      <Confetti fire={confetti} />
      <header className="flex items-center justify-between px-6 py-4">
        <Link to="/" aria-label="FixPilot home">
          <Logo className="h-9 w-auto" />
        </Link>
        <p className="hidden font-mono text-xs uppercase tracking-[0.25em] text-mist sm:block">Live Repair Race</p>
        <Link to="/upload" className="text-sm underline">
          Exit
        </Link>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-16">
        <section className="text-center">
          <motion.p
            key={done ? "done" : "clock"}
            initial={{ scale: 0.98 }}
            animate={{ scale: 1 }}
            className={`font-mono text-[18vw] font-semibold leading-none tracking-tight md:text-[10rem] ${
              won ? "text-fixed" : finish && !won ? "text-review" : "text-ink"
            }`}
            aria-live="polite"
          >
            {formatClock(elapsed)}
            <span className="text-[6vw] md:text-5xl">s</span>
          </motion.p>
          <div className="mx-auto mt-6 grid max-w-3xl grid-cols-3 gap-3">
            {STAGES.map((stage, index) => {
              const time = times[stage.id];
              const reached = time !== undefined;
              const failed = stage.id === "verified" && reached && finish?.result === "unverified";
              return (
                <motion.div
                  key={stage.id}
                  animate={reached ? { y: [-4, 0], scale: [1.04, 1] } : {}}
                  className={`rounded-2xl border px-3 py-4 transition ${
                    reached
                      ? failed
                        ? "border-review bg-panel"
                        : "border-ink bg-ink text-cream shadow-lift"
                      : "border-line bg-panel text-mist"
                  }`}
                >
                  <p className="font-mono text-xs uppercase tracking-[0.2em] opacity-90">Stage {index + 1}</p>
                  <p className="mt-1 text-lg font-semibold">
                    {stage.label} {reached && (failed ? "✗" : "✓")}
                  </p>
                  <p className="mt-1 font-mono text-sm">{reached ? `${time!.toFixed(1)}s` : running ? "…" : "—"}</p>
                </motion.div>
              );
            })}
          </div>
          <AnimatePresence>
            {finish && (
              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={`mx-auto mt-6 max-w-2xl text-lg ${won ? "font-semibold" : ""}`}
              >
                {won ? `Bug found, fixed and verified in ${finish.t?.toFixed(1)} seconds. ` : ""}
                {finish.message}
              </motion.p>
            )}
          </AnimatePresence>
          {!running && !done && (
            <p className="mx-auto mt-6 max-w-2xl text-mist">
              Pick an example or paste your own code, then press Start. FixPilot scans it, writes a fix and runs tests on the old
              and new code while the clock runs. Every second is real work, not an animation.
            </p>
          )}
          {error && <p className="mt-6 text-bug">{error}</p>}
        </section>

        <section className="mt-10 grid gap-6 lg:grid-cols-2">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">Paste buggy code</h2>
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <button
                    key={example.label}
                    type="button"
                    disabled={running}
                    onClick={() => setCode(example.code)}
                    className="rounded-full border border-line bg-panel px-3 py-1 text-xs hover:border-ink"
                  >
                    {example.label}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              value={code}
              onChange={(event) => setCode(event.target.value)}
              spellCheck={false}
              aria-label="Code to race"
              rows={14}
              disabled={running}
              className="mt-3 w-full rounded-2xl border border-line bg-panel p-4 font-mono text-sm leading-relaxed"
            />
            <button
              type="button"
              onClick={() => void go()}
              disabled={running || !code.trim()}
              className="btn-primary mt-3 w-full py-3 text-lg"
            >
              {running ? "Racing…" : done ? "Race again" : "Start the race"}
            </button>
          </div>
          <div className="space-y-4">
            <div className="card-3d p-4">
              <p className="font-mono text-xs uppercase tracking-[0.15em] text-mist">The bug</p>
              {bug ? (
                <>
                  <p className="mt-1 text-lg font-semibold">{bug.title}</p>
                  <p className="font-mono text-xs text-mist">
                    {bug.file}:{bug.line} · {bug.severity}
                  </p>
                </>
              ) : (
                <p className="mt-1 text-mist">{running ? "Reading your code and looking for bugs…" : "Paste code or pick an example to start."}</p>
              )}
            </div>
            <div className="card-3d p-4">
              <p className="font-mono text-xs uppercase tracking-[0.15em] text-mist">The fix</p>
              {diff ? (
                <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-cream p-3 font-mono text-xs leading-relaxed">
                  {diff.split("\n").map((line, index) => (
                    <span
                      key={index}
                      className={`block ${
                        line.startsWith("+") && !line.startsWith("+++")
                          ? "text-fixed"
                          : line.startsWith("-") && !line.startsWith("---")
                            ? "text-bug"
                            : ""
                      }`}
                    >
                      {line || " "}
                    </span>
                  ))}
                </pre>
              ) : (
                <p className="mt-1 text-mist">{bug && running ? "Writing the fix…" : "—"}</p>
              )}
            </div>
            {projectId && done && (
              <Link to={`/p/${projectId}/fix`} className="btn-secondary inline-block">
                Open this race in FixPilot
              </Link>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
