"""The HTTP API. Its OpenAPI schema is the contract the web client's types are generated from."""

from __future__ import annotations

from django.conf import settings
from ninja import NinjaAPI
from ninja.security import django_auth

from apps.accounts.api import router as auth_router
from apps.profiles.api import router as profile_router

api = NinjaAPI(
    title="job-seeker",
    version="0.1.0",
    # Session cookie authentication on every route unless the route opts out. It also enforces
    # the CSRF token on every write.
    auth=django_auth,
    # The interactive docs are a development tool; the schema itself is in the repository.
    docs_url="/docs" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

api.add_router("/auth", auth_router)
api.add_router("/profile", profile_router)
