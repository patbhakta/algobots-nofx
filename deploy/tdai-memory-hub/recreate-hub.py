#!/usr/bin/env python3
"""Restore only the hub from the saved inspect and env; never echo secrets."""
import json
import subprocess
import sys
from pathlib import Path

backup = Path('/root/tdai-rebuild-backup')
cfg = json.loads((backup / 'tdai-memory-hub.json').read_text())[0]
host = cfg['HostConfig']
name = sys.argv[1] if len(sys.argv) > 1 else 'tdai-memory-hub-candidate'
image = 'agentmemory/memory-hub:alg-3427'
args = ['docker', 'run', '-d', '--name', name,
        '--network', host['NetworkMode'], '--env-file', str(backup / 'hub.env')]
for bind in host.get('Binds') or []:
    args += ['-v', bind]
if name == 'tdai-memory-hub':
    args += ['--restart', host['RestartPolicy']['Name']]
    for port, bindings in (host.get('PortBindings') or {}).items():
        for binding in bindings or []:
            args += ['-p', f"{binding.get('HostIp') or '0.0.0.0'}:{binding['HostPort']}:{port}"]
args += [image]
subprocess.run(args, check=True)
