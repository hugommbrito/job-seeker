import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type User = components["schemas"]["UserOut"];

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
const CSRF_COOKIE = "csrftoken";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function readCookie(name: string): string | null {
  for (const part of document.cookie.split("; ")) {
    const separator = part.indexOf("=");
    if (separator !== -1 && part.slice(0, separator) === name) {
      return decodeURIComponent(part.slice(separator + 1));
    }
  }
  return null;
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

/** Run `listener` whenever the server says the session is gone. Returns the unsubscribe. */
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

async function csrfToken(): Promise<string | null> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  // The session cookie is HttpOnly; the CSRF cookie is deliberately readable, and this route
  // exists only to set it.
  await globalThis.fetch("/api/auth/csrf", { credentials: "same-origin" });
  return readCookie(CSRF_COOKIE);
}

const middleware: Middleware = {
  async onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method.toUpperCase())) {
      const token = await csrfToken();
      if (token) request.headers.set("X-CSRFToken", token);
    }
    return request;
  },
  onResponse({ response }) {
    // Only 401 ends the session on this side. 403 means "you may not do this": the demo
    // account gets it on every route that is not open to it, and must stay signed in.
    if (response.status === 401) {
      for (const listener of unauthorizedListeners) listener();
    }
    return response;
  },
};

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: "same-origin",
  // Looked up on every call, so tests can replace the global.
  fetch: (request) => globalThis.fetch(request),
});
api.use(middleware);
