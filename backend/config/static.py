"""Static file serving for the built web client."""

from __future__ import annotations

from whitenoise.middleware import WhiteNoiseMiddleware


# WhiteNoise ships no type information, hence the ignore.
class SpaWhiteNoiseMiddleware(WhiteNoiseMiddleware):  # type: ignore[misc]
    """WhiteNoise, plus long-lived caching for the web client's hashed files."""

    def immutable_file_test(self, path: str, url: str) -> bool:
        # Vite writes content-hashed files under /assets/, so a changed file has a new URL and
        # the old one can be cached forever. WhiteNoise only knows this about Django's own
        # static files.
        return url.startswith("/assets/") or bool(super().immutable_file_test(path, url))
