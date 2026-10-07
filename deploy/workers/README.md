# Paper worker isolation (A06-3, ALG-3259)

Every paper worker the `Supervisor` spawns is launched through
`algobots.engine.workers.sandbox`, which runs in the child before the worker is
`exec`ed:

    python -m algobots.engine.workers.sandbox --account <acct> --state-dir <D> \
        [--uid U --gid G] --mem-mb 4096 --nice 10 --netns -- <worker command>

A control that was requested but can't be applied fails closed. The worker
never starts, the sandbox exits `78` (`EX_CONFIG`), and the supervisor reports
it as `exited`. Each worker writes `<state_dir>/workers/<acct>.sandbox.json`,
which splits its controls into `enforced` and `asserted`. That file is the
record for that process.

## Enforced vs asserted

| Control | Status | How |
|---|---|---|
| Non-root UID | **Enforced when `ALGOBOTS_WORKER_UID` is set** (and `ALGOBOTS_WORKER_GID`, which defaults to the UID) | `setgroups([])`, `setgid`, `setuid` before exec. It fails closed if the process is still UID 0. The supervisor `chown`s the worker's heartbeat dir and lease to that UID. `/demo/api/workers` shows the worker's real UID from `/proc` (`uid`). **Unset, the worker stays the API's UID (root in the image) and the report says `asserted.uid`.** |
| Memory cap | **Enforced** | `RLIMIT_AS` = `ALGOBOTS_WORKER_MEM_MB` (default 4096). Nautilus maps about 2.4 GB of virtual memory for about 345 MB RSS, so the cap is on address space, not RSS. A worker that grows past it gets `MemoryError` and dies alone. Also `RLIMIT_NOFILE=1024` and `RLIMIT_CORE=0`. |
| CPU | **Partly**: priority only | `nice +10` under the API. There is **no per-worker CPU-rate cap**. Without cgroup delegation in the container, an rlimit can only kill (`RLIMIT_CPU`), not throttle. The honest cap for the single-host setup is the API container's compose `deploy.resources` (or `cpus:`), which bounds the API and all workers together. It is not set yet. |
| No research code / `stock-vaults` | **Enforced with a dropped UID**, asserted as root | `/root/repos`, `/root/repos/stock-vaults`, `/mnt/funnytree/stock-vaults` and `/opt/stock-vaults` must be absent or unreadable to the worker UID, or the sandbox refuses. In the API image they are **absent**: the compose file mounts only the Laya feed (ro) and the demo state volume. On the bare host, `/root` is `755`, so a worker run there under any UID would be **refused**. That is the intended outcome. |
| Env scoped to the account | **Enforced** | `sandbox.scoped_env` (supervisor side) passes only `PATH`, `LANG`, `LC_ALL`, `TZ`, `PYTHONPATH`, `PYTHONUNBUFFERED`, `VIRTUAL_ENV`, `ALGOBOTS_DEMO_*` and that account's own `ALGOBOTS_ACCT_<ACCT>_*`. `DATABASE_URL`, the JWT secret, the credential key, broker keys and other accounts' secrets never reach a worker. The resulting key list goes into `enforced.env_keys`. |
| No broker egress | **Asserted** (enforced only with `CAP_SYS_ADMIN`) | The sandbox tries `unshare(CLONE_NEWNET)` (a loopback-only namespace). Docker's default capability set refuses it, so in the API container this is **asserted**: the worker builds only Nautilus's simulated paper venue, imports no live data or exec client, and holds no broker credentials (see env). On the host as root it is enforced. |
| Management only via the authenticated API | **By construction** | There is no HTTP route that starts, stops or restarts a worker. The supervisor is driven only by the API lifespan (`start_workers`/`stop_workers`) and the lease CLI on the host. `GET /demo/api/workers` only calls `Supervisor.status` (read-only). |

## Enabling the UID drop in production

`deploy/docker-compose.yml` doesn't set `ALGOBOTS_WORKER_UID` yet, so the live
demo workers still run as root with the other controls applied. To turn it on,
add `ALGOBOTS_WORKER_UID: "65534"` to the `api` service environment and
recreate the container. The measurement and demo below already ran with it
on, on the API image (`artifacts/A06/demo-run.json` → `sandbox.*.enforced.uid
== 65534`). Before flipping it live, check that the `demostate` volume's
`kill-switch.json` and the feed mount are readable by that UID. The supervisor
chowns only `workers/` and the lease files.

## Measuring

    docker run --rm -v $PWD/src:/app/src:ro -v $PWD/artifacts/A06:/out \
        -e PYTHONPATH=/app/src algobots-api:latest \
        python -m algobots.engine.workers.measure --state-dir /tmp/state --out /out \
            --seconds 120 --uid 65534

This runs the declared fixture (`algobots.engine.workers.fixture`: syn1–syn4,
two strategies each, so eight deployments) and writes
`artifacts/A06/measurements.json` and `demo-run.json`.
