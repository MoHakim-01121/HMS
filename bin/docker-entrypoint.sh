#!/bin/bash
# Container entrypoint: idempotent migrate + collectstatic, then hand off to
# the CMD (gunicorn). Settings gate on a real SECRET_KEY so these run here at
# runtime — never at image build time where env vars aren't available.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"