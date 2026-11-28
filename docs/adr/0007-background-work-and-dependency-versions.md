# 0007. Background work on Celery and Redis, and how new dependencies are versioned

2026-11-24. Accepted. Settles the open item "whether Django's built-in task framework has matured
enough to replace Celery" in the implementation plan, section 10, with its default. Refines
section 3.2 for the services Phase 1 adds. Not yet deployed.

## Context

Phase 1 brings the first background work: capture extraction, reminders, notification delivery
and housekeeping, some of it on a schedule. The plan names Celery with Redis and leaves open
whether Django's own task framework could replace it. Django 6.1, the version in use, ships that
framework with two backends only, `dummy` and `immediate`: there is no worker that runs tasks out
of process and no scheduler, so it cannot run the work above on its own.

## Decision

- **Celery 5.7 with a Redis 8 broker.** Tasks are acknowledged late and re-queued if a worker
  dies, so a task cut short by a deploy runs again; every task is written to be safe to repeat.
  Redis holds the queue only, with persistence off: anything that must survive a restart lives
  in Postgres. In production it requires a password, because Coolify's predefined network is
  shared with every other resource on the server.
- **One schedule, in settings.** `SCHEDULED_TASKS` lists each periodic task with its interval;
  beat's schedule is built from it, and `/api/operations` uses the same interval to call a task
  overdue when its last success is older than two intervals.
- **Run records.** Each scheduled run writes a row to `operations_taskrun`, a catalog table with
  counts and, on failure, the exception's class name only, since a message can quote the data it
  failed on. `/api/operations` reads it and is open to the owner only.
- **New dependencies are adopted at a release at least two weeks old**, extending the reasoning
  of ADR 0001 to libraries: redis-py 8.1.0 rather than the 8.2.0 published the day before,
  wcwidth 0.9.4 rather than a three-day-old 0.9.5, react-router 8.5.1 rather than 8.5.2 or
  8.5.3. For drag and drop the stable `@dnd-kit/core` 6.3 line is used; its successor
  `@dnd-kit/react` is still before 1.0.

## Consequences

- Three services join the production compose file: `worker`, `beat` (exactly one) and `redis`.
  The next deploy needs `REDIS_PASSWORD` set in Coolify, or the file refuses to start.
- Local development needs Redis for anything that enqueues work: `make db-up` starts it next to
  Postgres, and `make worker` and `make beat` run the two processes. Tests run tasks in-process
  and need neither.
