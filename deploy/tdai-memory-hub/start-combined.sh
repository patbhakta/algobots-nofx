#!/bin/bash
set -euo pipefail
# Recreate the panel's remote registry without printing the credential.
node --input-type=module <<'JS'
import fs from 'node:fs';
const e = process.env;
fs.mkdirSync('/app/panel/config', { recursive: true });
fs.writeFileSync('/app/panel/config/metadata-instances.json', JSON.stringify({instances: [{
  id: e.REMOTE_INSTANCE_ID || 'default', name: e.REMOTE_INSTANCE_NAME || 'Memory Core',
  gateway_endpoint: e.REMOTE_INSTANCE_URL, api_key: e.REMOTE_INSTANCE_KEY,
  proxy_endpoint: e.REMOTE_INSTANCE_PROXY_URL
}]}), {mode: 0o600});
JS
cd /app
PORT="${KNOWLEDGE_PORT:-8424}" node dist/server.mjs &
knowledge_pid=$!
cd /app/panel
PORT="${PANEL_PORT:-8125}" KNOWLEDGE_SERVICE_URL="http://127.0.0.1:${KNOWLEDGE_PORT:-8424}" node dist/index.js &
panel_pid=$!
stop() { kill -TERM "$knowledge_pid" "$panel_pid" 2>/dev/null || true; }
trap stop TERM INT EXIT
set +e
wait -n "$knowledge_pid" "$panel_pid"
status=$?
stop
wait "$knowledge_pid" "$panel_pid" 2>/dev/null
# Either child exiting requires the container to restart.
if [ "$status" -eq 0 ]; then status=1; fi
exit "$status"
