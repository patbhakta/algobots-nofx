# ALG-3350 P0.2 done-when evidence: guarded NoFX SQLite -> Postgres rehearsal

Captured 2026-10-14T07:13:08Z. Source was a byte-identical copy of the
live `/opt/algobots-stack/data/data.db` from .243; destination was a throwaway
`postgres:16-alpine` container. Production was never written to.

## Live database untouched

```
before: bca74df71a04337c16c0fa22918d5306  /opt/algobots-stack/data/data.db
copy:   bca74df71a04337c16c0fa22918d5306  nofx-copy.db
after:  bca74df71a04337c16c0fa22918d5306  /opt/algobots-stack/data/data.db
```

## Blocker found and fixed

A plain `pgloader sqlite://... postgresql://...` (the previous script) FAILS on
the real schema:

```
ERROR Database error 22P02: invalid input syntax for type numeric: "false"
FATAL Failed to create the schema, see above.
```

NoFX's GORM schema declares all 25 boolean columns across 9 tables as
`numeric DEFAULT false`. pgloader maps SQLite `numeric` to Postgres `numeric`,
whose DEFAULT `false` is invalid. The script now generates a load file with
`CAST type numeric to boolean`. SQLite stores these as integer 0/1, which
Postgres accepts as boolean input, so no value transform is needed (an earlier
attempt using `sqlite-timestamp-to-timestamp` corrupted `1` into `1-01-01`).

Separately, `pgloader` exits 0 even after logging `FATAL Failed to create the
schema`, so `set -e` never caught it. The script now scans the pgloader log.

## Verification report (all 18 tables matched)

```
NoFX guarded migration verification
source_copy=/tmp/paperclip-run-alg-3350-a3c800f0-406-xvA4rX/nofx-copy.db
owner_email=pat@bhakta.us
sqlite_integrity=ok
owner_survived=yes
numeric_to_boolean_cast=applied
ai_charges=0
ai_models=0
decision_records=0
exchanges=0
grid_configs=0
grid_events=0
grid_instances=0
grid_levels=0
grid_regime_assessments=0
strategies=1
system_config=1
telegram_configs=0
trader_equity_snapshots=0
trader_fills=0
trader_orders=0
trader_positions=0
traders=0
users=1
```

## Post-migration type and owner check

```
$ psql ... -c "SELECT email FROM users"
pat@bhakta.us
$ psql ... -c "SELECT is_active, config_visible, pg_typeof(is_active) FROM strategies"
t|t|boolean
```

## Guards verified (each refuses and writes no report)

```
missing CONFIRM_TEST_COPY -> exit 2: refusing: set CONFIRM_TEST_COPY=YES after supplying a copy, never live data.db
non-empty destination     -> exit 2: refusing: destination public schema is not empty
nonexistent source        -> exit 2: source copy not found
```

Production cutover (setting NoFX `DB_TYPE=postgres`) remains a separately
authorized Kestra deployment and is NOT performed by this repository.
