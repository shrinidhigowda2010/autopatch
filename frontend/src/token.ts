const TOKEN_KEY = "fixpilot_token";
const GUEST_KEY = "fixpilot_guest";

// Earlier builds stored these under the old AutoPatch name; move them so nobody is signed out.
const LEGACY_KEYS: [string, string][] = [
  ["autopatch_token", TOKEN_KEY],
  ["autopatch_guest", GUEST_KEY],
];

try {
  for (const [old, current] of LEGACY_KEYS) {
    const value = localStorage.getItem(old);
    if (value !== null) {
      if (localStorage.getItem(current) === null) localStorage.setItem(current, value);
      localStorage.removeItem(old);
    }
  }
} catch {
  /* storage unavailable */
}

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function setGuestFlag(value: boolean): void {
  try {
    if (value) localStorage.setItem(GUEST_KEY, "1");
    else localStorage.removeItem(GUEST_KEY);
  } catch {
    /* ignore */
  }
}

export function getGuestFlag(): boolean {
  try {
    return localStorage.getItem(GUEST_KEY) === "1";
  } catch {
    return false;
  }
}

export { TOKEN_KEY, GUEST_KEY };
