import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { extensionFor, guessLanguage, isArchiveName, looksLikeUrl } from "../lib/language";

type Tab = "file" | "paste" | "link";

type ExtractedFile = { path: string; content: string; language: string };

type Extraction = {
  kind: string;
  files: ExtractedFile[];
  notes: string[];
};

type Preview = Extraction & { source: string };

const TABS: { id: Tab; label: string }[] = [
  { id: "file", label: "Upload a file" },
  { id: "paste", label: "Paste code" },
  { id: "link", label: "Paste a link" },
];

const FORMATS = [
  "Code: .py .js .ts .jsx .tsx .java .c .cpp .cs .go .rb .php .kt .swift .rs .sql .sh .html .css",
  "Text: .json .yaml .xml .md .txt",
  "Archives: .zip .tar .tar.gz",
  "Documents: .pdf .docx .ipynb",
  "Screenshots: .png .jpg .webp .gif .bmp",
];

function checkLabel(language: string): string {
  return language === "Python"
    ? "Full check: static tools + sandbox tests"
    : "AI analysis only, not verified by tests";
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export default function Upload() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("file");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [code, setCode] = useState("");
  const [filename, setFilename] = useState("");
  const [url, setUrl] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const detected = guessLanguage(code);
  const pasteName = filename.trim() || `main${extensionFor(detected)}`;

  async function run<T>(label: string, work: () => Promise<T>) {
    setBusy(label);
    setError("");
    try {
      return await work();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      return undefined;
    } finally {
      setBusy("");
    }
  }

  async function importArchive(file: File) {
    const body = new FormData();
    body.append("file", file);
    const project = await run("Unpacking the archive…", () =>
      api<{ id: string }>("/api/projects/upload", { method: "POST", body }),
    );
    if (project) navigate(`/p/${project.id}/scan`);
  }

  async function sendFile(file: File) {
    if (isArchiveName(file.name)) {
      await importArchive(file);
      return;
    }
    const body = new FormData();
    body.append("file", file);
    const reading = file.type.startsWith("image/") ? "Reading the code in your image…" : "Reading the file…";
    const result = await run(reading, () =>
      api<Extraction>("/api/projects/extract", { method: "POST", body }),
    );
    if (!result) return;
    if (result.kind === "archive") {
      await importArchive(file);
      return;
    }
    setPreview({ ...result, source: file.name });
  }

  async function createProject(name: string, origin: string, files: { path: string; content: string }[]) {
    const project = await run("Creating the project…", () =>
      api<{ id: string }>("/api/projects/paste", {
        method: "POST",
        body: JSON.stringify({ name, origin, files }),
      }),
    );
    if (project) navigate(`/p/${project.id}/scan`);
  }

  async function sendPaste(event: FormEvent) {
    event.preventDefault();
    await createProject(pasteName.replace(/\.[^.]+$/, ""), "paste", [{ path: pasteName, content: code }]);
  }

  async function sendLink(event: FormEvent) {
    event.preventDefault();
    const project = await run("Fetching the link…", () =>
      api<{ id: string }>("/api/projects/link", { method: "POST", body: JSON.stringify({ url: url.trim() }) }),
    );
    if (project) navigate(`/p/${project.id}/scan`);
  }

  function updateFile(index: number, change: Partial<ExtractedFile>) {
    setPreview((current) => {
      if (!current) return current;
      const files = current.files.map((file, at) => (at === index ? { ...file, ...change } : file));
      return { ...current, files };
    });
  }

  function removeFile(index: number) {
    setPreview((current) => (current ? { ...current, files: current.files.filter((_, at) => at !== index) } : current));
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void sendFile(file);
  }

  // Ctrl+V anywhere on the page: images upload, links go to the link tab, text goes to the paste tab.
  useEffect(() => {
    function onPaste(event: ClipboardEvent) {
      if (isTyping(event.target) || busy || preview) return;
      const data = event.clipboardData;
      if (!data) return;
      const file = Array.from(data.files)[0];
      if (file) {
        event.preventDefault();
        setTab("file");
        void sendFile(file.name ? file : new File([file], "pasted-image.png", { type: file.type }));
        return;
      }
      const text = data.getData("text");
      if (!text.trim()) return;
      event.preventDefault();
      setPreview(null);
      if (looksLikeUrl(text)) {
        setUrl(text.trim());
        setTab("link");
      } else {
        setCode(text);
        setTab("paste");
      }
    }
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  });

  if (preview) {
    const ready = preview.files.some((file) => file.content.trim());
    return (
      <div className="mx-auto max-w-4xl">
        <h1 className="text-3xl font-semibold">Here's what FixPilot found</h1>
        <p className="mt-2 text-mist">
          From <span className="font-medium text-ink">{preview.source}</span>. Check the code, fix anything that was
          read wrong, then scan.
        </p>
        {preview.notes.length > 0 && (
          <ul className="mt-4 space-y-1 rounded-xl border border-line bg-panel px-4 py-3 text-sm text-mist">
            {preview.notes.map((note) => (
              <li key={note}>• {note}</li>
            ))}
          </ul>
        )}
        <div className="mt-6 space-y-5">
          {preview.files.map((file, index) => (
            <div key={index} className="card-3d p-4">
              <div className="flex flex-wrap items-center gap-3">
                <input
                  value={file.path}
                  onChange={(event) => updateFile(index, { path: event.target.value })}
                  className="flex-1 rounded-lg border border-line bg-cream px-3 py-1.5 font-mono text-sm"
                  aria-label="File name"
                />
                <span className="badge-emboss border-line">{file.language}</span>
                <button type="button" className="text-sm text-mist underline" onClick={() => removeFile(index)}>
                  Remove
                </button>
              </div>
              <p className="mt-2 text-xs text-mist">{checkLabel(file.language)}</p>
              <textarea
                value={file.content}
                onChange={(event) => updateFile(index, { content: event.target.value })}
                spellCheck={false}
                rows={Math.min(24, Math.max(6, file.content.split("\n").length + 1))}
                className="mt-3 w-full rounded-lg border border-line bg-cream p-3 font-mono text-sm leading-relaxed"
              />
            </div>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            className="btn-primary"
            disabled={!ready || Boolean(busy)}
            onClick={() =>
              void createProject(
                preview.source.replace(/\.[^.]+$/, ""),
                preview.kind,
                preview.files.map(({ path, content }) => ({ path, content })),
              )
            }
          >
            {busy || "Scan now"}
          </button>
          <button className="btn-secondary" disabled={Boolean(busy)} onClick={() => setPreview(null)}>
            Start over
          </button>
        </div>
        {error && <p className="mt-4 text-bug">{error}</p>}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-semibold">Upload</h1>
      <p className="mt-2 text-mist">
        Code files, archives, PDFs, Word docs, notebooks or screenshots of code, up to 8 MB. You can also press Ctrl+V
        anywhere on this page.
      </p>

      <div className="mt-6 flex gap-2 rounded-2xl border border-line bg-panel p-1" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={`flex-1 rounded-xl px-3 py-2 text-sm font-medium transition ${
              tab === item.id ? "bg-ink text-cream shadow-emboss" : "text-ink hover:bg-cream"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "file" && (
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileInput.current?.click()}
          className={`mt-6 cursor-pointer rounded-xl border border-dashed px-6 py-12 text-center transition ${
            dragging ? "border-ink bg-cream" : "border-line bg-panel"
          }`}
        >
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void sendFile(file);
            }}
          />
          <span className="text-lg">{busy || "Drop a file here, or click to choose one"}</span>
          <ul className="mx-auto mt-4 max-w-xl space-y-1 text-left text-sm text-mist">
            {FORMATS.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-mist">
            PDFs, documents and screenshots open in a preview first, so you can check the code before scanning.
          </p>
        </div>
      )}

      {tab === "paste" && (
        <form onSubmit={sendPaste} className="mt-6 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <input
              value={filename}
              onChange={(event) => setFilename(event.target.value)}
              placeholder={pasteName}
              className="flex-1 rounded-lg border border-line bg-cream px-3 py-2 font-mono text-sm"
              aria-label="File name"
            />
            <span className="badge-emboss border-line">{code.trim() ? detected : "No code yet"}</span>
          </div>
          <textarea
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="Paste your code here"
            spellCheck={false}
            rows={16}
            className="w-full rounded-xl border border-line bg-panel p-4 font-mono text-sm leading-relaxed"
          />
          {code.trim() && <p className="text-xs text-mist">{checkLabel(detected)}</p>}
          <button className="btn-primary" disabled={!code.trim() || Boolean(busy)}>
            {busy || "Scan now"}
          </button>
        </form>
      )}

      {tab === "link" && (
        <form onSubmit={sendLink} className="mt-6 space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://github.com/owner/repo"
              className="flex-1 rounded-lg border border-line bg-cream px-3 py-2"
            />
            <button className="btn-primary" disabled={!url.trim() || Boolean(busy)}>
              {busy || "Import"}
            </button>
          </div>
          <ul className="space-y-1 text-sm text-mist">
            <li>GitHub repo: https://github.com/owner/repo</li>
            <li>GitHub file: https://github.com/owner/repo/blob/main/app.py</li>
            <li>Gist, Pastebin, or any public raw file link (http or https)</li>
          </ul>
        </form>
      )}

      {error && <p className="mt-4 text-bug">{error}</p>}
    </div>
  );
}
