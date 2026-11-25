# Architecture decision records

Decisions taken after the [planning package](../planning/README.md) was closed. One short file
per decision, numbered in the order they were taken.

A record is never edited to say something different. When a decision changes, a new record is
added and the old one gets a line pointing to it.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-runtime-and-toolchain-versions.md) | Runtime and toolchain versions | Accepted |
| [0002](0002-database-bootstrap-outside-migrations.md) | Roles and extensions are created by a bootstrap script, not by migrations | Accepted |
| [0003](0003-first-tenant-table-in-phase-0.md) | The first per-user table ships in Phase 0 | Accepted |
| [0004](0004-deployment-topology-on-coolify.md) | Deployment topology on Coolify | Proposed |
| [0005](0005-web-scaffold-scope.md) | The web scaffold has no router and no service worker yet | Accepted |
| [0006](0006-references-between-tenant-tables-match-the-owner.md) | References between tenant tables also match the owner | Accepted |

## Format

```
# NNNN. Title

Date, status, and what it supersedes or refines (a decision-log number or another record).

## Context     what forced a decision
## Decision    what was decided
## Consequences what follows, including the costs
```
