"""The single entry point through which code acts on behalf of a user.

Every per-user table has a row-level-security policy that compares its ``user_id`` with the
Postgres setting ``app.user_id``. This module is the only place that sets it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import connection, transaction

SETTING = "app.user_id"

_active_user_id: ContextVar[int | None] = ContextVar("tenant_user_id", default=None)


class TenantContextError(RuntimeError):
    """Raised when tenant data is reached without a context, or two contexts are mixed."""


def _write_setting(value: str) -> None:
    # The third argument makes the value local to the transaction, so it can never outlive the
    # request or task on a pooled connection.
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [SETTING, value])


@contextmanager
def tenant_context(user_id: int) -> Iterator[None]:
    """Run the enclosed block as ``user_id``: its queries see and write only that user's rows.

    Opens a transaction, because the setting is transaction-local. A middleware wraps every
    authenticated request in it; background tasks and management commands open it explicitly.

    Do no network I/O inside the block: it holds a database transaction open for its whole
    duration.

    Entering it again for the same user is a no-op. Entering it for a different user is an
    error: a unit of work belongs to one tenant, and a nested switch would be the easiest way
    to write rows under the wrong owner.
    """
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise TenantContextError("tenant_context needs an integer user id.")

    active = _active_user_id.get()
    if active is not None:
        if active != user_id:
            raise TenantContextError(
                "A tenant context is already active for another user; contexts cannot be nested."
            )
        yield
        return

    with transaction.atomic():
        _write_setting(str(user_id))
        token = _active_user_id.set(user_id)
        try:
            yield
        finally:
            _active_user_id.reset(token)
        # Reached only when the block succeeded. Ending the outermost transaction already clears
        # the setting; this covers the case where the block is itself inside a transaction
        # (every test is), where a released savepoint would otherwise leave the user set.
        # After an error the rollback undoes the assignment, and no query could run anyway.
        # Empty is the "no user" value: this function is the only writer and refuses to nest,
        # so there is never an outer user to restore.
        if not connection.needs_rollback:
            _write_setting("")


def current_user_id() -> int:
    """Return the user the current block runs as, or fail loudly outside a context."""
    user_id = _active_user_id.get()
    if user_id is None:
        raise TenantContextError("No tenant context is active.")
    return user_id


def active_user_id() -> int | None:
    """Return the user the current block runs as, or None outside a context."""
    return _active_user_id.get()
