#!/bin/sh
set -e

echo "================================================================="
echo " STARTING ROAD RISK & ACCESSIBILITY BACKEND CONTAINER (NER INDIA)"
echo "================================================================="

DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-postgres}"

echo "Waiting for PostgreSQL database at ${DB_HOST}:${DB_PORT}..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
  echo "PostgreSQL is unavailable - sleeping 2 seconds..."
  sleep 2
done

echo "PostgreSQL database is ready!"

# Run database setup & XGBoost model training if requested or default
if [ "$RUN_POPULATE_ON_STARTUP" != "false" ]; then
    echo "Running database initialization, feature seeding, IMD weather sync, and XGBoost model training..."
    python scripts/populate_db.py
fi

echo "Database ready & XGBoost model loaded. Starting FastAPI application..."
exec "$@"
