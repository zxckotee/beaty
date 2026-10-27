#!/usr/bin/env bash
# Production compose wrapper (same flags as scripts/redeploy.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "Docker Compose is not installed" >&2
  exit 1
fi

if [ ! -f .env.prod ]; then
  echo ".env.prod not found (run deploy or scripts/write-env-from-ci.sh)" >&2
  exit 1
fi

exec "${DC[@]}" -p beaty -f docker-compose.prod.yml --env-file .env.prod "$@"
