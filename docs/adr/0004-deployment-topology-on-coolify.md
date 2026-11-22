# 0004. Deployment topology on Coolify

2026-11-21. **Proposed**: designed from Coolify's documentation and rehearsed locally with
Docker, not yet run on the server. To be confirmed or replaced after the first deploy. Refines
the implementation plan, section 3.2.

## Context

The plan asks for one image with a command per service, a one-shot `migrate` that runs before
`api` and is the only holder of the schema owner's credentials, and scheduled Postgres backups.
Reading Coolify's documentation and issue tracker (version 4.7) showed three things that decide
how this can be arranged:

1. In an application deployed from a compose file, every variable set in Coolify's UI is given
   to every service. A `MIGRATOR_DATABASE_URL` variable would be readable inside `api`, which
   defeats the separation.
2. The "pre-deployment command" runs in the old container and is skipped on the first deploy, so
   it cannot run migrations.
3. Scheduled backups cover standalone database resources (and databases inside a service stack),
   not a database declared inside an application's compose file. Backups are `pg_dump` archives
   and are not encrypted by Coolify.

## Decision

- **Postgres** is a standalone Coolify database resource using the `pgvector/pgvector:pg18`
  image, bootstrapped once with `infra/postgres/bootstrap.sh`. Coolify's scheduled backup dumps
  the `jobseeker` database to an S3 bucket that encrypts at rest.
- **`migrate` and `api`** are one compose application (`infra/docker-compose.coolify.yml`)
  connected to Coolify's predefined network to reach the database. `api` starts only after
  `migrate` has completed successfully.
- **The schema owner's DSN is a file on the server**, readable only by the container user and
  mounted into `migrate` alone. Settings read it through `DATABASE_URL_FILE`. It is never a
  Coolify variable, so it cannot reach `api`.
- As a second line, `api` checks its own database role at start and refuses to run as a
  superuser, a role with `BYPASSRLS`, or the schema owner.

## Consequences

- One secret is managed outside Coolify's UI, by hand, on the server.
- Verified locally: the image, the `migrate` then `api` sequence, the credential read from a
  mounted file, `api` refusing the owner's credentials, and bootstrap-then-restore of a dump.
- Not verified until the first deploy: that Coolify honours `depends_on` with
  `service_completed_successfully`, that it passes an absolute bind mount through unchanged, and
  the exact hostname of the database on the predefined network. The runbook lists a fallback for
  each.
