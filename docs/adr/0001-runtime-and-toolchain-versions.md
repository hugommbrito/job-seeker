# 0001. Runtime and toolchain versions

2026-11-21. Accepted. Settles the open item "exact Django and CPython versions" in the
implementation plan, section 10.

## Context

The plan says to use the current stable Django and CPython at implementation time. On the day
Phase 0 was implemented, several components had a release only days or weeks old, and some tools
this project depends on did not support the newest major version of what they build on.

## Decision

| Component | Chosen | Newest available | Why not the newest |
| --- | --- | --- | --- |
| Django | 6.1 | 6.1 | |
| Django Ninja | 1.8 | 1.8 | |
| CPython | 3.14 | 3.15 (four weeks old) | Binary wheels for the database driver, Pydantic's core and Argon2 were not verified on 3.15 |
| PostgreSQL | 18 | 19.0 (two days old) | A database major version is adopted after its first patch releases, and the pgvector image for it is equally new |
| pgvector | 0.8 | 0.8 | |
| Node.js | 24 | 26 | 24 still bundles corepack, which pins the package manager from `package.json` |
| pnpm | 12 | 12 | |
| TypeScript | 5.9 | 7.0 | `openapi-typescript` supports 5.x only and `typescript-eslint` supports up to 6.0 |
| Vite / React / Tailwind | 8 / 19 / 4 | same | |

Exact versions are in `backend/uv.lock` and `web/pnpm-lock.yaml`.

## Consequences

- CPython, PostgreSQL and TypeScript each need a follow-up when the reason above no longer holds.
  The TypeScript upgrade is blocked on the two tools named, not on this codebase.
- The Postgres 18 image stores data under `/var/lib/postgresql` (a version-specific
  subdirectory), not `/var/lib/postgresql/data`. Volume mounts in this repository use the new
  path; a mount at the old path would silently keep data inside the container.
