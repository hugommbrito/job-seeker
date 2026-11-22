# job-seeker

A self-hosted job-search assistant. Django API in `backend/`, React client in `web/`. The design
is in `docs/planning/02-implementation-plan.md`; read the section for the phase you are working
on before writing code. Later decisions are in `docs/adr/`.

## Project rules

These apply to every phase. They come from the implementation plan, section 2.

1. **No personal data in git, ever.** Real CVs, emails, labels, eval output and private context
   live in `private/` (git-ignored). Fixtures are synthetic and use placeholder companies.
   Screenshots come only from the demo tenant. Public docs, test names, ADRs and commit messages
   never refer to a real person's job search.
2. **Nothing is discarded silently.** Every eliminated posting records a machine-readable
   reason. An undeterminable fact is tri-state (`unknown`) and never eliminates.
3. **No `if user_id == ...`.** Anything that differs between users is a database row validated
   by Pydantic on read. No profile is defined in code.
4. **The model proposes, code decides, a person confirms.** The model returns categorical
   verdicts with verbatim quotes; the score is computed in code from profile weights. An email
   never changes a status without approval.
5. **No invented experience.** Every generated CV bullet cites its source bullets and inherits
   the lowest evidence level among them (`hands_on`, `led`, `supervised`).
6. **Posting and email text is untrusted data** in every sink, not only prompts: model calls
   over it have no tools and schema-validated output; the UI renders it as text; outbound
   fetches are guarded.
7. **Official public APIs only.** No scraping of LinkedIn or Indeed. Identifiable User-Agent, a
   measured gap per source, an immediate pause on 429 or 403, no CAPTCHA or login workarounds.
8. **A model failure never drops work.** No key, an error or a refusal leaves the item marked as
   not evaluated.
9. **English everywhere:** code, comments, docs, UI, commits. Commits read "Do X, because Y".
   Comments explain why.

## Before you commit

- The git hooks (`make setup` enables them) refuse personal data, saved documents and personal
  commit emails. Never bypass them with `--no-verify`; if a hook fires, the content is the
  problem. Hook output never echoes what matched, so read the file it names.
- `private/` holds the owner's context and seed documents. Read it when a task needs it; never
  copy from it into anything tracked, including test names and commit messages.
- Record a decision that changes or adds to the plan as a short ADR in `docs/adr/`. Do not edit
  `docs/planning/`.

## Commands

`make help` lists them. The ones you need most:

```sh
make db-up && make migrate   # local Postgres, then migrations as the schema owner
make test                    # backend (pytest) and web (vitest)
make check                   # everything CI runs
make api-types               # after any change to an API route or schema
```

Backend commands read `.env` through `uv run --env-file`. Run pytest from `backend/` with
`uv run --env-file ../.env pytest`. pnpm is pinned in `web/package.json`; use `corepack pnpm`.

## Tenancy: the rules the tests enforce

Every table is tenant, catalog or framework. The meta-test fails on a table that is none.

**Adding a per-user table**

1. Inherit `apps.tenancy.models.TenantModel` (it adds the `user` foreign key).
2. In the migration that creates the table, add `sql.enable_tenant_rls("<table>")` from
   `apps.tenancy.sql` and depend on `("tenancy", "0001_grants")`.
3. Register a canary seeder in `backend/tests/canaries.py`.

**Adding a shared table**: inherit `CatalogModel`. It must not have a user column.

**Acting as a user outside a request** (tasks, management commands): wrap the work in
`tenant_context(user_id)`. It is a database transaction, so do no network I/O inside it. It
cannot be nested for a different user.

**Adding a route**: mark the view `@demo_readable` or `@demo_denied` (`apps.accounts.demo`),
below the route decorator. An unmarked route fails `test_route_classification`. A route with a
path parameter also needs an example path in `backend/tests/routes.py`, so the isolation suite
can call it. Then run `make api-types`.

**Tests run as the `app` role**, the one row-level security binds. Do not change the suite to
connect as the owner to make something pass; a test that needs the owner is testing the wrong
thing. Raw SQL in a test that expects a refusal must match Postgres's message, not just "any
database error".

## Conventions

- Python: ruff (lint and format) and mypy in strict mode. Tests are not type-checked.
- Settings come from the environment (`backend/config/settings.py`); `NAME_FILE` reads a secret
  from a file. Tests use `config.settings_test`, which pins the values that change behaviour.
- The web client talks to the API only through `web/src/api/client.ts`. Only a 401 ends the
  session on the client; a 403 does not.
- `web/src/components/ui/` is generated by the shadcn CLI; add components with
  `corepack pnpm dlx shadcn@latest add <name>` and leave them as generated.
- Do not log email addresses, request bodies or posting text.
