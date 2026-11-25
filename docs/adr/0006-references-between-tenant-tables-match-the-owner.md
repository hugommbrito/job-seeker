# 0006. References between tenant tables also match the owner

2026-11-24. Accepted. Adds to the implementation plan, section 3.3 (database roles and tenancy).

## Context

Phase 1 adds the first per-user table that points at another per-user table: a timeline event
belongs to an application. Postgres checks foreign keys without applying row-level security, so
the plain key Django creates accepts a row owned by user A that points at user B's row. Nothing
leaks through reads (B's policy hides A's row, A's policy hides B's), but the write succeeds,
which tells A that B's row exists, and the data is wrong from then on. The API never takes a
parent id from a request body, so this is not reachable today; it would take one careless view.

## Decision

Every reference from a tenant table to another tenant table carries a second foreign key on
`(column, user_id)` referencing `(id, user_id)` on the parent, which gets a matching unique
constraint. Two migration helpers in `apps.tenancy.sql` write them: `tenant_key(parent)` and
`same_tenant_foreign_key(child, column, parent)`. A NULL in the column skips the check, like the
plain key, so optional references work unchanged.

The catalog meta-test, and `manage.py verify` on a deployed database, read every foreign key
from `pg_catalog` and fail on a reference between tenant tables that lacks the pair.

The isolation suite also changed: a route with a path parameter is now called with the id of
every row planted in that model, for every tenant, instead of with a fixed example path that
could not know which ids the planted rows would get. `PARAMETERS` in `tests/routes.py` names the
model behind each parameter.

## Consequences

- A per-user table that references another needs two extra lines in its migration; the
  meta-test names the missing one.
- Django keeps its own single-column key, so the ORM, cascades and `SET NULL` behave as before.
  Both keys are deferred to commit, like Django's.
