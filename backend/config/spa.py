"""Serves the web client's entry page for every path the server does not own.

The client does its own routing, so /board or /settings must return the same index.html that /
does. Its other files (scripts, styles, icons) are real files and are served by WhiteNoise before
a request ever reaches this view.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.views.decorators.http import require_safe

from apps.accounts.demo import demo_readable


@demo_readable
@require_safe
def index(request: HttpRequest) -> HttpResponse:
    try:
        html = (settings.WEB_DIST_DIR / "index.html").read_bytes()
    except FileNotFoundError:
        return HttpResponseNotFound(
            "The web client has not been built. Run `pnpm build` in web/, or use the Vite "
            "development server.",
            content_type="text/plain",
        )
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    # The page names content-hashed files, so it must be revalidated to pick up a new build.
    response["Cache-Control"] = "no-cache"
    return response
