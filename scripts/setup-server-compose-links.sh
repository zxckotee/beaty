#!/usr/bin/env bash
# Run on the server after git pull/reset (called from write-env-from-ci.sh).
# Makes plain `docker-compose logs -f` target the CI/production stack in /root/beaty.
set -euo pipefail

DEPLOY_PATH="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

if [ ! -f "$DEPLOY_PATH/.env.prod" ]; then
  echo "setup-server-compose-links: .env.prod missing, skip" >&2
  exit 1
fi

if [ ! -f "$DEPLOY_PATH/docker-compose.prod.yml" ]; then
  echo "setup-server-compose-links: docker-compose.prod.yml missing" >&2
  exit 1
fi

cd "$DEPLOY_PATH"

# Default compose file + env (docker-compose v1 and compose v2 read .env from project dir).
ln -sf docker-compose.prod.yml docker-compose.yml
ln -sf .env.prod .env

# Same project name as redeploy.sh (-p beaty); also set explicitly if cwd name differs.
if ! grep -q '^COMPOSE_PROJECT_NAME=' .env.prod 2>/dev/null; then
  echo "COMPOSE_PROJECT_NAME=beaty" >> .env.prod
fi
grep -q '^COMPOSE_PROJECT_NAME=' .env || echo "COMPOSE_PROJECT_NAME=beaty" >> .env

echo "Server compose links: docker-compose.yml -> docker-compose.prod.yml, .env -> .env.prod"
