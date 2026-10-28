#!/bin/sh

set -eu

echo "Applying database migrations"
python -m flask --app app:create_app db upgrade
echo "Database migrations applied"

if [ "${FLASK_ENV:-production}" = "development" ]; then
    echo "Starting Watchly in development mode"
    exec python /run.py
fi

echo "Starting Watchly in production mode"
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 4 \
    --access-logfile - \
    "app:create_app()"
