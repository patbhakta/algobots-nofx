#!/bin/sh
set -eu
umask 0002
python -m algobots.strategies.quantlab &
worker=$!
"$@" &
marimo=$!
trap 'kill "$worker" "$marimo" 2>/dev/null || true' EXIT INT TERM
while kill -0 "$worker" 2>/dev/null && kill -0 "$marimo" 2>/dev/null; do
    sleep 1
done
exit 1
