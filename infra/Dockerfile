# syntax=docker/dockerfile:1
#
# One image for every service; the command picks the service (see infra/entrypoint.sh).
# Build from the repository root:  docker build -f infra/Dockerfile .
#
# Nothing here is architecture-specific, so the same file builds on amd64 and arm64.

# --- The web client. Its toolchain and node_modules never reach the runtime image.
FROM node:24-slim AS web
WORKDIR /src/web
# pnpm comes from the packageManager field in package.json.
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# --- Python dependencies, installed from the lockfile into a virtualenv that is copied over.
FROM python:3.14-slim AS python-deps
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# --- Runtime. Debian-based because the PDF renderer added in a later phase needs Pango.
FROM python:3.14-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    WEB_DIST_DIR=/app/web_dist \
    DEMO_DIR=/app/demo
RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
WORKDIR /app
COPY --from=python-deps /app/.venv /app/.venv
COPY backend/ /app/
# The demo persona, which the migrate service loads when DEMO_SEED=1.
COPY demo/ /app/demo/
COPY --from=web /src/web/dist /app/web_dist
COPY infra/entrypoint.sh /usr/local/bin/entrypoint
# Settings must import for collectstatic; these values are placeholders that are never used.
RUN DJANGO_SECRET_KEY=build-time-placeholder \
    DATABASE_URL=postgres://build@localhost/build \
    python manage.py collectstatic --noinput
USER app
EXPOSE 8000
# /health touches no database, so this says "the process is up" and nothing else. A one-shot
# container (migrate) exits before the first probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)"]
ENTRYPOINT ["entrypoint"]
CMD ["api"]
