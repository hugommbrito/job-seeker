"""Every route the server answers, found by walking Django's URL resolver.

Shared by the isolation suite and the route classification test so that neither can drift from
what is really mounted: a route added anywhere (an API operation, an admin mount, a static
mount) shows up here without being listed by hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.demo import ninja_path_view, views_for

# Concrete paths to request for route patterns that are not literal. A pattern with a parameter
# must be listed here, or the suites fail: they cannot check a route they cannot call.
EXAMPLE_PATHS: dict[str, list[str]] = {
    # The web client's catch-all: the root and an arbitrary client-side route.
    r"^(?!api/|static/).*$": ["/", "/some/client/route"],
}


@dataclass(frozen=True)
class Route:
    pattern: str
    method: str  # an HTTP method, or "*" for a plain Django view that handles its own
    view: Callable[..., Any]
    is_api: bool

    @property
    def label(self) -> str:
        return f"{self.method} {self.pattern}"

    def paths(self) -> list[str]:
        if self.pattern in EXAMPLE_PATHS:
            return EXAMPLE_PATHS[self.pattern]
        if re.search(r"[<(\[\\^$*+?]", self.pattern):
            raise AssertionError(
                f"Route {self.label} has parameters; add example paths to tests/routes.py."
            )
        return ["/" + self.pattern]


def _walk(patterns: list[Any], prefix: str = "") -> Iterator[tuple[str, URLPattern]]:
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _walk(entry.url_patterns, route)
        else:
            yield route, entry


def all_routes() -> list[Route]:
    routes = []
    for pattern, entry in _walk(get_resolver().url_patterns):
        is_api = ninja_path_view(entry.callback) is not None
        for method, view in views_for(entry.callback).items():
            routes.append(Route(pattern=pattern, method=method, view=view, is_api=is_api))
    return routes
