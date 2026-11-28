"""Operational endpoints.

`/health` says the process is up and nothing more; it touches no database, so a slow query can
never make the platform restart a healthy container. Whether work is getting done is a different
question, answered by `/api/operations` (apps.operations.api).
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe

from apps.accounts.demo import demo_readable


@demo_readable
@require_safe
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})
