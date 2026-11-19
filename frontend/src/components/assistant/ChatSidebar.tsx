import { useState } from "react";
import { Link } from "react-router-dom";
import { ChatIcon, GearIcon, MenuIcon, PlusIcon } from "./icons";

export interface ConversationRow {
  id: string;
  title: string;
  language: string;
  updated_at: string;
}

interface Props {
  open: boolean;
  onToggle: () => void;
  conversations: ConversationRow[];
  loading: boolean;
  activeId: string;
  projectId: string;
  coderId: string;
  initials: string;
  name: string;
  onNewChat: () => void;
  onOpen: (id: string) => void;
  onRename: (id: string) => void;
  onDelete: (id: string) => void;
}

/** Collapsible left rail: new chat, recent chats, settings and who is signed in. */
export default function ChatSidebar({
  open,
  onToggle,
  conversations,
  loading,
  activeId,
  projectId,
  coderId,
  initials,
  name,
  onNewChat,
  onOpen,
  onRename,
  onDelete,
}: Props) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  const railButton = "grid h-10 w-10 place-items-center rounded-full text-ink transition hover:bg-cream";

  return (
    <>
      {/* Dim the chat behind the drawer on phones. */}
      {open && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={onToggle}
          className="absolute inset-0 z-20 bg-ink/20 md:hidden"
        />
      )}
      <aside
        className={`z-30 flex shrink-0 flex-col border-r border-line bg-panel transition-[width] duration-300 ${
          open ? "absolute inset-y-0 left-0 w-64 shadow-card md:static md:shadow-none" : "hidden w-16 md:flex"
        }`}
      >
        <div className={`flex items-center gap-2 px-3 py-3 ${open ? "" : "flex-col"}`}>
          <button type="button" onClick={onToggle} className={railButton} aria-label={open ? "Collapse sidebar" : "Expand sidebar"}>
            <MenuIcon className="h-5 w-5" />
          </button>
          {open && <span className="text-sm font-semibold">FixPilot Assistant</span>}
        </div>

        <div className="px-3">
          <button
            type="button"
            onClick={onNewChat}
            className={`flex items-center gap-2 rounded-full border border-line bg-cream text-sm font-medium text-ink transition hover:border-ink ${
              open ? "w-full px-4 py-2.5" : "h-10 w-10 justify-center"
            }`}
            title="New chat"
          >
            <PlusIcon />
            {open && "New chat"}
          </button>
        </div>

        <div className="mt-4 min-h-0 flex-1 overflow-auto px-2">
          {open && <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-mist">Recent</p>}
          {open && loading && (
            <div className="space-y-2 px-2" aria-label="Loading chats">
              {[0, 1, 2].map((key) => (
                <div key={key} className="skeleton h-8" />
              ))}
            </div>
          )}
          {open && !loading && conversations.length === 0 && (
            <p className="px-2 text-sm text-mist">No chats yet. Your conversations will show up here.</p>
          )}
          <ul className="space-y-1">
            {conversations.map((conv) => (
              <li key={conv.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onOpen(conv.id)}
                  title={conv.title}
                  className={`flex w-full items-center gap-2 rounded-full text-left text-sm transition ${
                    open ? "px-3 py-2" : "mx-auto h-10 w-10 justify-center"
                  } ${conv.id === activeId ? "bg-ink text-cream" : "text-ink hover:bg-cream"}`}
                >
                  <ChatIcon className="h-4 w-4 shrink-0" />
                  {open && <span className="truncate pr-10">{conv.title}</span>}
                </button>
                {open && (
                  <div className="absolute right-2 top-1/2 hidden -translate-y-1/2 gap-1 group-focus-within:flex group-hover:flex">
                    <button
                      type="button"
                      onClick={() => onRename(conv.id)}
                      className="rounded-full bg-panel px-1.5 text-xs text-ink hover:underline"
                      aria-label={`Rename ${conv.title}`}
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(conv.id)}
                      className="rounded-full bg-panel px-1.5 text-xs text-bug hover:underline"
                      aria-label={`Delete ${conv.title}`}
                    >
                      ✕
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative border-t border-line px-3 py-3">
          {settingsOpen && open && (
            <div className="absolute bottom-full left-3 right-3 mb-2 rounded-2xl border border-line bg-panel p-2 text-sm shadow-card">
              <Link to="/profile" className="block rounded-xl px-3 py-2 hover:bg-cream">
                Profile & coder ID
              </Link>
              <Link to={projectId ? `/p/${projectId}/dashboard` : "/dashboard"} className="block rounded-xl px-3 py-2 hover:bg-cream">
                {projectId ? "Project dashboard" : "Dashboard"}
              </Link>
              <Link to={projectId ? `/p/${projectId}/fix` : "/history"} className="block rounded-xl px-3 py-2 hover:bg-cream">
                {projectId ? "Fix page" : "History"}
              </Link>
              <p className="px-3 py-2 text-xs text-mist">Enter sends · Shift+Enter adds a line</p>
            </div>
          )}
          <div className={`flex items-center gap-2 ${open ? "" : "flex-col"}`}>
            <button
              type="button"
              onClick={() => (open ? setSettingsOpen((v) => !v) : onToggle())}
              className={railButton}
              aria-label="Settings"
              aria-expanded={settingsOpen}
            >
              <GearIcon />
            </button>
            <Link
              to="/profile"
              className="flex min-w-0 items-center gap-2 rounded-full hover:bg-cream"
              title={coderId || "Guest"}
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-xs font-semibold text-cream">
                {initials}
              </span>
              {open && (
                <span className="min-w-0 pr-2">
                  <span className="block truncate text-sm font-medium">{name}</span>
                  <span className="block truncate font-mono text-[11px] text-mist">{coderId || "Guest session"}</span>
                </span>
              )}
            </Link>
          </div>
        </div>
      </aside>
    </>
  );
}
