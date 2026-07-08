#!/bin/bash
set -e

mkdir -p "$(dirname "$0")/../logs"

python manage.py migrate --noinput

# Background WhatsApp sends (see hw/tasks.py) are processed by qcluster, not
# the web workers. Run it as its own long-lived process (separate systemd
# unit / supervisor program) alongside this script — it is NOT started here
# because this script's final `exec` replaces itself with gunicorn.
# Example systemd unit (adjust paths to match the deployment):
#   ExecStart=/path/to/venv/bin/python manage.py qcluster

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --worker-class gthread \
  --workers ${GUNICORN_WORKERS:-3} \
  --threads ${GUNICORN_THREADS:-4} \
  --timeout 120 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --preload
