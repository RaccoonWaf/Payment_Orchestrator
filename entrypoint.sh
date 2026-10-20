#!/bin/sh
set -e

echo "Waiting for database..."
until python -c "import socket; s=socket.create_connection(('${POSTGRES_HOST:-db}', int('${POSTGRES_PORT:-5432}')), 2); s.close()" 2>/dev/null; do
  sleep 1
done

echo "Running migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080