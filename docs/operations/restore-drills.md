# Restore drills

A backup that has never been restored is a hope, not a backup. This file is the record of each
time one was restored and checked.

## Procedure

1. Download a scheduled backup of the `jobseeker` database from the off-host bucket to a machine
   with Docker. Do not use the copy on the server: the drill is meant to prove the off-host one.
2. Run the drill:

   ```sh
   scripts/restore-drill.sh path/to/the-archive.dump
   ```

   It starts a scratch Postgres container, creates the roles with `infra/postgres/bootstrap.sh`
   (a single-database archive contains none), restores the archive, and verifies that:

   - the migration history and the users came back;
   - every tenant table has row-level security enabled and forced;
   - the `app` role reads no tenant row with no user set;
   - the `app` role, acting as one user, reads that user's rows and nobody else's;
   - every table is owned by `migrator`.

   The container is removed at the end. No live database is touched.
3. Delete the downloaded archive. It contains every user's data.
4. Add a row to the log below with the report the script printed.

Repeat after any change to the backup configuration, the bootstrap script or the Postgres major
version, and at least twice a year.

## Log

| Date | Source of the archive | Archive size | Duration | Result | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-11-21 | Local development database, dumped with `pg_dump -Fc` | 32 KB | 3 s | Passed | **Rehearsal of the procedure, not a drill.** Two synthetic users with one row each. It proves the script and the bootstrap-then-restore order; it says nothing about the off-host backup, which does not exist yet |

The Phase 0 acceptance needs one row here whose source is the off-host bucket of the deployed
instance.
