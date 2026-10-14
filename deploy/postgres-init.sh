#!/bin/sh
set -eu

# Runs only when the Postgres named volume is initialized. Identifiers are
# quoted as identifiers; passwords remain owned by POSTGRES_USER.
case "${NOFX_DB:-nofx}" in
  *[!A-Za-z0-9_]*) echo "NOFX_DB contains invalid characters" >&2; exit 1 ;;
esac
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "CREATE DATABASE \"${NOFX_DB:-nofx}\"" 2>/dev/null || \
psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -tAc "SELECT 1 FROM pg_database WHERE datname='${NOFX_DB:-nofx}'" | grep -qx 1
