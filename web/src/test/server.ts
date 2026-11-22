import { vi } from "vitest";

type Handler = (request: Request) => Response | Promise<Response>;

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function empty(status = 204): Response {
  return new Response(null, { status });
}

/**
 * Replace `fetch` with a table of "METHOD /path" handlers and return the requests it received.
 * A request with no handler fails the test, so nothing reaches the network by accident.
 */
export function serve(handlers: Record<string, Handler>): Request[] {
  const received: Request[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(new URL(input, location.origin), init);
      received.push(request.clone());
      const key = `${request.method} ${new URL(request.url).pathname}`;
      const handler = handlers[key];
      if (!handler) throw new Error(`Unexpected request: ${key}`);
      return handler(request);
    }),
  );
  return received;
}
