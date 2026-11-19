import { Link, Outlet, useLocation, useParams } from "react-router-dom";
import { createContext, useContext, useState } from "react";

interface Prefs {
  studentMode: boolean;
  setStudentMode: (value: boolean) => void;
  language: "en" | "kn" | "hi";
  setLanguage: (value: "en" | "kn" | "hi") => void;
}

const PrefsContext = createContext<Prefs>({
  studentMode: false,
  setStudentMode: () => undefined,
  language: "en",
  setLanguage: () => undefined,
});

export function usePrefs() {
  return useContext(PrefsContext);
}

const steps = [
  ["upload", "Upload"],
  ["scan", "Scan"],
  ["explain", "Explain"],
  ["fix", "Fix"],
  ["test", "Test"],
] as const;

function navClass(active: boolean): string {
  return `rounded-lg px-3 py-2 text-sm ${active ? "bg-lime text-ink" : "text-paper hover:bg-white/5"}`;
}

export default function Shell() {
  const { projectId } = useParams();
  const location = useLocation();
  const [studentMode, setStudentMode] = useState(false);
  const [language, setLanguage] = useState<"en" | "kn" | "hi">("en");
  const base = projectId ? `/p/${projectId}` : "";

  function stepActive(path: string): boolean {
    if (projectId) return location.pathname.startsWith(`${base}/${path}`);
    return path === "upload" && location.pathname === "/upload";
  }

  return (
    <PrefsContext.Provider value={{ studentMode, setStudentMode, language, setLanguage }}>
      <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
        <aside className="border-b border-line bg-panel/80 px-4 py-5 md:min-h-screen md:border-b-0 md:border-r">
          <Link to="/" className="block">
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-lime">SAPTHAHACKS'26</p>
            <p className="mt-1 text-2xl font-semibold">AutoPatch</p>
          </Link>
          <p className="mt-2 text-sm text-mist">Find the bug. Explain it. Patch only the lines that need it. Prove it with a test.</p>
          <nav className="mt-6 flex gap-2 overflow-x-auto md:flex-col">
            {steps.map(([path, label], index) => (
              <Link
                key={path}
                to={projectId ? `${base}/${path}` : "/upload"}
                aria-current={stepActive(path) ? "page" : undefined}
                className={navClass(stepActive(path))}
              >
                <span className="mr-2 font-mono text-xs opacity-70">0{index + 1}</span>
                {label}
              </Link>
            ))}
            <div className="my-2 hidden h-px bg-line md:block" />
            <Link to={projectId ? `${base}/dashboard` : "/upload"} aria-current={projectId && location.pathname.startsWith(`${base}/dashboard`) ? "page" : undefined} className={navClass(Boolean(projectId) && location.pathname.startsWith(`${base}/dashboard`))}>
              Dashboard
            </Link>
            <Link to={projectId ? `${base}/history` : "/upload"} aria-current={projectId && location.pathname.startsWith(`${base}/history`) ? "page" : undefined} className={navClass(Boolean(projectId) && location.pathname.startsWith(`${base}/history`))}>
              History
            </Link>
            <Link to="/benchmark" aria-current={location.pathname.startsWith("/benchmark") ? "page" : undefined} className={navClass(location.pathname.startsWith("/benchmark"))}>
              Benchmark
            </Link>
          </nav>
        </aside>
        <div>
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
            <p className="text-sm text-mist">{projectId ? `Project ${projectId}` : "No project loaded"}</p>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={studentMode}
                  onChange={(event) => setStudentMode(event.target.checked)}
                />
                Student mode
              </label>
              <select
                aria-label="Explanation language"
                value={language}
                onChange={(event) => setLanguage(event.target.value as "en" | "kn" | "hi")}
                className="rounded-md border border-line bg-ink px-2 py-1"
              >
                <option value="en">English</option>
                <option value="kn">ಕನ್ನಡ</option>
                <option value="hi">हिन्दी</option>
              </select>
            </div>
          </header>
          <main className="px-5 py-6">
            <Outlet />
          </main>
        </div>
      </div>
    </PrefsContext.Provider>
  );
}
