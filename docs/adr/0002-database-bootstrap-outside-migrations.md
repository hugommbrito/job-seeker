# 0002. Roles and extensions are created by a bootstrap script, not by migrations

2026-11-21. Accepted. Refines the implementation plan, section 3.3, which lists "roles, grants,
extensions" and row-level security as hand-written migration operations.

## Context

Three of those four cannot be done from a migration without weakening the design they belong to:

- Creating a login role needs its password. A migration is a file in a public repository.
- Creating roles needs `CREATEROLE`, and creating the `vector` extension needs a superuser. The
  role that runs migrations (`migrator`) is deliberately neither.
- The test database is created fresh on every run by `migrator`, so anything it cannot create
  must already be there.

## Decision

`infra/postgres/bootstrap.sh` runs once per database server, as a superuser, with the passwords
supplied through the environment. It creates the roles (`migrator`, `app`, `backup`, and
`litellm` when asked), the databases, and the `vector` and `pg_trgm` extensions. It installs the
extensions into `template1` first, so every database created afterwards, including each test
database, inherits them. It is idempotent: running it again rotates passwords or adds what is
missing.

Migrations keep everything that needs neither a secret nor a superuser, through the helpers in
`backend/apps/tenancy/sql.py`: the grants to `app`, and `ENABLE` plus `FORCE ROW LEVEL SECURITY`
with the isolation policy on each tenant table. The first migration also checks that both
extensions are present and fails with a message naming the script if they are not.

The same script is used in three places: the local Postgres container (as an init script), CI
(run against the service container), and production (run once after the database is created).

## Consequences

- A new environment needs one manual step before the first migration. The failure when it is
  skipped is immediate and says what to do.
- A database backup of one database contains no roles. Recovery is therefore "bootstrap, then
  restore", which is the order `scripts/restore-drill.sh` follows and verifies.
- Role attributes live in one reviewed file instead of being spread over migrations.
