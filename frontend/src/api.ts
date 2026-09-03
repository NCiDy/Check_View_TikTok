let csrfToken = "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function setCsrfToken(value?: string | null) {
  csrfToken = value || "";
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken && !["GET", "HEAD"].includes((options.method || "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    cache: "no-store",
    headers,
  });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = (payload as { detail?: string } | null)?.detail || `Lỗi HTTP ${response.status}`;
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized", { detail }));
    }
    throw new ApiError(detail, response.status);
  }
  return payload as T;
}

export function notify(message: string, type: "success" | "error" | "info" = "info") {
  window.dispatchEvent(new CustomEvent("app:toast", { detail: { message, type } }));
}
