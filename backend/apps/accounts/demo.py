"""The demo role is denied everything it is not explicitly given.

A public guest account runs on the same instance as real data. Row-level security already keeps
the guest inside its own (synthetic) tenant; this guard decides what the guest may do there, and
keeps it away from anything that costs money or reaches the outside world.

Every route carries one of two marks, placed on the view function:

    @demo_readable   the guest may call it
    @demo_denied     the guest gets 403 (also what an unmarked route gets)

The second mark changes nothing at run time. It exists so that a test can require every route to
state its decision: an unmarked route fails the build instead of being denied by accident or,
worse, opened by a later refactor.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from ninja.operation import PathView

from apps.accounts.models import Role

_MARK = "_demo_access"


class DemoAccess(StrEnum):
    READABLE = "readable"
    DENIED = "denied"


def demo_readable[ViewT: Callable[..., Any]](view: ViewT) -> ViewT:
    """Mark a view the demo account may call."""
    setattr(view, _MARK, DemoAccess.READABLE)
    return view


def demo_denied[ViewT: Callable[..., Any]](view: ViewT) -> ViewT:
    """Mark a view the demo account may not call. Same effect as no mark, but on record."""
    setattr(view, _MARK, DemoAccess.DENIED)
    return view


def ninja_path_view(callback: Callable[..., Any]) -> PathView | None:
    """Return the Django Ninja path behind a URL callback, or None for a plain Django view.

    Ninja serves all methods of a path through one closure and offers no public way back to the
    operations. The closure is the only link, so this reads it; if a Ninja release changes that,
    the route classification test fails and the guard, finding no mark, denies.
    """
    for cell in getattr(callback, "__closure__", None) or ():
        try:
            value = cell.cell_contents
        except ValueError:  # an empty cell
            continue
        if isinstance(value, PathView):
            return value
    return None


def views_for(callback: Callable[..., Any]) -> dict[str, Callable[..., Any]]:
    """Map each HTTP method a URL callback serves to the function that carries its mark.

    A plain Django view answers every method with one function, reported under the key "*".
    """
    path_view = ninja_path_view(callback)
    if path_view is None:
        return {"*": callback}
    return {
        method: operation.view_func
        for operation in path_view.operations
        for method in operation.methods
    }


def demo_access(callback: Callable[..., Any], method: str) -> DemoAccess | None:
    """Return the mark for a request, or None when the route never stated one."""
    views = views_for(callback)
    view = views.get(method) or views.get("*")
    return getattr(view, _MARK, None) if view is not None else None


class DemoGuardMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., Any],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or user.role != Role.DEMO:
            return None
        if demo_access(view_func, request.method or "") is DemoAccess.READABLE:
            return None
        # 403, not 401: the session is valid and must survive, the action is simply not offered.
        return JsonResponse({"detail": "Not available to the demo account."}, status=403)
