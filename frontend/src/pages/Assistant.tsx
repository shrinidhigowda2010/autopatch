import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { api } from "../api";
import DiffView from "../components/DiffView";
import FileTree from "../components/FileTree";
import Logo from "../components/Logo";
import { getStoredToken } from "../token";
import type { Project, TreeNode } from "../types";

interface Conversation {
  id: string;
  title: string;
  language: string;
  updated_at: string;
}

interface ToolStep {
  name: string;
  label: string;
  status: string;
}

interface PatchCard {
  patch_id: string;
  bug_id: string;
  title: string;
  file: string;
  status: string;
  diff: string;
  before_code: string;
  after_code: string;
  confidence: number;
}

interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_steps?: ToolStep[];
  patches?: PatchCard[];
  streaming?: boolean;
}

interface BugRow {
  id: string;
  title: string;
  severity: string;
  file: string;
}

const QUICK = [
  "Find all bugs in this project",
  "Explain this bug simply",
  "Why did this test fail?",
  "Is this fix safe?",
  "Make this code faster",
  "Write tests for this function",
];

function authHeader(): HeadersInit {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function Assistant() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [project, setProject] = useState<Project | null>(null);
  const [bugs, setBugs] = useState<BugRow[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState<"en" | "kn" | "hi">("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [typing, setTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const bugParam = params.get("bug") || "";

  const loadConversations = useCallback(async () => {
    if (!projectId) return;
    const body = await api<{ conversations: Conversation[] }>(
      `/api/assistant/conversations?project_id=${projectId}`,
    );
    setConversations(body.conversations);
    return body.conversations;
  }, [projectId]);

  const openConversation = useCallback(async (id: string) => {
    const body = await api<Conversation & { messages: ChatMsg[] }>(`/api/assistant/conversations/${id}`);
    setActiveId(id);
    setLanguage((body.language as "en" | "kn" | "hi") || "en");
    setMessages(
      body.messages.map((msg) => ({
        ...msg,
        role: msg.role === "user" ? "user" : "assistant",
      })),
    );
  }, []);

  const ensureConversation = useCallback(async () => {
    const list = (await loadConversations()) || [];
    if (list[0]) {
      await openConversation(list[0].id);
      return list[0].id;
    }
    const created = await api<Conversation>("/api/assistant/conversations", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, title: "New chat", language }),
    });
    await loadConversations();
    await openConversation(created.id);
    return created.id;
  }, [loadConversations, openConversation, projectId, language]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    api<Project>(`/api/projects/${projectId}`)
      .then((proj) => {
        if (!cancelled) setProject(proj);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    api<{ bugs: BugRow[]; scan: { id: string } | null }>(`/api/projects/${projectId}/dashboard`)
      .then((dash) => {
        if (!cancelled) setBugs(dash.bugs || []);
      })
      .catch(() => undefined);
    ensureConversation().catch((err: Error) => {
      if (!cancelled) setError(err.message);
    });
    return () => {
      cancelled = true;
    };
    // Intentionally only when the project changes — language edits should not reset the chat.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (bugParam) {
      setInput((prev) => (prev.includes(bugParam) ? prev : `Explain bug ${bugParam} simply`));
    }
  }, [bugParam]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  async function newChat() {
    const created = await api<Conversation>("/api/assistant/conversations", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, title: "New chat", language }),
    });
    await loadConversations();
    setMessages([]);
    setActiveId(created.id);
  }

  async function renameChat(id: string) {
    const title = window.prompt("Rename chat", conversations.find((c) => c.id === id)?.title || "Chat");
    if (!title) return;
    await api(`/api/assistant/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    await loadConversations();
  }

  async function deleteChat(id: string) {
    if (!window.confirm("Delete this conversation?")) return;
    await api(`/api/assistant/conversations/${id}`, { method: "DELETE" });
    const list = (await loadConversations()) || [];
    if (id === activeId) {
      if (list[0]) await openConversation(list[0].id);
      else {
        setActiveId("");
        setMessages([]);
        await newChat();
      }
    }
  }

  async function sendMessage(text: string) {
    if (!text.trim() || busy) return;
    let convId = activeId;
    if (!convId) convId = await ensureConversation();
    setBusy(true);
    setTyping(true);
    setError("");
    const userMsg: ChatMsg = { id: `local-${Date.now()}`, role: "user", content: text.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    const assistantId = `stream-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", tool_steps: [], patches: [], streaming: true },
    ]);

    try {
      const response = await fetch(`/api/assistant/conversations/${convId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({
          content: text.trim(),
          language,
          bug_id: bugParam || undefined,
        }),
      });
      if (!response.ok || !response.body) {
        throw new Error("Could not reach the assistant.");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
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
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId ? { ...msg, content: msg.content + String(data.text || "") } : msg,
              ),
            );
          } else if (data.type === "tool") {
            const step = data as unknown as ToolStep;
            setMessages((prev) =>
              prev.map((msg) => {
                if (msg.id !== assistantId) return msg;
                const steps = [...(msg.tool_steps || [])];
                const idx = steps.findIndex((s) => s.name === step.name && s.label === step.label);
                if (idx >= 0) steps[idx] = step;
                else steps.push(step);
                return { ...msg, tool_steps: steps };
              }),
            );
          } else if (data.type === "patch") {
            const patch = data.patch as PatchCard;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, patches: [...(msg.patches || []), patch] }
                  : msg,
              ),
            );
          } else if (data.type === "saved") {
            const saved = data.message as ChatMsg;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId
                  ? {
                      ...saved,
                      role: "assistant",
                      streaming: false,
                    }
                  : msg,
              ),
            );
            await loadConversations();
          } else if (data.type === "error") {
            setError(String(data.detail || "Assistant error"));
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assistant failed.");
      setMessages((prev) => prev.filter((msg) => msg.id !== assistantId));
    } finally {
      setBusy(false);
      setTyping(false);
      setMessages((prev) => prev.map((msg) => (msg.id === assistantId ? { ...msg, streaming: false } : msg)));
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  function insertBug(bug: BugRow) {
    setParams({ bug: bug.id });
    setInput(`Explain bug ${bug.id} (${bug.title}) simply`);
  }

  async function decidePatch(patchId: string, action: "approve" | "reject") {
    if (action === "approve") {
      await api(`/api/patches/${patchId}/approve`, { method: "POST" });
    } else {
      await api(`/api/patches/${patchId}/reject`, {
        method: "POST",
        body: JSON.stringify({ note: "Rejected from Repairo Assistant" }),
      });
    }
    setMessages((prev) =>
      prev.map((msg) => ({
        ...msg,
        patches: (msg.patches || []).map((p) =>
          p.patch_id === patchId ? { ...p, status: action === "approve" ? "applied" : "rejected" } : p,
        ),
      })),
    );
  }

  const tree: TreeNode[] = project?.tree || [];

  return (
    <div className="-mx-5 -my-6 flex h-[calc(100vh-3.5rem)] min-h-[560px] flex-col md:flex-row">
      {/* Conversations */}
      <aside className="flex w-full flex-col border-b border-line bg-panel md:w-64 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-3">
          <div>
            <p className="text-sm font-semibold">Repairo Assistant</p>
            <p className="text-xs text-mist">Project chats</p>
          </div>
          <button type="button" onClick={() => void newChat()} className="btn-secondary px-2 py-1 text-xs">
            New chat
          </button>
        </div>
        <ul className="flex-1 overflow-auto p-2">
          {conversations.map((conv) => (
            <li key={conv.id} className="mb-1">
              <button
                type="button"
                onClick={() => void openConversation(conv.id)}
                className={`w-full rounded-xl px-2 py-2 text-left text-sm ${
                  conv.id === activeId ? "bg-ink text-cream" : "hover:bg-cream"
                }`}
              >
                <span className="line-clamp-2">{conv.title}</span>
              </button>
              <div className="mt-1 flex gap-1 px-1">
                <button type="button" className="text-[11px] text-mist hover:underline" onClick={() => void renameChat(conv.id)}>
                  Rename
                </button>
                <button type="button" className="text-[11px] text-mist hover:underline" onClick={() => void deleteChat(conv.id)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      </aside>

      {/* Chat */}
      <section className="flex min-w-0 flex-1 flex-col bg-cream">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
          <div>
            <h1 className="text-lg font-semibold">Discuss your code</h1>
            <p className="text-sm text-mist">{project?.name || projectId}</p>
          </div>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as "en" | "kn" | "hi")}
            className="rounded-xl border border-line bg-panel px-2 py-1.5 text-sm"
            aria-label="Assistant language"
          >
            <option value="en">English</option>
            <option value="kn">ಕನ್ನಡ</option>
            <option value="hi">हिन्दी</option>
          </select>
        </header>

        <div className="flex-1 space-y-4 overflow-auto px-4 py-4">
          {messages.length === 0 && (
            <div className="rounded-2xl border border-line bg-panel p-4 text-sm text-mist">
              Ask about bugs, tests, or fixes. The assistant can scan files and propose patches — nothing is applied
              until you Approve.
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              msg={msg}
              projectId={projectId}
              onApprove={(id) => void decidePatch(id, "approve")}
              onReject={(id) => void decidePatch(id, "reject")}
            />
          ))}
          {typing && (
            <div className="flex items-center gap-2 text-sm text-mist">
              <Logo markOnly className="h-6 w-auto" />
              <span className="animate-pulse">Repairo is thinking…</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-line px-4 py-2">
          <div className="mb-2 flex flex-wrap gap-2">
            {QUICK.map((chip) => (
              <button
                key={chip}
                type="button"
                disabled={busy}
                onClick={() => void sendMessage(chip)}
                className="rounded-full border border-line bg-panel px-3 py-1 text-xs text-mist hover:border-ink"
              >
                {chip}
              </button>
            ))}
          </div>
          {error && <p className="mb-2 text-sm text-bug">{error}</p>}
          <form onSubmit={onSubmit} className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about this project…"
              className="flex-1 rounded-2xl border border-line bg-panel px-3 py-2.5"
              disabled={busy}
            />
            <button type="submit" disabled={busy || !input.trim()} className="btn-primary disabled:opacity-60">
              Send
            </button>
          </form>
        </div>
      </section>

      {/* Context panel */}
      <aside className="hidden w-72 flex-col border-l border-line bg-panel lg:flex">
        <div className="border-b border-line px-3 py-3">
          <p className="text-sm font-semibold">Project context</p>
          <p className="text-xs text-mist">Click a bug to attach it</p>
        </div>
        <div className="max-h-[40%] overflow-auto border-b border-line p-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-mist">Bugs</p>
          <ul className="space-y-1">
            {bugs.length === 0 && <li className="text-xs text-mist">No findings yet — run a scan.</li>}
            {bugs.map((bug) => (
              <li key={bug.id}>
                <button
                  type="button"
                  onClick={() => insertBug(bug)}
                  className="w-full rounded-xl border border-line bg-cream px-2 py-1.5 text-left text-xs hover:border-ink"
                >
                  <span className="font-medium">{bug.title}</span>
                  <span className="mt-0.5 block font-mono text-[10px] text-mist">
                    {bug.file} · {bug.severity}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex-1 overflow-auto p-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-mist">Files</p>
          {tree.length > 0 ? <FileTree nodes={tree} /> : <p className="text-xs text-mist">No tree yet.</p>}
          <Link to={`/p/${projectId}/fix`} className="mt-4 inline-block text-xs font-medium underline-offset-2 hover:underline">
            Open Fix page →
          </Link>
        </div>
      </aside>
    </div>
  );
}

function MessageBubble({
  msg,
  projectId,
  onApprove,
  onReject,
}: {
  msg: ChatMsg;
  projectId: string;
  onApprove: (patchId: string) => void;
  onReject: (patchId: string) => void;
}) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} gap-2`}>
      {!isUser && <Logo markOnly className="mt-1 h-8 w-auto shrink-0" />}
      <div className={`max-w-[85%] space-y-2 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-3 py-2 text-sm shadow-emboss ${
            isUser ? "bg-ink text-cream" : "border border-line bg-panel text-ink"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{msg.content}</p>
          ) : (
            <Markdown body={msg.content || (msg.streaming ? "…" : "")} />
          )}
        </div>
        {(msg.tool_steps || []).map((step, index) => (
          <div key={`${step.name}-${index}`} className="rounded-xl border border-line bg-cream px-3 py-2 text-xs text-mist shadow-emboss">
            {step.name === "run_tests" ? "🧪" : step.name.includes("scan") || step.name.includes("search") ? "🔍" : "✅"}{" "}
            {step.label}
          </div>
        ))}
        {(msg.patches || []).map((patch) => (
          <div key={patch.patch_id} className="card-3d max-w-xl p-3">
            <p className="text-sm font-semibold">{patch.title}</p>
            <p className="font-mono text-xs text-mist">
              {patch.file} · {patch.status} · {Math.round(patch.confidence * 100)}%
            </p>
            <div className="mt-2">
              <DiffView before={patch.before_code} after={patch.after_code} diff={patch.diff} />
            </div>
            {patch.status === "proposed" && (
              <div className="mt-2 flex gap-2">
                <button type="button" className="btn-primary px-3 py-1.5 text-xs" onClick={() => onApprove(patch.patch_id)}>
                  Approve
                </button>
                <button type="button" className="btn-secondary px-3 py-1.5 text-xs" onClick={() => onReject(patch.patch_id)}>
                  Reject
                </button>
                <Link to={`/p/${projectId}/fix`} className="btn-secondary px-3 py-1.5 text-xs">
                  Edit on Fix page
                </Link>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Markdown({ body }: { body: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const code = String(children).replace(/\n$/, "");
          if (match) {
            return (
              <div className="relative my-2 overflow-hidden rounded-xl border border-line">
                <button
                  type="button"
                  className="absolute right-2 top-2 z-10 rounded-lg border border-line bg-panel px-2 py-0.5 text-[10px]"
                  onClick={() => void navigator.clipboard.writeText(code)}
                >
                  Copy
                </button>
                <SyntaxHighlighter style={oneLight} language={match[1]} PreTag="div">
                  {code}
                </SyntaxHighlighter>
              </div>
            );
          }
          return (
            <code className="rounded bg-cream px-1 font-mono text-[0.85em]" {...props}>
              {children}
            </code>
          );
        },
        a({ href, children }) {
          return (
            <a href={href} className="underline" target="_blank" rel="noreferrer">
              {children}
            </a>
          );
        },
      }}
    >
      {body}
    </ReactMarkdown>
  );
}
