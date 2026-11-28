"""Record a piece of background work as it runs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django.utils import timezone

from apps.operations.models import RunOutcome, TaskRun


@contextmanager
def recorded(name: str) -> Iterator[dict[str, int]]:
    """Wrap a run: yields a dict of counts to fill in, and stores the outcome either way.

    The row is written outside any tenant context and outside the work's own transactions, so a
    failure inside the work cannot roll back the record of it.
    """
    run = TaskRun.objects.create(name=name, started_at=timezone.now())
    counts: dict[str, int] = {}
    try:
        yield counts
    except Exception as error:
        run.outcome = RunOutcome.ERROR
        run.error = type(error).__name__
        raise
    else:
        run.outcome = RunOutcome.OK
    finally:
        run.finished_at = timezone.now()
        run.counts = counts
        run.save(update_fields=["outcome", "error", "finished_at", "counts"])
