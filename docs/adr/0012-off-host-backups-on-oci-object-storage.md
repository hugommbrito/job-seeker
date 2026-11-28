# 0012. Off-host backups go to an OCI Object Storage bucket that only one key can reach

2026-11-27. Accepted. Settles "off-host backup target" in the implementation plan, section 10,
and names the bucket that ADR 0004 left as "an S3 bucket that encrypts at rest".

## Context

Coolify's scheduled backup is a `pg_dump` archive of the `jobseeker` database taken by the
superuser, so it holds every user's rows, and Coolify does not encrypt it (ADR 0004). It needs a
destination off the server, encrypted at rest, reached with a credential that Coolify keeps on
that same server. The server runs on Oracle Cloud (plan, section 3.2), whose Object Storage has
an S3-compatible API. Its S3 credentials, Customer Secret Keys, have no permissions of their own:
each acts with everything its user may do.

## Decision

- **A private bucket in a compartment of its own**, with Oracle-managed encryption and the
  Standard tier (an archived object has to be restored before it can be downloaded). No
  versioning, so that what Coolify's retention deletes is really gone.
- **A user that can do one thing.** Its only capability is Customer Secret Keys, and its group's
  policy grants `read buckets` and `manage objects`, both conditioned on the bucket's name. The
  key exists only in Coolify.
- **A time-bound retention rule of seven days, left unlocked.** Nothing younger can be deleted
  or overwritten, even with Coolify's key, and that user cannot change the rule. Coolify's own
  retention for the bucket keeps more than seven days, or its pruning fails on protected objects.
- The archive is Coolify's single-database `pg_dump --format=custom`, which keeps owners and
  privileges. The first restore drill from the bucket, on 2026-11-27, confirmed both.

## Consequences

- The backups are in the same cloud account as the server. They survive the loss of the server
  or its disk, not the loss of the account (suspension, billing, a compromised administrator);
  a second account or provider is the step that would cover it.
- Whoever takes the server can read the backups with the key, as they can read the live
  database. The retention rule keeps them from erasing the last seven days.
- The key never expires, and a user can hold two, so it is rotated by hand without a gap
  (runbook, section 8).
