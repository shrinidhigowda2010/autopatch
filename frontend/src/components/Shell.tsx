import { Link, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { createContext, useContext, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAuth } from "../auth";
import AiStatus from "./AiStatus";
import Logo from "./Logo";

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
  return `rounded-2xl px-3 py-2 text-sm transition ${active ? "bg-ink text-cream shadow-emboss" : "text-ink hover:bg-panel"}`;
}

export default function Shell() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isGuest, initials, logout } = useAuth();
  const [studentMode, setStudentMode] = useState(false);
  const [language, setLanguage] = useState<"en" | "kn" | "hi">("en");
  const [menuOpen, setMenuOpen] = useState(false);
  // Pathless layout routes sometimes omit child params — also read from the URL.
  const projectId = useMemo(() => {
    if (params.projectId) return params.projectId;
    const match = location.pathname.match(/^\/p\/([^/]+)/);
    return match?.[1];
  }, [params.projectId, location.pathname]);
  const base = projectId ? `/p/${projectId}` : "";
  const isAuthPage = location.pathname === "/login" || location.pathname === "/register";
  const assistantTo = projectId ? `${base}/assistant` : "/upload";

  function stepActive(path: string): boolean {
    if (projectId) return location.pathname.startsWith(`${base}/${path}`);
    return path === "upload" && location.pathname === "/upload";
  }

  async function onLogout() {
    setMenuOpen(false);
    await logout();
    navigate("/login");
  }

  return (
    <PrefsContext.Provider value={{ studentMode, setStudentMode, language, setLanguage }}>
      <div className={`min-h-screen ${isAuthPage ? "" : "md:grid md:grid-cols-[260px_1fr]"}`}>
        {!isAuthPage && (
          <aside className="border-b border-line bg-panel/90 px-5 py-6 md:min-h-screen md:border-b-0 md:border-r">
            <Link to="/" className="block">
              <Logo className="h-10 w-auto" />
            </Link>
            <p className="mt-3 text-sm text-mist">Find it. Fix it. Prove it.</p>
            <nav className="mt-8 flex gap-2 overflow-x-auto md:flex-col">
              {steps.map(([path, label], index) => (
                <Link
                  key={path}
                  to={projectId ? `${base}/${path}` : "/upload"}
                  aria-current={stepActive(path) ? "page" : undefined}
                  className={navClass(stepActive(path))}
                >
                  <span className="mr-2 font-mono text-xs opacity-60">0{index + 1}</span>
                  {label}
                </Link>
              ))}
              <div className="my-2 hidden h-px bg-line md:block" />
              <Link
                to={assistantTo}
                className={navClass(Boolean(projectId) && location.pathname.includes("/assistant"))}
              >
                FixPilot Assistant
              </Link>
              <Link
                to={projectId ? `${base}/dashboard` : "/upload"}
                className={navClass(Boolean(projectId) && location.pathname.startsWith(`${base}/dashboard`))}
              >
                Dashboard
              </Link>
              <Link
                to={projectId ? `${base}/history` : "/upload"}
                className={navClass(Boolean(projectId) && location.pathname.startsWith(`${base}/history`))}
              >
                History
              </Link>
              {projectId && (
                <Link to={`${base}/decisions`} className={navClass(location.pathname.startsWith(`${base}/decisions`))}>
                  Decision Log
                </Link>
              )}
              <Link to="/benchmark" className={navClass(location.pathname.startsWith("/benchmark"))}>
                Benchmark
              </Link>
              <Link to="/race" className={navClass(false)}>
                🏁 Repair Race
              </Link>
            </nav>
            <div className="mt-8 hidden md:block">
              <AiStatus />
            </div>
          </aside>
        )}
        <div className="flex min-h-screen flex-col">
          {!isAuthPage && (
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
              <p className="text-sm text-mist">{projectId ? `Project ${projectId}` : "No project loaded"}</p>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <label className="flex items-center gap-2 text-mist">
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
                  className="rounded-xl border border-line bg-panel px-2 py-1.5 text-ink"
                >
                  <option value="en">English</option>
                  <option value="kn">ಕನ್ನಡ</option>
                  <option value="hi">हिन्दी</option>
                </select>

                {user ? (
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setMenuOpen((open) => !open)}
                      className="flex items-center gap-2 rounded-2xl border border-line bg-panel px-2 py-1 shadow-emboss"
                    >
                      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-xs font-semibold text-cream">
                        {initials}
                      </span>
                      <span className="hidden font-mono text-xs text-mist sm:inline">{user.coder_id}</span>
                    </button>
                    {menuOpen && (
                      <div className="absolute right-0 z-40 mt-2 w-48 rounded-2xl border border-line bg-panel py-1 shadow-card">
                        <Link to="/profile" onClick={() => setMenuOpen(false)} className="block px-3 py-2 hover:bg-cream">
                          Profile
                        </Link>
                        <Link to="/my-history" onClick={() => setMenuOpen(false)} className="block px-3 py-2 hover:bg-cream">
                          My History
                        </Link>
                        <button type="button" onClick={() => void onLogout()} className="block w-full px-3 py-2 text-left hover:bg-cream">
                          Logout
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    {isGuest && <span className="rounded-xl border border-line px-2 py-1 text-xs text-mist">Guest</span>}
                    <Link to="/login" className="btn-secondary px-3 py-1.5 text-sm">
                      Sign in
                    </Link>
                  </div>
                )}
              </div>
            </header>
          )}
          <main className={`flex-1 px-5 py-6 ${isAuthPage ? "px-4" : ""}`}>
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.28, ease: "easeOut" }}
                className="page-enter"
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </main>
          {!isAuthPage && (
            <footer className="border-t border-line px-5 py-3 md:hidden">
              <AiStatus />
            </footer>
          )}
        </div>
      </div>
    </PrefsContext.Provider>
  );
}
