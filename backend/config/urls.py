from django.urls import URLPattern, path, re_path

from apps.accounts.demo import demo_denied
from apps.operations.views import health
from config.api import api
from config.spa import index

api_urls = api.urls
for pattern in api_urls[0]:
    # Django Ninja mounts a root view of its own that always answers 404; it exists only so the
    # API's base path can be reversed. It is not ours to decorate, so it is marked here.
    if isinstance(pattern, URLPattern) and pattern.name == "api-root":
        demo_denied(pattern.callback)

urlpatterns = [
    path("health", health, name="health"),
    path("api/", api_urls),
    # Everything else belongs to the web client. /api/ is excluded so an unknown API path is a
    # 404, not an HTML page that a client would try to parse as JSON.
    re_path(r"^(?!api/|static/).*$", index, name="spa"),
]
