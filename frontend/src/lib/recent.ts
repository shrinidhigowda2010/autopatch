/**
 * Remember what this browser opened, so guests (who have no account) still see
 * their own projects and chats on the Dashboard, History and Assistant pages.
 */

const PROJECTS_KEY = "fixpilot_recent_projects";
const CHATS_KEY = "fixpilot_recent_chats";
const LIMIT = 50;

function read(key: string): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function remember(key: string, id: string): void {
  if (!id) return;
  const next = [id, ...read(key).filter((item) => item !== id)].slice(0, LIMIT);
  try {
    localStorage.setItem(key, JSON.stringify(next));
  } catch {
    // Storage can be full or blocked; the feature just degrades.
  }
}

export const rememberProject = (id: string) => remember(PROJECTS_KEY, id);
export const recentProjectIds = () => read(PROJECTS_KEY);
export const rememberChat = (id: string) => remember(CHATS_KEY, id);
export const recentChatIds = () => read(CHATS_KEY);
