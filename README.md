# job-seeker

A self-hosted job-search assistant for Toronto. It collects postings from public
applicant-tracking-system APIs, ranks each one against a user's profile, tracks applications on
a kanban, proposes status changes from application emails, and builds a tailored CV per posting.

Each user's data is isolated from every other user's, and a public guest account can browse a
synthetic demo on the same instance.

## Status

**Phase 0 (foundation) is implemented; nothing is deployed yet.** What exists today is the base
everything else stands on: accounts and sessions, per-user isolation enforced by the database,
the checks that keep it honest, and an empty app that two people can sign in to. Collection,
ranking, the tracker and the CV builder are the next phases.

The full design is in [docs/planning](docs/planning/README.md); decisions taken since are in
[docs/adr](docs/adr/README.md).

## How isolation works

This is the part of Phase 0 worth reading the code for.

- **The database enforces it, not the application.** Every per-user table has row-level security
  enabled and forced, with one policy that compares the row's owner with a transaction-local
  setting. The app connects as a role that owns nothing and cannot bypass the policy, so a query
  that forgets its `WHERE` clause returns the caller's rows and nothing else.
  ([`apps/tenancy`](backend/apps/tenancy))
- **One entry point.** `tenant_context(user_id)` is the only code that sets who a block runs as.
  A middleware wraps every signed-in request in it.
- **The tests connect as the app role.** A suite that ran as the table owner would pass without
  ever exercising a policy. The test database is migrated by the owner and then handed to the
  tests as `app`. ([`tests/conftest.py`](backend/tests/conftest.py))
- **A meta-test reads `pg_catalog`.** Every table must be classified as tenant, catalog or
  framework, and every tenant table must really carry the forced policy. A new table cannot ship
  without that decision. The same rules run against a deployed database with `manage.py verify`.
- **A canary suite crawls every route.** One tenant is seeded with unique strings; no response
  to another tenant, to the guest or to an anonymous visitor may contain one. Routes are found
  by walking the URL resolver, so a new route is covered without being listed.
- **The guest is denied by default.** Every route must state whether the demo account may call
  it; an unmarked route fails the build, and gets 403 at run time.
- **The api refuses to start with the wrong credentials.** A superuser, a role with `BYPASSRLS`
  or the schema owner would make every policy silently irrelevant, so the container checks its
  own role before serving.

## Stack

| | |
| --- | --- |
| Backend | Python 3.14, Django 6.1, Django Ninja (Pydantic, OpenAPI), PostgreSQL 18 with pgvector and `pg_trgm` |
| Web | React 19, Vite, TypeScript, Tailwind 4, shadcn/ui, TanStack Query |
| Contract | The API's OpenAPI schema; the web client's types are generated from it and CI fails if they are stale |
| Delivery | One Docker image with a command per service, deployed with Coolify |

## Repository layout

```
backend/           Django project
  config/          settings, URLs, API wiring
  apps/            one Django app per domain: tenancy, accounts, profiles, operations
  tests/           pytest suite; runs against a real Postgres as the app role
web/               React client
infra/             Dockerfile, compose files, Postgres bootstrap script
scripts/           hygiene checks, smoke test, restore drill
docs/planning/     the design and the decision log
docs/adr/          later decisions
docs/operations/   deploy runbook, restore drill log
private/           git-ignored: personal data never enters the repository
```

## Running it locally

Needs Docker, [uv](https://docs.astral.sh/uv/), and Node 24 with corepack enabled
(`corepack enable`).

```sh
make setup      # git hooks, .env from .env.example, dependencies
make db-up      # Postgres with the roles and extensions created on first start
make migrate    # as the schema owner
make user EMAIL=you@example.org ROLE=owner

make run        # API on http://127.0.0.1:8000
make web        # web client on http://localhost:5173
```

`make help` lists every command.

## Checks

```sh
make check      # lint, types, both test suites, generated API types, production build
make hygiene    # full git history: personal data, stray documents, personal commit emails
make image      # build the production image
```

CI runs the same checks on every push. It holds no secrets.

## Personal data stays out of git

The app handles CVs and application emails, and this repository is public. Three guards keep
them apart, all in [`scripts/hygiene.py`](scripts/hygiene.py): a private denylist of names and
companies checked against file contents, file names and commit messages; a refusal of `.pdf`,
`.eml` and `.html` files outside a short allowlist; and a check that commit emails are no-reply
addresses. Git hooks run them before every commit, and CI runs the last two over the full
history. Fixtures are synthetic and use placeholder companies.

## Deploying

See the [deploy runbook](docs/operations/deploy.md).

## Licence

[MIT](LICENSE).
