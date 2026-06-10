#!/bin/bash
set -e

mkdir -p "$(dirname "$0")/../logs"

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers 2 \
  --timeout 120 \
  --preload
