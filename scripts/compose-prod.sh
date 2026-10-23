#!/usr/bin/env bash
# Production Docker Compose wrapper (same flags as CI deploy / redeploy.sh).
# Usage: scripts/compose-prod.sh logs -f api
#        scripts/compose-prod.sh ps
set -euo pipefail

DEPLOY_PATH="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEPLOY_PATH"

if [ ! -f .env.prod ]; then
  echo "Missing .env.prod — run scripts/write-env-from-ci.sh or wait for CI deploy." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "Docker Compose is not installed" >&2
  exit 1
fi

exec "${DC[@]}" -p beaty -f docker-compose.prod.yml --env-file .env.prod "$@"
