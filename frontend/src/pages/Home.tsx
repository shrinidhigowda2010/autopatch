import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "../api";
import BugFixTyping from "../components/BugFixTyping";
import CountUp from "../components/CountUp";
import { Skeleton } from "../components/Skeleton";
import HeroShield from "../components/HeroShield";
import Logo from "../components/Logo";
import type { SampleInfo } from "../types";

interface Benchmark {
  detection_rate?: number;
  fix_success_rate?: number;
  false_positives?: number;
  false_positive_count?: number;
  bug_count?: number;
  project_count?: number;
  projects_fixed?: number;
  projects?: { fixed?: boolean; detected?: number; ground_truth?: number }[];
  summary?: {
    detection_rate?: number;
    fix_success_rate?: number;
    false_positives?: number;
  };
}

const TECH = ["Python", "FastAPI", "React", "Gemini", "SQLAlchemy", "Docker"];

const HOW = [
  {
    title: "Detect",
    copy: "Static analysis tools and Gemini read your code together, then merge what they find into one clear bug list.",
  },
  {
    title: "Repair",
    copy: "FixPilot writes the smallest change that fixes each bug and shows you a before/after. You approve, edit or reject it.",
  },
  {
    title: "Verify",
    copy: "Tests run on the old code and the new code. If a fix breaks anything, it is undone on its own.",
  },
] as const;

export default function Home() {
  const navigate = useNavigate();
  const location = useLocation();
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  // Filled from the measured benchmark (benchmark/results/latest.json via the API).
  const [bench, setBench] = useState<{
    bugsDetected: number;
    fixesVerified: number;
    falsePositives: number;
    projectsTested: number;
  } | null>(null);

  useEffect(() => {
    api<SampleInfo[]>("/api/samples").then(setSamples).catch((err: Error) => setError(err.message));
    api<Benchmark>("/api/benchmark")
      .then((body) => {
        const projects = body.projects || [];
        const fromProjects = projects.reduce(
          (sum, row) => sum + (row.detected ?? row.ground_truth ?? 0),
          0,
        );
        const bugsDetected = body.bug_count ?? fromProjects;
        const rate = body.fix_success_rate ?? body.summary?.fix_success_rate ?? 0;
        const fixesVerified = Math.round(bugsDetected * (rate <= 1 ? rate : rate / 100));
        setBench({
          bugsDetected,
          fixesVerified,
          falsePositives: Number(
            body.false_positive_count ?? body.false_positives ?? body.summary?.false_positives ?? 0,
          ),
          projectsTested: body.project_count ?? projects.length,
        });
      })
      .catch(() => undefined);
  }, []);

  // Links like "/#examples" from other pages land on the sample cards.
  useEffect(() => {
    if (location.hash !== "#examples" || samples.length === 0) return;
    document.getElementById("examples")?.scrollIntoView({ behavior: "smooth" });
  }, [location.hash, samples.length]);

  async function openSample(sample: SampleInfo) {
    setBusy(sample.id);
    setError("");
    try {
      const project = await api<{ id: string }>("/api/projects/sample", {
        method: "POST",
        body: JSON.stringify({ sample_id: sample.id }),
      });
      navigate(`/p/${project.id}/scan?auto=1`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That sample didn't open. Give it a second and try again.");
      setBusy("");
    }
  }

  return (
    <div className="mx-auto max-w-6xl text-ink">
      <section className="grid items-center gap-8 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <Logo className="h-12 w-auto" />
          <p className="mt-6 font-mono text-xs uppercase tracking-[0.22em] text-ink">Find it. Fix it. Prove it.</p>
          <h1 className="mt-3 max-w-xl text-4xl font-semibold leading-tight tracking-tight text-ink md:text-5xl">
            Find the bug. Fix it. Prove the fix works.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-ink/80">
            Drop in your code and FixPilot finds what's broken, tells you why in plain words, writes the smallest fix, and
            runs tests to prove it. Nothing changes until you say yes.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/upload" className="btn-primary">
              Upload your code
            </Link>
            <a href="#examples" className="btn-secondary">
              Try a sample in one click
            </a>
          </div>
          <div className="mt-8 max-w-md">
            <BugFixTyping />
          </div>
        </div>
        <HeroShield />
      </section>

      <section className="mt-12 grid gap-3 rounded-2xl border border-line bg-panel p-5 shadow-card sm:grid-cols-2 lg:grid-cols-4">
        {(
          [
            ["Bugs detected", bench?.bugsDetected],
            ["Fixes verified", bench?.fixesVerified],
            ["False positives", bench?.falsePositives],
            ["Projects tested", bench?.projectsTested],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="px-2 py-1">
            <p className="text-sm text-mist">{label}</p>
            <div className="mt-1 text-4xl font-semibold text-ink">
              {value === undefined ? <Skeleton className="mt-1 h-10 w-16" /> : <CountUp value={value} />}
            </div>
          </div>
        ))}
        <p className="text-xs text-mist sm:col-span-2 lg:col-span-4">
          Measured by the built-in benchmark on 8 seeded projects. <Link to="/benchmark" className="font-medium text-ink underline">See the details</Link>
        </p>
      </section>

      <section className="mt-16">
        <h2 className="text-3xl font-semibold text-ink">How it works</h2>
        <p className="mt-2 max-w-2xl text-ink/80">Three steps from broken code to a fix you can trust.</p>
        <div className="mt-8 grid gap-5 md:grid-cols-3" style={{ perspective: "1200px" }}>
          {HOW.map((item, index) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, y: 20, rotateX: 8 }}
              whileInView={{ opacity: 1, y: 0, rotateX: index === 1 ? -2 : index === 2 ? 3 : 4 }}
              whileHover={{ y: -10, rotateX: 0, rotateY: index === 0 ? 4 : index === 2 ? -4 : 0, scale: 1.02 }}
              viewport={{ once: true, amount: 0.35 }}
              transition={{ delay: index * 0.08, type: "spring", stiffness: 260, damping: 22 }}
              className="rounded-2xl border border-line bg-panel p-6 shadow-card will-change-transform"
              style={{
                transformStyle: "preserve-3d",
                transform: `rotateZ(${index === 0 ? -2 : index === 2 ? 2 : 0}deg)`,
              }}
            >
              <p className="font-mono text-xs uppercase tracking-[0.18em] text-mist">0{index + 1}</p>
              <h3 className="mt-2 text-xl font-semibold text-ink">{item.title}</h3>
              <p className="mt-2 text-ink/80">{item.copy}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="text-3xl font-semibold text-ink">Why FixPilot</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {[
            ["Test-proven fixes", "A fix only counts when the tests that failed before pass after."],
            ["Human approval on every change", "FixPilot asks before every change. Risky edits never go in on their own."],
            ["Explainable root cause", "Every bug comes with the input that triggers it, in plain words, and in Kannada or Hindi if you prefer."],
            ["Full audit trail", "Every decision is logged with your Coder ID and time, and you can download it all as a PDF."],
          ].map(([title, copy]) => (
            <div key={title} className="card-3d p-5">
              <h3 className="text-lg font-semibold text-ink">{title}</h3>
              <p className="mt-2 text-ink/80">{copy}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="examples" className="mt-16 scroll-mt-8">
        <h2 className="text-3xl font-semibold text-ink">Explore example projects</h2>
        <p className="mt-2 max-w-2xl text-ink/80">
          New here? Pick one. Each card opens a small program with real bugs and scans it right away, so you can see the
          whole find, fix and prove loop in about a minute.
        </p>
        {error && <p className="mt-4 text-bug">{error}</p>}
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {samples.length === 0 && !error && [0, 1, 2, 3].map((key) => <Skeleton key={key} className="h-36" />)}
          {samples.map((sample) => (
            <button
              key={sample.id}
              onClick={() => openSample(sample)}
              disabled={busy === sample.id}
              className="card-3d p-5 text-left text-ink disabled:opacity-60"
            >
              <p className="text-lg font-semibold">{sample.title}</p>
              <p className="mt-2 text-ink/80">{sample.blurb}</p>
              <p className="mt-4 font-mono text-xs text-mist">
                {busy === sample.id ? "Loading…" : `${sample.bugs} bugs hiding · tap to scan`}
              </p>
            </button>
          ))}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-ink">Built with</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {TECH.map((name) => (
            <span
              key={name}
              className="rounded-xl border border-line bg-panel px-3 py-2 text-sm font-medium text-ink shadow-emboss"
            >
              {name}
            </span>
          ))}
        </div>
      </section>

      <footer className="mt-20 border-t border-line pb-4 pt-10">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div>
            <Logo className="h-9 w-auto" />
            <p className="mt-3 font-mono text-sm text-ink">Find it. Fix it. Prove it.</p>
            <p className="mt-2 text-sm text-ink/80">Built at Sapthagiri NPS University</p>
          </div>
          <a
            href="https://github.com/shrinidhigowda2010/autopatch"
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium text-ink underline-offset-4 hover:underline"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
