# 0005. The web scaffold has no router and no service worker yet

2026-11-21. Accepted. Narrows the Phase 0 web scaffold; the plan's stack lists a PWA without
saying which phase adds its parts.

## Context

Phase 0 has two screens: sign in, and an empty app. The plan's stack for the web client includes
client-side routing concerns (filters in the URL), drag and drop, and a PWA with web push.

## Decision

Each of those arrives with the phase that first uses it, the same rule the plan applies to
backend services:

- No router in Phase 0. Which of the two screens shows is decided by whether there is a session.
  Phase 1 adds routes together with the board and the table view.
- No service worker in Phase 0. The web manifest is in place; the service worker comes in
  Phase 2 with web push, which is its first real use. A service worker that caches the shell of
  an authenticated app needs an update strategy, and there is nothing to design it against yet.
- No drag-and-drop library until the kanban exists.

## Consequences

- The Phase 0 bundle and its dependency list stay small and every dependency has a caller.
- The server's catch-all route already serves the entry page for any client-side path, so adding
  a router later needs no backend change.
