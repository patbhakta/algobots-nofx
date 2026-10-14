#!/bin/sh
# Guarded NoFX SQLite -> Postgres migration REHEARSAL.
#
# Never point this at the live /opt/algobots-stack/data/data.db. Take a copy
# first; the CONFIRM_TEST_COPY gate exists to make that explicit. The script
# refuses to touch a non-empty destination and only writes its verification
# report once every check has passed.
#
# NoFX's GORM schema declares booleans as `numeric DEFAULT false`, which
# pgloader would otherwise map to a Postgres `numeric` column whose DEFAULT is
# invalid ("invalid input syntax for type numeric: false"). The generated load
# file casts those columns to `boolean`; SQLite stores them as 0/1, which
# Postgres accepts as boolean input directly, so no value transform is needed.
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
command -v pgloader >/dev/null || { echo "pgloader is required" >&2; exit 2; }

sqlite3 "$SOURCE" 'PRAGMA integrity_check;' | grep -qx ok
sqlite3 "$SOURCE" "SELECT 1 FROM users WHERE lower(email)=lower('$OWNER_EMAIL') LIMIT 1;" | grep -qx 1

# Destination must be disposable and empty. pgloader creates tables and data.
[ "$(psql "$TARGET" -Atqc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")" = 0 ] || {
  echo "refusing: destination public schema is not empty" >&2; exit 2;
}

# The load file lives beside the source copy so that a containerised pgloader
# sees it under the same mount that exposes the database.
WORKDIR=$(dirname "$SOURCE")
LOADFILE="$WORKDIR/.nofx-migrate-$$.load"
PGLOADER_LOG="$WORKDIR/.nofx-migrate-$$.log"
trap 'rm -f "$LOADFILE"' EXIT

cat > "$LOADFILE" <<EOF
LOAD DATABASE
     FROM sqlite://$SOURCE
     INTO $TARGET

 WITH create tables, create indexes, reset sequences

 CAST type numeric to boolean;
EOF

# pgloader exits 0 even when it logs "FATAL Failed to create the schema", so
# its status alone cannot be trusted; scan the log and then re-verify the data.
pgloader "$LOADFILE" 2>&1 | tee "$PGLOADER_LOG"
if grep -qE '(FATAL|ERROR) ' "$PGLOADER_LOG"; then
  echo "pgloader reported errors; see $PGLOADER_LOG" >&2
  exit 3
fi

psql "$TARGET" -Atqc "SELECT 1 FROM users WHERE lower(email)=lower('$OWNER_EMAIL') LIMIT 1" | grep -qx 1

# Compare row counts without a pipeline, so that a mismatch can exit the
# script directly rather than only a subshell. Report is staged and published
# only after every table matches, so a failed run leaves no passing report.
TABLES=$(sqlite3 "$SOURCE" \
  "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
STAGED="$REPORT.partial"
: > "$STAGED"
{
  echo "NoFX guarded migration verification"
  echo "source_copy=$SOURCE"
  echo "owner_email=$OWNER_EMAIL"
  echo "sqlite_integrity=ok"
  echo "owner_survived=yes"
  echo "numeric_to_boolean_cast=applied"
} >> "$STAGED"

IFS='
'
for table in $TABLES; do
  sqlite_count=$(sqlite3 "$SOURCE" "SELECT count(*) FROM \"$table\";")
  pg_count=$(psql "$TARGET" -Atqc "SELECT count(*) FROM \"$table\"")
  if [ "$sqlite_count" != "$pg_count" ]; then
    echo "row count mismatch: $table sqlite=$sqlite_count postgres=$pg_count" >&2
    rm -f "$STAGED"
    exit 3
  fi
  echo "$table=$sqlite_count" >> "$STAGED"
done
unset IFS

mv "$STAGED" "$REPORT"
echo "verification report written to $REPORT"
