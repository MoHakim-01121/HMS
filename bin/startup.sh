#!/bin/bash
set -e

mkdir -p "$(dirname "$0")/../logs"

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --worker-class gthread \
  --workers ${GUNICORN_WORKERS:-3} \
  --threads ${GUNICORN_THREADS:-4} \
  --timeout 120 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --preload
