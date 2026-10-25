#!/bin/bash
# Bounded quantlab alias; existing exporter and stock-vault mounts are unchanged.
set -euo pipefail
MNT=/mnt/funnytree-quantlab/algobots
mountpoint -q "$MNT" && exit 0
mkdir -p "$MNT"
# The server's default 0022 otherwise strips group-write from new outputs.
sshfs -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,allow_other,default_permissions \
  -o 'sftp_server=/usr/lib/openssh/sftp-server -u 0002' \
  root@100.79.207.5:/mnt/vault-data/algobots "$MNT"
