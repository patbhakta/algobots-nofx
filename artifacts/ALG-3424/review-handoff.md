# UID-1000 acceptance — 2026-10-25

CEO review delta for PR #20; remains pending independent review and merge.

- Repository Ruff passes; warehouse tests: 14 passed.
- Deployed only marimo-quantlab with the UID/GID 1000 overlay and the approved
  /mnt/funnytree-quantlab/algobots alias. Healthy, tailnet-only :8205.
- Protected GET /api/files/roots returns 401 without token and 200 with token.
  The public login page can return 200, so it is not the auth acceptance route.
- Exact UID-1000 acceptance command passed; see uid1000-acceptance.log.
  Snapshot openbb-spy-ad6a2491f1d84484 has 10 SPY bars; rc6 catalog query,
  BacktestEngine replay (10 events), and Warehouse.load readback all passed.
- New outputs are root:1000, manifest 0664, catalog snapshot directory 02770.
  UID 1000 wrote, read, reopened and appended; a root-owned 0700 probe remained
  inaccessible to UID 1000 and was removed.

Non-root verification exposed three deployment issues corrected in this delta:
OpenBB bindings must be generated during image build; the SFTP connection needs
server umask 0002 as well as the container umask; UUID staging directories must
request 0770 rather than tempfile's 0700 on the root:1000 SSHFS alias. Shared
catalog immutability and manifest publication order remain covered by tests.

The installed bounded mount script is committed under deploy/quantlab. Its SFTP
umask affects only this alias connection. The existing exporter and stock-vault
mounts were not changed. Existing quantlab .config and .local directories were
made group-writable to allow runtime configuration. No data files were rewritten.
