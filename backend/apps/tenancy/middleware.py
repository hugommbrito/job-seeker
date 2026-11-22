"""Runs every authenticated request inside the signed-in user's tenant context."""

from __future__ import annotations

from collections.abc import Callable

from django.db import transaction
from django.http import HttpRequest, HttpResponse

from apps.tenancy.context import tenant_context


class TenantContextMiddleware:
    """Wrap the view in ``tenant_context`` so row-level security knows who is asking.

    Anonymous requests get no context: tenant tables then return nothing at all, which is the
    safe answer for a route that forgot to require a session.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return self.get_response(request)

        with tenant_context(user.pk):
            response = self.get_response(request)
            # The context is also the request's transaction. Django turns an unhandled
            # exception into a 500 response before it reaches this point, so the status is the
            # only signal left that the work should not be kept.
            if response.status_code >= 500:
                transaction.set_rollback(True)
            return response
