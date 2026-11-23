#!/bin/sh
# Tickerlens entrypoint (Railway).
# - If a persistent volume is mounted at /data, seed it with the baked-in
#   database on first boot and point the app at it, so refreshes survive
#   restarts and redeploys.
# - Otherwise (no volume) fall back to the baked-in DB at /app/tickerlens.db.
# - Railway provides $PORT; default 8123 matches local dev.
set -e

if [ -d /data ]; then
  if [ ! -f /data/tickerlens.db ]; then
    echo "Seeding /data/tickerlens.db from image..."
    cp /app/tickerlens.db /data/tickerlens.db
  fi
  export DATABASE_URL="sqlite:////data/tickerlens.db"
fi

export PYTHONPATH=/app/src
exec uvicorn tickerlens.main:app --host 0.0.0.0 --port "${PORT:-8123}"
