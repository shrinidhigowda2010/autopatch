export class ApiError extends Error {}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      /* the body was not JSON */
    }
    throw new ApiError(detail);
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    return response.json() as Promise<T>;
  }
  return response as unknown as T;
}
