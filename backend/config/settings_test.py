"""Settings for tests, type checking and schema export.

The values that shape behaviour are fixed here so a developer's .env (where DEBUG is on) cannot
change what the tests see: the route set, the cookie flags and the checks all depend on DEBUG.
The database URL still comes from the environment, because tests need a real Postgres.
"""

import os

os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_SECRET_KEY"] = "test-only"  # noqa: S105
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver"
os.environ["TRUSTED_PROXY_COUNT"] = "0"
os.environ["SERVICE_NAME"] = "api"
# Tasks run in-process, so a test that commits sees the task's effect without a broker.
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "1"
# Lets tools that never open a connection (mypy, schema export) import the settings.
os.environ.setdefault("DATABASE_URL", "postgres://app:unused@127.0.0.1:5433/jobseeker")

from config.settings import *  # noqa: F403
