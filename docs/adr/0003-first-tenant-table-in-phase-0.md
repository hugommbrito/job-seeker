# 0003. The first per-user table ships in Phase 0

2026-11-21. Accepted. Adds to Phase 0 of the implementation plan, which lists the tenancy
machinery but no per-user table.

## Context

Phase 0 must deliver row-level security, a meta-test over the database catalog and a canary
isolation suite. With no per-user table in the schema, all three would pass by having nothing to
check: "every tenant table has a policy" is true of zero tables, and "no response contains
another tenant's data" is true when there is no tenant data.

The alternative was a table that exists only in tests. That proves the machinery, but leaves the
deployed database without a single policy, so the acceptance run on the deployed instance would
verify nothing real.

## Decision

Phase 0 creates `profiles.Profile`, the first table from the plan's per-user list, with one
field: the user's timezone. `GET /api/profile` returns it, or the default when the user has no
row yet. Reading never creates a row.

The remaining profile fields (filters, weights, home location, notification preferences) and
their validation are added with the first-run wizard in Phase 1, as planned.

Two guards make sure the suites never go hollow again: the meta-test fails if there is no tenant
table, and the isolation suite fails if any tenant model has no canary seeder.

## Consequences

- Phase 1 extends an existing table with a migration instead of creating it.
- The deployed instance has a real policy to verify from the first deploy.
