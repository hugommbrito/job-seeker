"""Every route the server answers, found by walking Django's URL resolver.

Shared by the isolation suite and the route classification test so that neither can drift from
what is really mounted: a route added anywhere (an API operation, an admin mount, a static
mount) shows up here without being listed by hand.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.demo import ninja_path_view, views_for

# Concrete paths to request for route patterns that are not literal and have no parameter the
# table below can fill.
EXAMPLE_PATHS: dict[str, list[str]] = {
    # The web client's catch-all: the root and an arbitrary client-side route.
    r"^(?!api/|static/).*$": ["/", "/some/client/route"],
}

# Which planted model each path parameter names. The isolation suite calls a route once for every
# row it planted in that model, in every tenant, so a route is always tried with other tenants'
# ids; the other suites use 0. A parameter missing from this table fails the suites: they cannot
# check a route they cannot call.
PARAMETERS: dict[str, str] = {
    "application_id": "Application",
    "event_id": "ApplicationEvent",
}

_PARAMETER = re.compile(r"<(?:\w+:)?(?P<name>\w+)>")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def expand(template: str, ids: Mapping[str, Sequence[int]] | None) -> list[str]:
    """Fill each {Model} placeholder with every planted id of that model (0 when none given)."""
    names = _PLACEHOLDER.findall(template)
    choices = [list((ids or {}).get(name) or [0]) for name in names]
    paths = []
    for combination in itertools.product(*choices):
        path = template
        for name, value in zip(names, combination, strict=True):
            path = path.replace("{" + name + "}", str(value), 1)
        paths.append(path)
    return paths


@dataclass(frozen=True)
class Route:
    pattern: str
    method: str  # an HTTP method, or "*" for a plain Django view that handles its own
    view: Callable[..., Any]
    is_api: bool

    @property
    def label(self) -> str:
        return f"{self.method} {self.pattern}"

    def paths(self, ids: Mapping[str, Sequence[int]] | None = None) -> list[str]:
        if self.pattern in EXAMPLE_PATHS:
            return EXAMPLE_PATHS[self.pattern]

        def placeholder(match: re.Match[str]) -> str:
            model = PARAMETERS.get(match["name"])
            if model is None:
                raise AssertionError(
                    f"Route {self.label} has the parameter {match['name']!r}; name the model it "
                    "refers to in PARAMETERS in tests/routes.py."
                )
            return "{" + model + "}"

        template = "/" + _PARAMETER.sub(placeholder, self.pattern)
        if re.search(r"[<(\[\\^$*+?]", template):
            raise AssertionError(
                f"Route {self.label} is a pattern; add example paths to tests/routes.py."
            )
        return expand(template, ids)


def _walk(patterns: list[Any], prefix: str = "") -> Iterator[tuple[str, URLPattern]]:
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _walk(entry.url_patterns, route)
        else:
            yield route, entry


def all_routes() -> list[Route]:
    routes = []
    seen: set[tuple[str, str]] = set()
    for pattern, entry in _walk(get_resolver().url_patterns):
        is_api = ninja_path_view(entry.callback) is not None
        for method, view in views_for(entry.callback).items():
            # Django Ninja mounts one URL pattern per operation, each serving every method of its
            # path; Django dispatches to the first, so the rest are the same route again.
            if (pattern, method) in seen:
                continue
            seen.add((pattern, method))
            routes.append(Route(pattern=pattern, method=method, view=view, is_api=is_api))
    return routes
