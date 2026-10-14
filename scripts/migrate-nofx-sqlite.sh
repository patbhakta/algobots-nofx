#!/bin/sh
set -eu

SOURCE=${1:?usage: migrate-nofx-sqlite.sh COPY_OF_DATA_DB POSTGRES_URI REPORT_FILE}
TARGET=${2:?usage: migrate-nofx-sqlite.sh COPY_OF_DATA_DB POSTGRES_URI REPORT_FILE}
REPORT=${3:?usage: migrate-nofx-sqlite.sh COPY_OF_DATA_DB POSTGRES_URI REPORT_FILE}
OWNER_EMAIL=${OWNER_EMAIL:-pat@bhakta.us}

[ -f "$SOURCE" ] || { echo "source copy not found: $SOURCE" >&2; exit 2; }
[ "${CONFIRM_TEST_COPY:-}" = "YES" ] || {
  echo "refusing: set CONFIRM_TEST_COPY=YES after supplying a copy, never live data.db" >&2
  exit 2
}
sqlite3 "$SOURCE" 'PRAGMA integrity_check;' | grep -qx ok
sqlite3 "$SOURCE" "SELECT 1 FROM users WHERE lower(email)=lower('$OWNER_EMAIL') LIMIT 1;" | grep -qx 1

# Destination must be disposable and empty. pgloader creates tables and data.
[ "$(psql "$TARGET" -Atqc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")" = 0 ] || {
  echo "refusing: destination public schema is not empty" >&2; exit 2;
}
command -v pgloader >/dev/null || { echo "pgloader is required" >&2; exit 2; }
pgloader "sqlite://$SOURCE" "$TARGET"

psql "$TARGET" -Atqc "SELECT 1 FROM users WHERE lower(email)=lower('$OWNER_EMAIL') LIMIT 1" | grep -qx 1
{
  echo "NoFX guarded migration verification"
  echo "owner_email=$OWNER_EMAIL"
  echo "sqlite_integrity=ok"
  echo "owner_survived=yes"
  sqlite3 "$SOURCE" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;" |
  while IFS= read -r table; do
    sqlite_count=$(sqlite3 "$SOURCE" "SELECT count(*) FROM \"$table\";")
    pg_count=$(psql "$TARGET" -Atqc "SELECT count(*) FROM \"$table\"")
    [ "$sqlite_count" = "$pg_count" ] || { echo "row count mismatch: $table" >&2; exit 3; }
    echo "$table=$sqlite_count"
  done
} > "$REPORT"
