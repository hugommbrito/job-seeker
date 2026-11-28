# 0011. Capture from a URL and the Django admin move to Phase 2

2026-11-25. Accepted. Moves two Phase 1 items of the implementation plan, section 7, to Phase 2:
"Capture: paste text or a URL" (the URL half) and "Admin registered for catalog and operations
models".

## Context

Capture from a URL means resolving a known applicant-tracking-system link through that system's
API (Greenhouse, Lever, Ashby) and, for any other site, a guarded fetch: https only, public
addresses only, re-checked after every redirect (section 3.5). Phase 2 builds connectors for the
same three systems, with normalisation and fixture tests, and ports the polite HTTP module from
the rental monitor. Writing both parsers now would mean writing them twice.

The admin needs a site that understands this project's roles (the user model has no `is_staff`
or permissions), a URLconf served only on an internal host, and the route-classification test
extended to that URLconf. In Phase 1 the only catalog and operations tables are the task-run log,
which `/api/operations` already reports, and the Telegram polling offset, which nobody edits.

## Decision

- Phase 1 captures by pasted text. A posting's URL can be given alongside the text and is kept.
  The URL half arrives in Phase 2 on top of the connectors, with the guarded fetch for other
  sites; LinkedIn and Indeed links will be refused with the same prompt to paste.
- The admin arrives in Phase 2 with the shared catalog it exists to edit (companies, offices,
  sources), behind the role-aware site and the internal-host URLconf described above.

## Consequences

- Capturing a posting takes a copy and paste of its text, on every site, for now.
- Phase 2 carries two more items; until then the owner reads operations through
  `/api/operations` and edits nothing shared, as nothing shared exists yet.
