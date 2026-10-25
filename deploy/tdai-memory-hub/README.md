# tdai memory-hub recovery

Reproducible deployment overlay for TencentCloud/TencentDB-Agent-Memory revision
`0468a2a5b50eaafc54758ed1e2e6609472e5b6ce`. This is the combined service on .243:
panel/UI on tailnet port 8125 and knowledge on 8424. Core and proxy are separate.

The knowledge manifest pins OpenTelemetry API 1.9.1, SDK-node/exporter 0.219.0,
and core/trace-base 2.8.0. Langfuse 5.6 permits exporter versions up to 1.0;
a fresh unlocked install selected exporter 0.300 and SDK 3.0, whose imports
require API 1.10. A temporary `npm install --no-save api@1.9.0` did not fix that
graph and was undone by prune. Every build stage now uses `npm ci`, with
npm 11.11.0 and Node 22.23.4. Panel and web locks come from the pinned source.

The committed knowledge lock was generated in an empty directory using npm
11.11.0 `npm install --package-lock-only --ignore-scripts --no-audit --no-fund`.
The resolver emitted 27 orphan entries marked `extraneous` under Vitest,
including non-Linux esbuild binaries. Those extraneous entries were removed;
otherwise `npm ci` failed with EBADPLATFORM. npm 10.9.9 also failed resolution
with its `edgesOut` bug. The final lock passed a complete clean image build,
including native SQLite installation, all three builds and production prune.

Build on the host, from this directory (the context must be empty):

```sh
bash build.sh /opt/tdai-test /root/tdai-rebuild-backup/hub-build-new
```

Only tracked upstream files enter the context. The overlay supplies the manifest,
lock, Dockerfile and combined launcher; it never copies host `.env` files.
The launcher creates the panel registry from the saved environment with mode
0600, starts both services, and terminates the sibling if either exits. Tini
reaps children. Health requires both APIs to respond.

`recreate-hub.py` reads the existing `/root/tdai-rebuild-backup/hub.env` and
`tdai-memory-hub.json`. It prints only the new container ID. With no arguments,
it creates an unpublished `tdai-memory-hub-candidate` for internal smoke checks.
With `tdai-memory-hub`, it restores the saved network, volume, restart policy,
and tailnet port bindings. Stop/remove the candidate and stop/rename the previous
hub before creating the production name. Never run the old multi-service
`recreate_tdai.py` for this repair.

Recovery verification, 2026-10-25:

- Node reports v22.23.4; full production `npm ls --omit=dev --all` exits 0.
- Knowledge and panel `/health` return HTTP 200 on both internal and published ports.
- Panel `/`, its JavaScript/CSS assets, and `/api/v1/meta/instances` return 200.
- Registry points to `http://memory-core:8420` and preserves the tailnet proxy URL.
- Container health reports healthy. Core and proxy remain healthy.
- Image tag: `agentmemory/memory-hub:alg-3427` (also tagged `latest`).
- Image ID: `sha256:24aa96bc219f319522ee50708872be47e5d5f8ae672cd5013de0c5d56522ac75`.
- Failed old container retained stopped as `tdai-memory-hub-failed-alg3427`.
- Host build log: `/root/tdai-rebuild-backup/build-alg3427.log`.

These are startup, dependency, UI and routing checks. No LLM ingestion requests
or paid inference were needed to prove this repair.
