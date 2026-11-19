import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { SampleInfo } from "../types";

export default function Home() {
  const navigate = useNavigate();
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<SampleInfo[]>("/api/samples").then(setSamples).catch((err: Error) => setError(err.message));
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
      setError(err instanceof Error ? err.message : "Could not load the sample.");
      setBusy("");
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-lime">Problem statement 02</p>
      <h1 className="mt-2 max-w-3xl text-4xl font-semibold leading-tight md:text-5xl">
        A bug report you can read, a patch you approve, and a test that shows the fix worked.
      </h1>
      <p className="mt-4 max-w-2xl text-mist">
        Upload a Python file, a zip, or a public GitHub repo. AutoPatch runs real linters and a security scan,
        then asks Gemini about logic mistakes. Nothing is written into your project until you accept it.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link to="/upload" className="rounded-lg bg-lime px-4 py-2 font-medium text-ink">
          Upload code
        </Link>
        <Link to="/benchmark" className="rounded-lg border border-line px-4 py-2">
          See measured benchmark
        </Link>
      </div>
      {error && <p className="mt-4 text-coral">{error}</p>}
      <h2 className="mt-10 text-lg font-medium">One-click demo</h2>
      <p className="text-sm text-mist">Each card loads a small buggy program and starts a scan. The marks calculator is the one from the problem statement.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {samples.map((sample) => (
          <button
            key={sample.id}
            onClick={() => openSample(sample)}
            disabled={busy === sample.id}
            className="rounded-xl border border-line bg-panel p-4 text-left hover:border-lime/60 disabled:opacity-60"
          >
            <p className="font-medium">{sample.title}</p>
            <p className="mt-1 text-sm text-mist">{sample.blurb}</p>
            <p className="mt-3 font-mono text-xs text-lime">{busy === sample.id ? "Loading…" : `${sample.bugs} known bugs`}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
