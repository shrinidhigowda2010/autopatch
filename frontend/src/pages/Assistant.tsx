import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { api } from "../api";
import { useAuth } from "../auth";
import FileTree from "../components/FileTree";
import { usePrefs } from "../components/Shell";
import ChatSidebar, { type ConversationRow } from "../components/assistant/ChatSidebar";
import Composer, { type ChatMode } from "../components/assistant/Composer";
import MessageBubble, { ThinkingDots, type ChatMsg, type PatchCard, type ToolStep } from "../components/assistant/MessageBubble";
import { MenuIcon } from "../components/assistant/icons";
import { recentChatIds, recentProjectIds, rememberChat } from "../lib/recent";
import { listen, speechSupported } from "../lib/speech";
import { getStoredToken } from "../token";
import type { Project, TreeNode } from "../types";

interface BugRow {
  id: string;
  title: string;
  severity: string;
  file: string;
}

interface Suggestion {
  title: string;
  prompt: string;
  prefill?: boolean; // put it in the box for the user to finish instead of sending
}

const PROJECT_SUGGESTIONS: Suggestion[] = [
  { title: "Find every bug", prompt: "Find all bugs in this project" },
  { title: "Explain it simply", prompt: "Explain the most serious bug simply, like I'm new to coding" },
  { title: "Fix and prove it", prompt: "Fix the most serious bug and run the tests to prove it" },
  { title: "Review my code", prompt: "Review this project for risky code and missing edge cases" },
];

const GENERAL_SUGGESTIONS: Suggestion[] = [
  { title: "Check my code", prompt: "Find bugs in this code:\n```python\n\n```", prefill: true },
  { title: "Explain an error", prompt: "Explain this error and how to fix it:\n", prefill: true },
  { title: "Try an example", prompt: "Find bugs in: def average(marks): return sum(marks) / len(marks)" },
  { title: "Learn a concept", prompt: "Explain Python list comprehensions with a short example" },
];

const MAX_MESSAGE_CHARS = 12000;
const TEXT_ATTACH_LIMIT = 200_000;
const BINARY_TYPES = /\.(pdf|docx|png|jpe?g|webp|ipynb)$/i;

function authHeader(): HeadersInit {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function asChatMsg(msg: ChatMsg): ChatMsg {
  return { ...msg, role: msg.role === "user" ? "user" : "assistant" };
}

/**
 * The FixPilot Assistant. Inside /p/:projectId it chats about that project.
 * At /assistant it is a standalone chat: code pasted or attached in a message is
 * scanned behind the scenes, and an existing project can be picked instead.
 */
export default function Assistant() {
  const { projectId = "" } = useParams();
  const standalone = !projectId;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { user, initials } = useAuth();
  const { language } = usePrefs(); // the header language drives replies and voice input

  const [project, setProject] = useState<Project | null>(null);
  const [myProjects, setMyProjects] = useState<{ id: string; name: string }[]>([]);
  const [bugs, setBugs] = useState<BugRow[]>([]);
  const [conversations, setConversations] = useState<ConversationRow[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("auto");
  const [busy, setBusy] = useState(false);
  const [loadingChat, setLoadingChat] = useState(true);
  const [attaching, setAttaching] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window !== "undefined" && window.innerWidth >= 1024);
  const [contextOpen, setContextOpen] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const stopListening = useRef<(() => void) | null>(null);
  const bugParam = params.get("bug") || "";
  const firstName = user?.full_name?.trim().split(/\s+/)[0] || "there";
  const micSupported = speechSupported();
  const suggestions = standalone ? GENERAL_SUGGESTIONS : PROJECT_SUGGESTIONS;

  const showProblem = useCallback((message: string) => {
    setError(message);
    setToast(message);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 6000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const loadConversations = useCallback(async () => {
    const query = standalone
      ? `ids=${encodeURIComponent(recentChatIds().join(","))}`
      : `project_id=${encodeURIComponent(projectId)}`;
    const body = await api<{ conversations: ConversationRow[] }>(`/api/assistant/conversations?${query}`);
    setConversations(body.conversations);
    return body.conversations;
  }, [projectId, standalone]);

  const openConversation = useCallback(async (id: string) => {
    setLoadingChat(true);
    try {
      const body = await api<ConversationRow & { messages: ChatMsg[] }>(`/api/assistant/conversations/${id}`);
      setActiveId(id);
      setMessages(body.messages.map(asChatMsg));
    } finally {
      setLoadingChat(false);
    }
  }, []);

  const createConversation = useCallback(async () => {
    const created = await api<ConversationRow>("/api/assistant/conversations", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId || undefined, title: "New chat", language }),
    });
    if (standalone) rememberChat(created.id);
    setActiveId(created.id);
    void loadConversations();
    return created.id;
  }, [projectId, standalone, language, loadConversations]);

  useEffect(() => {
    let cancelled = false;
    setMessages([]);
    setActiveId("");
    setProject(null);
    setBugs([]);
    setLoadingChat(true);
    if (projectId) {
      api<Project>(`/api/projects/${projectId}`)
        .then((proj) => !cancelled && setProject(proj))
        .catch((err: Error) => !cancelled && showProblem(err.message));
      api<{ bugs: BugRow[] }>(`/api/projects/${projectId}/dashboard`)
        .then((dash) => !cancelled && setBugs(dash.bugs || []))
        .catch(() => undefined);
    }
    loadConversations()
      .then(async (list) => {
        if (cancelled) return;
        if (list[0]) await openConversation(list[0].id);
        else setLoadingChat(false);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        showProblem(err.message);
        setLoadingChat(false);
      });
    return () => {
      cancelled = true;
    };
    // Only when the project changes; a language switch should not reset the chat.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Projects the user can attach from the standalone chat.
  useEffect(() => {
    if (!standalone) return;
    const ids = user ? "" : recentProjectIds().join(",");
    api<{ projects: { id: string; name: string }[] }>(`/api/me/history?ids=${encodeURIComponent(ids)}`)
      .then((body) => setMyProjects(body.projects))
      .catch(() => setMyProjects([]));
  }, [standalone, user]);

  useEffect(() => {
    if (bugParam) setInput((prev) => (prev.includes(bugParam) ? prev : `Explain bug ${bugParam} simply`));
  }, [bugParam]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => () => stopListening.current?.(), []);

  function updateReply(id: string, change: (msg: ChatMsg) => ChatMsg) {
    setMessages((prev) => prev.map((msg) => (msg.id === id ? change(msg) : msg)));
  }

  async function sendMessage(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    stopListening.current?.();
    setBusy(true);
    setError("");

    const replyId = `stream-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: "user", content },
      { id: replyId, role: "assistant", content: "", tool_steps: [], patches: [], streaming: true },
    ]);
    setInput("");

    let saved = false;
    let gotText = false;
    try {
      const convId = activeId || (await createConversation());
      const response = await fetch(`/api/assistant/conversations/${convId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ content, language, mode, bug_id: bugParam || undefined }),
      });
      if (!response.ok || !response.body) {
        const detail = await response.json().catch(() => null);
        throw new Error(
          (detail && typeof detail.detail === "string" && detail.detail) ||
            (response.status === 429 ? "You're sending messages quickly. Wait a moment and try again." : "Can't reach FixPilot right now. Check your connection and try again."),
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((row) => row.startsWith("data:"));
          if (!line) continue;
          const data = JSON.parse(line.slice(5).trim()) as Record<string, unknown>;
          if (data.type === "token") {
            gotText = true;
            updateReply(replyId, (msg) => ({ ...msg, content: msg.content + String(data.text || "") }));
          } else if (data.type === "tool") {
            const step = data as unknown as ToolStep;
            updateReply(replyId, (msg) => {
              const steps = [...(msg.tool_steps || [])];
              const index = steps.findIndex((s) => s.name === step.name && (s.label === step.label || s.status === "running"));
              if (index >= 0) steps[index] = step;
              else steps.push(step);
              return { ...msg, tool_steps: steps };
            });
          } else if (data.type === "patch") {
            const patch = data.patch as PatchCard;
            updateReply(replyId, (msg) => ({ ...msg, patches: [...(msg.patches || []), patch] }));
          } else if (data.type === "saved") {
            saved = true;
            updateReply(replyId, () => ({ ...(data.message as ChatMsg), role: "assistant", streaming: false }));
            void loadConversations();
          } else if (data.type === "error") {
            throw new Error(String(data.detail || "Something went wrong on my side. Try asking again."));
          }
        }
      }
      if (!saved) throw new Error("The connection closed before the reply finished. Please try again.");
    } catch (err) {
      showProblem(err instanceof Error ? err.message : "Something went wrong on my side. Try asking again.");
      if (!gotText) setMessages((prev) => prev.filter((msg) => msg.id !== replyId));
    } finally {
      setBusy(false);
      updateReply(replyId, (msg) => ({ ...msg, streaming: false }));
    }
  }

  function regenerate(replyIndex: number) {
    const question = [...messages.slice(0, replyIndex)].reverse().find((msg) => msg.role === "user");
    if (question) void sendMessage(question.content);
  }

  async function sendFeedback(messageId: string, value: number) {
    const before = messages.find((msg) => msg.id === messageId)?.feedback ?? null;
    updateReply(messageId, (msg) => ({ ...msg, feedback: value || null }));
    try {
      await api(`/api/assistant/messages/${messageId}/feedback`, { method: "POST", body: JSON.stringify({ value }) });
    } catch {
      updateReply(messageId, (msg) => ({ ...msg, feedback: before }));
      showProblem("Couldn't save that. Try again.");
    }
  }

  async function attachFile(file: File) {
    setAttaching(true);
    setError("");
    try {
      let snippets: { path: string; content: string; language: string }[];
      if (!BINARY_TYPES.test(file.name) && file.size <= TEXT_ATTACH_LIMIT) {
        snippets = [{ path: file.name, content: await file.text(), language: "" }];
      } else {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch("/api/projects/extract", { method: "POST", headers: authHeader(), body: form });
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          throw new Error((detail && typeof detail.detail === "string" && detail.detail) || "I couldn't read that file. Try pasting the code instead.");
        }
        const body = (await response.json()) as { files: typeof snippets };
        snippets = body.files;
      }
      if (!snippets.length || !snippets.some((item) => item.content.trim())) {
        throw new Error("I didn't find any code in that file.");
      }
      setInput((prev) => {
        const intro = prev.trim() || "Please check this code for bugs:";
        let room = MAX_MESSAGE_CHARS - intro.length - 40;
        const blocks = snippets.map((item) => {
          const code = item.content.slice(0, Math.max(0, room));
          room -= code.length + 20;
          return `\`\`\`${item.language.toLowerCase()}\n# ${item.path}\n${code}\n\`\`\``;
        });
        return `${intro}\n\n${blocks.join("\n\n")}`.slice(0, MAX_MESSAGE_CHARS);
      });
    } catch (err) {
      showProblem(err instanceof Error ? err.message : "Couldn't attach that file. Try pasting the code instead.");
    } finally {
      setAttaching(false);
    }
  }

  function toggleMic() {
    if (listening) {
      stopListening.current?.();
      return;
    }
    const base = input.trim();
    setListening(true);
    stopListening.current = listen(
      language,
      (spoken) => setInput(base ? `${base} ${spoken}` : spoken),
      (problem) => {
        setListening(false);
        stopListening.current = null;
        if (problem) showProblem(problem);
      },
    );
  }

  async function decidePatch(patchId: string, action: "approve" | "reject") {
    try {
      if (action === "approve") {
        await api(`/api/patches/${patchId}/approve`, { method: "POST" });
      } else {
        await api(`/api/patches/${patchId}/reject`, {
          method: "POST",
          body: JSON.stringify({ note: "Rejected from FixPilot Assistant" }),
        });
      }
      const status = action === "approve" ? "applied" : "rejected";
      setMessages((prev) =>
        prev.map((msg) => ({
          ...msg,
          patches: (msg.patches || []).map((p) => (p.patch_id === patchId ? { ...p, status } : p)),
        })),
      );
    } catch (err) {
      showProblem(err instanceof Error ? err.message : "Couldn't update that fix. Try again.");
    }
  }

  function newChat() {
    setError("");
    setActiveId("");
    setMessages([]);
    if (window.innerWidth < 768) setSidebarOpen(false);
  }

  async function renameChat(id: string) {
    const title = window.prompt("Rename chat", conversations.find((c) => c.id === id)?.title || "Chat");
    if (!title?.trim()) return;
    await api(`/api/assistant/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title: title.trim() }) });
    await loadConversations();
  }

  async function deleteChat(id: string) {
    if (!window.confirm("Delete this conversation?")) return;
    await api(`/api/assistant/conversations/${id}`, { method: "DELETE" });
    const list = await loadConversations();
    if (id === activeId) {
      if (list[0]) await openConversation(list[0].id);
      else newChat();
    }
  }

  function selectConversation(id: string) {
    if (window.innerWidth < 768) setSidebarOpen(false);
    void openConversation(id);
  }

  function attachBug(bug: BugRow) {
    setParams({ bug: bug.id });
    setInput(`Explain bug ${bug.id} (${bug.title}) simply`);
    setContextOpen(false);
  }

  function pickSuggestion(item: Suggestion) {
    if (item.prefill) setInput(item.prompt);
    else void sendMessage(item.prompt);
  }

  const empty = !loadingChat && messages.length === 0;
  const lastReplyIndex = messages.map((msg) => msg.role).lastIndexOf("assistant");
  const tree: TreeNode[] = project?.tree || [];

  const composer = (large: boolean) => (
    <Composer
      value={input}
      onChange={setInput}
      onSend={() => void sendMessage(input)}
      mode={mode}
      onModeChange={setMode}
      onAttach={(file) => void attachFile(file)}
      onMic={toggleMic}
      listening={listening}
      micSupported={micSupported}
      busy={busy}
      attaching={attaching}
      large={large}
    />
  );

  return (
    <div className="relative -mx-5 -my-6 flex h-[calc(100dvh-3.5rem)] min-h-[520px] overflow-hidden">
      <ChatSidebar
        open={sidebarOpen}
        onToggle={() => setSidebarOpen((v) => !v)}
        conversations={conversations}
        loading={loadingChat && conversations.length === 0}
        activeId={activeId}
        projectId={projectId}
        coderId={user?.coder_id || ""}
        initials={user ? initials : "G"}
        name={user?.full_name || "Guest"}
        onNewChat={newChat}
        onOpen={selectConversation}
        onRename={(id) => void renameChat(id)}
        onDelete={(id) => void deleteChat(id)}
      />

      <section className="relative flex min-w-0 flex-1 flex-col bg-cream">
        <header className="flex items-center gap-2 px-4 py-3">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="grid h-9 w-9 place-items-center rounded-full hover:bg-panel md:hidden"
            aria-label="Open chats"
          >
            <MenuIcon className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{standalone ? "General chat" : project?.name || "Your project"}</p>
            <p className="truncate text-xs text-mist">
              {standalone ? "Paste code or attach a file and I'll check it" : "Ask about this project. Nothing changes until you approve."}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {standalone ? (
              <select
                value=""
                onChange={(e) => e.target.value && navigate(`/p/${e.target.value}/assistant`)}
                className="h-9 max-w-[11rem] rounded-full border border-line bg-panel px-3 text-sm text-ink hover:border-ink"
                aria-label="Chat about one of your projects"
              >
                <option value="">{myProjects.length ? "Use a project…" : "No projects yet"}</option>
                {myProjects.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            ) : (
              <>
                <Link to="/assistant" className="hidden h-9 items-center rounded-full border border-line bg-panel px-3 text-sm hover:border-ink sm:flex">
                  General chat
                </Link>
                <button
                  type="button"
                  onClick={() => setContextOpen((v) => !v)}
                  className="h-9 whitespace-nowrap rounded-full border border-line bg-panel px-3 text-sm text-ink hover:border-ink xl:hidden"
                  aria-expanded={contextOpen}
                >
                  Context
                </button>
              </>
            )}
          </div>
        </header>

        <LayoutGroup>
          {loadingChat ? (
            <div className="mx-auto w-full max-w-3xl flex-1 space-y-5 px-4 py-6" aria-label="Loading conversation">
              <div className="skeleton ml-auto h-10 w-2/5" />
              <div className="space-y-2">
                <div className="skeleton h-4 w-11/12" />
                <div className="skeleton h-4 w-4/5" />
                <div className="skeleton h-4 w-3/5" />
              </div>
              <div className="skeleton ml-auto h-10 w-1/3" />
            </div>
          ) : empty ? (
            <div className="relative flex flex-1 flex-col items-center justify-center overflow-auto px-4 pb-10">
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center" aria-hidden="true">
                <div className="breathing-glow h-[420px] w-[min(720px,100%)] rounded-full" />
              </div>
              <motion.h1
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="relative mb-8 text-center text-3xl font-semibold leading-tight tracking-tight sm:text-4xl"
              >
                Hi {firstName}, I'm FixPilot.
                <span className="block text-ink/80">What should we fix today?</span>
              </motion.h1>
              <div className="relative w-full max-w-2xl">{composer(true)}</div>
              {error && <p className="relative mt-3 text-sm text-bug">{error}</p>}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.25, duration: 0.4 }}
                className="relative mt-6 grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2"
              >
                {suggestions.map((chip) => (
                  <button
                    key={chip.title}
                    type="button"
                    onClick={() => pickSuggestion(chip)}
                    className="rounded-2xl border border-line bg-panel px-4 py-3 text-left transition hover:-translate-y-0.5 hover:border-ink hover:shadow-card"
                  >
                    <span className="block text-sm font-semibold">{chip.title}</span>
                    <span className="mt-0.5 block truncate text-xs text-mist">{chip.prompt.split("\n")[0]}</span>
                  </button>
                ))}
              </motion.div>
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-auto px-4">
                <div className="mx-auto w-full max-w-3xl space-y-6 py-4">
                  <AnimatePresence initial={false}>
                    {messages.map((msg, index) => (
                      <motion.div
                        key={msg.id}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.25 }}
                      >
                        <MessageBubble
                          msg={msg}
                          projectId={projectId}
                          canRegenerate={index === lastReplyIndex && !busy}
                          onApprove={(id) => void decidePatch(id, "approve")}
                          onReject={(id) => void decidePatch(id, "reject")}
                          onRegenerate={() => regenerate(index)}
                          onFeedback={(value) => void sendFeedback(msg.id, value)}
                        />
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  {busy && messages[messages.length - 1]?.content && (
                    <div className="pl-10">
                      <ThinkingDots />
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>
              </div>
              <div className="px-4 pb-4 pt-2">
                <div className="mx-auto w-full max-w-3xl">
                  {error && <p className="mb-2 text-sm text-bug">{error}</p>}
                  {composer(false)}
                  <p className="mt-2 text-center text-xs text-mist">
                    FixPilot can be wrong. Patches are only applied after you approve them.
                  </p>
                </div>
              </div>
            </>
          )}
        </LayoutGroup>

        <AnimatePresence>
          {toast && (
            <motion.div
              role="alert"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 16 }}
              className="absolute bottom-24 left-1/2 z-40 flex w-[min(92%,32rem)] -translate-x-1/2 items-start gap-3 rounded-2xl border border-bug bg-panel px-4 py-3 text-sm text-ink shadow-card"
            >
              <span aria-hidden="true">⚠️</span>
              <span className="flex-1">{toast}</span>
              <button type="button" onClick={() => setToast("")} className="font-medium" aria-label="Dismiss">
                ✕
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      {!standalone && (
        <aside
          className={`z-30 w-72 shrink-0 flex-col border-l border-line bg-panel ${
            contextOpen ? "absolute inset-y-0 right-0 flex shadow-card" : "hidden"
          } xl:static xl:flex xl:shadow-none`}
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div>
              <p className="text-sm font-semibold">Project context</p>
              <p className="text-xs text-mist">Tap a bug to ask about it</p>
            </div>
            <button type="button" onClick={() => setContextOpen(false)} className="text-sm xl:hidden" aria-label="Close context">
              ✕
            </button>
          </div>
          <div className="max-h-[45%] overflow-auto border-b border-line p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-mist">Bugs</p>
            {bugs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-line p-3 text-xs text-mist">
                No findings yet.{" "}
                <Link to={`/p/${projectId}/scan`} className="font-medium text-ink underline">
                  Run a scan
                </Link>{" "}
                or ask me to find bugs.
              </div>
            ) : (
              <ul className="space-y-1.5">
                {bugs.map((bug) => (
                  <li key={bug.id}>
                    <button
                      type="button"
                      onClick={() => attachBug(bug)}
                      className="w-full rounded-xl border border-line bg-cream px-3 py-2 text-left text-xs hover:border-ink"
                    >
                      <span className="font-medium">{bug.title}</span>
                      <span className="mt-0.5 block font-mono text-[11px] text-mist">
                        {bug.file} · {bug.severity}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex-1 overflow-auto p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-mist">Files</p>
            {tree.length > 0 ? (
              <FileTree nodes={tree} />
            ) : project ? (
              <p className="text-xs text-mist">No files to show yet.</p>
            ) : (
              <div className="skeleton h-24" />
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
