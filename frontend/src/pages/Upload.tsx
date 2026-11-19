import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function Upload() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function sendFile(file: File) {
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const project = await api<{ id: string }>("/api/projects/upload", { method: "POST", body });
      navigate(`/p/${project.id}/scan`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function sendGithub(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const project = await api<{ id: string }>("/api/projects/github", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      navigate(`/p/${project.id}/scan`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "GitHub import failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">Upload</h1>
      <p className="mt-2 text-mist">A single source file, a zip of a project, or a public GitHub URL. The cap is 8 MB.</p>
      <label className="mt-6 block cursor-pointer rounded-xl border border-dashed border-line bg-panel px-6 py-10 text-center">
        <input
          type="file"
          className="hidden"
          accept=".py,.js,.jsx,.ts,.tsx,.zip,.json,.txt,.md"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void sendFile(file);
          }}
        />
        <span className="text-lg">{busy ? "Reading the files…" : "Drop a file here, or click to choose one"}</span>
        <p className="mt-2 text-sm text-mist">.py, .js, .ts or .zip</p>
      </label>
      <form onSubmit={sendGithub} className="mt-6 flex flex-col gap-3 sm:flex-row">
        <input
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://github.com/owner/repo"
          className="flex-1 rounded-lg border border-line bg-cream px-3 py-2"
        />
        <button className="btn-primary" disabled={busy || !url}>
          Import repo
        </button>
      </form>
      {error && <p className="mt-4 text-bug">{error}</p>}
    </div>
  );
}
