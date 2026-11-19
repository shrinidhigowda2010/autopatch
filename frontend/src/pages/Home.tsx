import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "../api";
import BugFixTyping from "../components/BugFixTyping";
import CountUp from "../components/CountUp";
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
    copy: "Static analysis plus an AI layer merges findings into clear bug reports.",
  },
  {
    title: "Repair",
    copy: "Minimal patches with side-by-side diffs. You approve, edit, or reject each change.",
  },
  {
    title: "Verify",
    copy: "Sandbox tests before and after every fix, with auto-rollback if something breaks.",
  },
] as const;

export default function Home() {
  const navigate = useNavigate();
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [bench, setBench] = useState({
    bugsDetected: 12,
    fixesVerified: 12,
    falsePositives: 0,
    projectsTested: 8,
  });

  useEffect(() => {
    api<SampleInfo[]>("/api/samples").then(setSamples).catch((err: Error) => setError(err.message));
    api<Benchmark>("/api/benchmark")
      .then((body) => {
        const projects = body.projects || [];
        const fromProjects = projects.reduce(
          (sum, row) => sum + (row.detected ?? row.ground_truth ?? 0),
          0,
        );
        const bugsDetected = body.bug_count ?? (fromProjects || 12);
        const rate = body.fix_success_rate ?? body.summary?.fix_success_rate ?? 1;
        const fixesVerified = Math.round(bugsDetected * (rate <= 1 ? rate : rate / 100));
        setBench({
          bugsDetected,
          fixesVerified,
          falsePositives: Number(
            body.false_positive_count ?? body.false_positives ?? body.summary?.false_positives ?? 0,
          ),
          projectsTested: body.project_count ?? (projects.length || 8),
        });
      })
      .catch(() => undefined);
  }, []);

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
      setError(err instanceof Error ? err.message : "Could not load the project.");
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
            Autonomous repair with human approval at every step.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-ink/80">
            FixPilot finds real bugs, explains the root cause, proposes a minimal patch, and proves it with tests —
            nothing is written until you approve.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/upload" className="btn-primary">
              Get started
            </Link>
            <a href="#examples" className="btn-secondary">
              Explore example projects
            </a>
          </div>
          <div className="mt-8 max-w-md">
            <BugFixTyping />
          </div>
        </div>
        <HeroShield />
      </section>

      <section className="mt-12 grid gap-3 rounded-2xl border border-line bg-panel p-5 shadow-card sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Bugs detected", bench.bugsDetected],
          ["Fixes verified", bench.fixesVerified],
          ["False positives", bench.falsePositives],
          ["Projects tested", bench.projectsTested],
        ].map(([label, value]) => (
          <div key={label as string} className="px-2 py-1">
            <p className="text-sm text-ink/70">{label}</p>
            <p className="mt-1 text-4xl font-semibold text-ink">
              <CountUp value={value as number} />
            </p>
          </div>
        ))}
      </section>

      <section className="mt-16">
        <h2 className="text-3xl font-semibold text-ink">How it works</h2>
        <p className="mt-2 max-w-2xl text-ink/80">Three steps from buggy code to a verified fix.</p>
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
              <p className="font-mono text-xs uppercase tracking-[0.18em] text-ink/60">0{index + 1}</p>
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
            ["Test-proven fixes", "Every approved change is checked in a sandbox before and after it lands."],
            ["Human approval on every change", "Ask-every-fix mode keeps you in control; risky edits never auto-apply."],
            ["Explainable root cause", "Plain-language triggers and student-friendly explanations for each finding."],
            ["Full audit trail", "Coder ID, decisions, and version timeline ship with your PDF and JSON reports."],
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
          Each card loads a small buggy program and starts a scan so you can walk the full Detect → Repair → Verify loop.
        </p>
        {error && <p className="mt-4 text-bug">{error}</p>}
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {samples.map((sample) => (
            <button
              key={sample.id}
              onClick={() => openSample(sample)}
              disabled={busy === sample.id}
              className="card-3d p-5 text-left text-ink disabled:opacity-60"
            >
              <p className="text-lg font-semibold">{sample.title}</p>
              <p className="mt-2 text-ink/80">{sample.blurb}</p>
              <p className="mt-4 font-mono text-xs text-ink/70">
                {busy === sample.id ? "Loading…" : `${sample.bugs} known bugs`}
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
            href="https://github.com"
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
