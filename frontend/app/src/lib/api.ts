const TOKEN_KEY = "cctv_token"

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail
  // FastAPI's default 422 validation-error shape is a list of {loc, msg, ...}
  // objects, not a string -- `new Error(detail)` on that renders as an
  // unhelpful "[object Object]"-ish message.
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ") || fallback
  }
  return fallback
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json")
  }

  const res = await fetch(`/api${path}`, { ...options, headers })

  // A 401 from the login endpoint itself means "wrong credentials," not "your
  // session expired" -- it must surface the real backend message instead of
  // being swallowed into the generic session-expiry handling below.
  if (res.status === 401 && path !== "/auth/login") {
    setToken(null)
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login"
    }
    throw new Error("Not authenticated")
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      detail = formatDetail(body.detail, detail)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }

  const contentType = res.headers.get("content-type") ?? ""
  if (contentType.includes("application/json")) {
    return res.json() as Promise<T>
  }
  return undefined as T
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
}

export function authHeader(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
