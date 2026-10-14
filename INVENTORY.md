# `.243` container inventory

Read-only snapshot taken 2026-10-14 from `100.82.57.72` with `docker ps -a`,
`docker inspect`, `docker volume ls`, and `docker network ls`. All published
ports bind only to the Tailscale address. Image tags below are the values
configured on the host (mutable `latest` tags are intentionally called out).

| Container | Image | Published ports | Storage mounts | Network |
| --- | --- | --- | --- | --- |
| `nofx-frontend` | `algobots/nofx-frontend:algobots-v6` | `100.82.57.72:8201 -> 80/tcp` | `/opt/algobots-stack/nofx-frontend-nginx.conf:/etc/nginx/conf.d/default.conf:ro` | `algobots-stack_algobots` |
| `nofx-trading` | `ghcr.io/nofxaios/nofx/nofx-backend:latest` | `100.82.57.72:8200 -> 8080/tcp` | `/opt/algobots-stack/bridge:/app/bridge`, `/opt/algobots-stack/data:/app/data`, `/etc/localtime:/etc/localtime:ro` | `algobots-stack_algobots` |
| `nautilus-marimo` | `nautilus-marimo:latest` | `100.82.57.72:8202 -> 2718/tcp` | `/mnt/funnytree/algobots:/home/nautilus/work`, `/opt/algobots-stack/bridge:/home/nautilus/work/bridge`, `/mnt/funnytree/algobots/stack/marimo-config/marimo.toml:/root/.config/marimo/marimo.toml` | `algobots-stack_algobots` |
| `algobots-api-1` | `algobots-api` | `100.82.57.72:8000 -> 8000/tcp` | `/opt/algobots-stack/bridge:/bridge`, `/opt/laya/kalshi:/feeds/kalshi:ro`, `algobots_demostate:/var/lib/algobots-demo` | `algobots_default` |
| `jkp-api` | `algobots/jkp-api:latest` | `100.82.57.72:8130 -> 8000/tcp` | `/opt/algobots/data/jkp:/data:ro` | `api_default` |
| `algobots-postgres-1` | `postgres:16-alpine` | `5432/tcp` internal only | `algobots_pgdata:/var/lib/postgresql/data` | `algobots_default` |
| `algobots-redis-1` | `redis:7-alpine` | `6379/tcp` internal only | `algobots_redisdata:/data` | `algobots_default` |
| `tdai-memory-hub` | `agentmemory/memory-hub:latest` | `100.82.57.72:8125 -> 8125/tcp`; `:8424 -> 8424/tcp` | `tdai-panel-data:/data/knowledge` | `tdai-memory-stack` |
| `tdai-proxy` | `agentmemory/memory-proxy:latest` | `100.82.57.72:8096 -> 8096/tcp` | `/opt/tdai-test/deploy/global-images/.proxy-config/config.yaml:/data/config.yaml:ro` | `tdai-memory-stack` |
| `tdai-memory-core` | `agentmemory/memory-core:latest` | `100.82.57.72:8420 -> 8420/tcp` | `tdai-memory-core-data:/data/tdai-memory`, `/opt/tdai-test/deploy/global-images/.memory-core-config/tdai-gateway.yaml:/data/config/tdai-gateway.yaml:ro` | `tdai-memory-stack` |

Named volumes present: `algobots_demostate`, `algobots_pgdata`,
`algobots_redisdata`, `tdai-memory-core-data`, and `tdai-panel-data`.

The Phase 0 target is the root [`compose.yaml`](compose.yaml): AlgoBots API,
NoFX, Nautilus, Postgres, and Redis share one `algobots` network. The unrelated
JKP and TDAI stacks remain inventoried but are not silently absorbed into this
deployment.

## Migration guard

The live NoFX database is currently the bind-mounted
`/opt/algobots-stack/data/data.db`. It must not be modified in place. Copy it
to a scratch directory, run `scripts/migrate-nofx-sqlite.sh` against an empty
test `nofx` database, and retain the generated verification report. The script
fails unless SQLite integrity passes, `pat@bhakta.us` exists before and after,
and every migrated table has the same row count. Only then may a separately
authorized Kestra deployment set NoFX's `DB_TYPE=postgres`; this repository
does not flip production automatically.
