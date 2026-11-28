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
  worker)
    export SERVICE_NAME=worker
    # The same refusal as the api: the worker writes tenant data, so it must be bound by
    # row-level security.
    python manage.py check --database default
    exec celery -A config worker --loglevel=INFO \
      --concurrency "${WORKER_CONCURRENCY:-2}" --queues default
    ;;
  beat)
    # Only schedules: it enqueues and reads no tenant data. Run exactly one.
    export SERVICE_NAME=beat
    exec celery -A config beat --loglevel=INFO --schedule /tmp/celerybeat-schedule
    ;;
  migrate)
    # The only service that connects as the schema owner.
    export SERVICE_NAME=migrate
    python manage.py migrate --noinput
    # The guest's synthetic tenant is rebuilt on every deploy, from demo/ in the image.
    if [ "${DEMO_SEED:-0}" = "1" ]; then
      python manage.py seed_demo
    fi
    ;;
  manage)
    shift
    exec python manage.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
