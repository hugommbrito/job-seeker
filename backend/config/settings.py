"""Django settings.

Everything that differs between environments comes from environment variables, so one image
serves every service and no secret is ever written to a file in the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str:
    """Read a setting from NAME, or from the file named by NAME_FILE.

    The file form is for secrets mounted into one container only (the migrate service's
    database credentials), which must not appear in an environment shared between services.
    """
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes"}


def env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG")

# Which of the image's services this process is. The api must never run with the schema owner's
# credentials; apps.tenancy.checks uses this to tell the two apart.
SERVICE_NAME = env("SERVICE_NAME", "api")

SECRET_KEY = env("DJANGO_SECRET_KEY")

# The public hostname comes from the environment. The loopback names are always accepted because
# the container health check calls the app directly; the reverse proxy only forwards requests
# for the public hostname, so they are not reachable from outside.
ALLOWED_HOSTS = [*env_list("DJANGO_ALLOWED_HOSTS"), "localhost", "127.0.0.1", "[::1]"]
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "ninja",
    "apps.tenancy",
    "apps.accounts",
    "apps.profiles",
    "apps.operations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.static.SpaWhiteNoiseMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Order matters: the tenant context needs request.user, and the demo guard must run inside
    # the same request cycle so its 403 never touches tenant data.
    "apps.tenancy.middleware.TenantContextMiddleware",
    "apps.accounts.demo.DemoGuardMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
# The catch-all route serves the single-page app, so there is never a slash to append.
APPEND_SLASH = False

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

# --- Database
# One DSN per process. The api and the workers get the `app` role; only the migrate service gets
# `migrator`. Row-level security is the reason: see docs/planning, section 3.3.
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL"),
        conn_max_age=60,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
# Argon2 only: there are no legacy hashes to keep verifying.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Failed sign-ins allowed per window before the answer becomes 429. The pair limit stops guessing
# against one account from one place; the wider limits stop spreading the guesses out.
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES_PER_EMAIL_AND_IP = 5
LOGIN_MAX_FAILURES_PER_EMAIL = 20
LOGIN_MAX_FAILURES_PER_IP = 30

# How many reverse proxies sit in front of the app and append to X-Forwarded-For. Zero means the
# header is ignored, because without a proxy the client writes it.
TRUSTED_PROXY_COUNT = int(env("TRUSTED_PROXY_COUNT", "0"))

# --- Sessions and CSRF
# The session table stores a hash of the key, so a database leak does not hand out live sessions.
SESSION_ENGINE = "apps.accounts.session_backend"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
# Readable by the single-page app on purpose: it echoes the value in the X-CSRFToken header.
CSRF_COOKIE_HTTPONLY = False

# --- Transport and browser hardening
if TRUSTED_PROXY_COUNT > 0:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "0"))
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# HTTP is redirected to HTTPS by the reverse proxy; doing it here too would redirect the
# container health check, which arrives over plain HTTP from inside the network.
SILENCED_SYSTEM_CHECKS = ["security.W008"]

# Posting and email text is untrusted (project rule 6). The app renders it as text, and this
# header makes sure that a mistake there still cannot run a script.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    # Component libraries position popovers with inline style attributes.
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

# --- Static files and the single-page app
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# The built web client. WhiteNoise serves its files from the site root; any other path falls
# through to the catch-all view, which returns index.html.
WEB_DIST_DIR = Path(env("WEB_DIST_DIR", str(BASE_DIR.parent / "web" / "dist")))
WHITENOISE_ROOT = WEB_DIST_DIR if WEB_DIST_DIR.is_dir() else None

# --- Locale
LANGUAGE_CODE = "en-ca"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# --- Logging
# Console only: the platform collects stdout. Request bodies and user data are never logged.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
