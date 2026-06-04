#!/bin/bash
set -e

mkdir -p "$(dirname "$0")/../logs"

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --timeout 120
