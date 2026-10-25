#!/bin/bash
# Usage: build.sh /path/to/TencentDB-Agent-Memory /path/to/empty-build-context
set -euo pipefail
source_dir=$(realpath "$1")
context=$(realpath -m "$2")
recipe=$(cd "$(dirname "$0")" && pwd)
revision=0468a2a5b50eaafc54758ed1e2e6609472e5b6ce
mkdir -p "$context"
[ -z "$(ls -A "$context")" ] || { echo 'Build context must be empty' >&2; exit 1; }
git -C "$source_dir" archive "$revision" MemoryKnowledge MemoryPanel | tar -x -C "$context"
cp "$recipe/MemoryKnowledge/package.json" "$context/MemoryKnowledge/package.json"
cp "$recipe/MemoryKnowledge/package-lock.json" "$context/MemoryKnowledge/package-lock.json"
cp "$recipe/Dockerfile" "$recipe/start-combined.sh" "$context/"
docker build -t agentmemory/memory-hub:alg-3427 "$context"
