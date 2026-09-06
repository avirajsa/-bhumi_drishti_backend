#!/bin/sh
set -e

echo "================================================================="
echo " STARTING ROAD RISK & ACCESSIBILITY BACKEND CONTAINER (NER INDIA)"
echo "================================================================="

if [ -n "$DATABASE_URL" ]; then
    # Extract host, port, user from DATABASE_URL
    DB_HOST=$(python3 -c "from urllib.parse import urlparse; u=urlparse('$DATABASE_URL'); print(u.hostname or 'localhost')")
    DB_PORT=$(python3 -c "from urllib.parse import urlparse; u=urlparse('$DATABASE_URL'); print(u.port or 5432)")
    DB_USER=$(python3 -c "from urllib.parse import urlparse; u=urlparse('$DATABASE_URL'); print(u.username or 'postgres')")
else
    DB_HOST="${POSTGRES_HOST:-db}"
    DB_PORT="${POSTGRES_PORT:-5432}"
    DB_USER="${POSTGRES_USER:-postgres}"
fi

echo "Waiting for PostgreSQL database at ${DB_HOST}:${DB_PORT}..."
RETRY_COUNT=0
MAX_RETRIES=15

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" || [ $RETRY_COUNT -ge $MAX_RETRIES ]; do
  echo "PostgreSQL is unavailable at ${DB_HOST}:${DB_PORT} - sleeping 2 seconds... (Attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
  RETRY_COUNT=$((RETRY_COUNT + 1))
  sleep 2
done

echo "Proceeding with database operations..."

# Run database setup & XGBoost model training if requested or default
if [ "$RUN_POPULATE_ON_STARTUP" != "false" ]; then
    echo "Running database initialization, feature seeding, IMD weather sync, and XGBoost model training..."
    python scripts/populate_db.py
fi

echo "Database ready & XGBoost model loaded. Starting FastAPI application..."
exec "$@"
