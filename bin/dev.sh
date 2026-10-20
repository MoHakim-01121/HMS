#!/bin/bash
# Dev lokal: nyalakan PostgreSQL (kalau belum), Django, dan Vite sekaligus.
# Ctrl+C mematikan Django dan Vite; database dibiarkan jalan.
set -e

cd "$(dirname "$0")/.."

PGDATA_DIR="${HMS_PGDATA:-$HOME/.local/share/hms-pg}"
PYTHON="${HMS_PYTHON:-.venv-linux/bin/python}"

if ! pg_ctl -D "$PGDATA_DIR" status >/dev/null 2>&1; then
  echo "Menyalakan database..."
  pg_ctl -D "$PGDATA_DIR" -l "$PGDATA_DIR/server.log" -w start >/dev/null
fi
echo "Database: jalan"

for port in 8000 5173; do
  if ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "Port $port sudah dipakai — server lain masih jalan. Matikan dulu, lalu ulangi." >&2
    exit 1
  fi
done

echo "Menjalankan migrasi..."
"$PYTHON" manage.py migrate --noinput

trap 'kill 0' EXIT

"$PYTHON" manage.py runserver 0.0.0.0:8000 &
npm run dev &

wait
