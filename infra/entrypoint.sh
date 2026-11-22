#!/bin/sh
# One image, one command per service. The first argument names the service.
set -e

case "${1:-api}" in
  api)
    export SERVICE_NAME=api
    # Refuses to start if the database role could bypass row-level security (a superuser, a
    # role with BYPASSRLS, or the schema owner). Failing here is better than serving every
    # tenant's rows to everyone.
    python manage.py check --deploy --database default
    exec gunicorn config.wsgi:application \
      --bind "0.0.0.0:${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-2}" \
      --access-logfile -
    ;;
  migrate)
    # The only service that connects as the schema owner.
    export SERVICE_NAME=migrate
    exec python manage.py migrate --noinput
    ;;
  manage)
    shift
    exec python manage.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
