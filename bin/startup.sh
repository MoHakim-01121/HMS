#!/bin/bash
# Startup script for Railway deployment

# Activate virtual environment
source "$(dirname "$0")/../env/bin/activate"

# Run Django migrations (optional, comment out if not needed)
python manage.py migrate --noinput

# Collect static files (optional, comment out if not needed)
python manage.py collectstatic --noinput

# Start the Django server using Gunicorn
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --timeout 120
