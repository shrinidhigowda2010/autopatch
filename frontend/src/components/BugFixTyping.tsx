import { useEffect, useState } from "react";

const BUGGY = "avg = sum(marks) / len(marks)";
const FIXED = "avg = sum(marks) / len(marks) if marks else 0";
const PASS = "✓ tests passed";

type Phase = "type-bug" | "underline" | "type-fix" | "pass" | "pause";

export default function BugFixTyping() {
  const [phase, setPhase] = useState<Phase>("type-bug");
  const [bugText, setBugText] = useState("");
  const [fixText, setFixText] = useState("");
  const [showUnderline, setShowUnderline] = useState(false);
  const [showPass, setShowPass] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);

  useEffect(() => {
    if (reduced) {
      setBugText(BUGGY);
      setFixText(FIXED);
      setShowUnderline(true);
      setShowPass(true);
      return;
    }

    let cancelled = false;
    let timer = 0;

    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        timer = window.setTimeout(resolve, ms);
      });

    const type = async (full: string, setter: (v: string) => void, speed = 28) => {
      for (let i = 0; i <= full.length; i += 1) {
        if (cancelled) return;
        setter(full.slice(0, i));
        await wait(speed);
      }
    };

    const loop = async () => {
      while (!cancelled) {
        setPhase("type-bug");
        setBugText("");
        setFixText("");
        setShowUnderline(false);
        setShowPass(false);
        await type(BUGGY, setBugText);
        if (cancelled) return;
        setPhase("underline");
        setShowUnderline(true);
        await wait(700);
        if (cancelled) return;
        setPhase("type-fix");
        await type(FIXED, setFixText, 22);
        if (cancelled) return;
        setPhase("pass");
        setShowPass(true);
        await wait(1600);
        if (cancelled) return;
        setPhase("pause");
        await wait(900);
      }
    };

    void loop();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [reduced]);

  return (
    <div className="rounded-2xl border border-line bg-panel p-4 shadow-card font-mono text-sm text-ink md:p-5">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">Bug → Fix</p>
      <div className="space-y-3">
        <div>
          <p className="text-[11px] text-mist">before</p>
          <p className={`mt-1 break-all ${showUnderline ? "decoration-bug underline decoration-2 underline-offset-4" : ""}`}>
            {bugText}
            {phase === "type-bug" && <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-ink align-middle" />}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-mist">after</p>
          <p className="mt-1 break-all text-fixed">
            {fixText}
            {phase === "type-fix" && <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-fixed align-middle" />}
          </p>
        </div>
        {showPass && (
          <p className="rounded-xl border border-fixed/30 bg-fixed/10 px-3 py-2 text-xs font-medium text-ink">
            {PASS}
          </p>
        )}
      </div>
    </div>
  );
}
