"""The HTTP API. Its OpenAPI schema is the contract the web client's types are generated from."""

from __future__ import annotations

from django.conf import settings
from ninja import NinjaAPI
from ninja.security import django_auth

from apps.accounts.api import router as auth_router
from apps.applications.api import router as applications_router
from apps.documents.api import router as documents_router
from apps.notifications.api import channels_router
from apps.notifications.api import router as notifications_router
from apps.operations.api import router as operations_router
from apps.postings.api import router as captures_router
from apps.profiles.api import router as profile_router
from apps.profiles.api import tracks_router

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
api.add_router("/tracks", tracks_router)
api.add_router("/applications", applications_router)
# Documents are reached through their application, so they share its prefix.
api.add_router("/applications", documents_router)
api.add_router("/captures", captures_router)
api.add_router("/notifications", notifications_router)
api.add_router("/channels", channels_router)
api.add_router("/operations", operations_router)
