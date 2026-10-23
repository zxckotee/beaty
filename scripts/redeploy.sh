#!/usr/bin/env bash
# Usage: redeploy.sh [build|nobuild]
set -euo pipefail

MODE="${1:-build}"
DEPLOY_PATH="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DEPLOY_PATH"

COMPOSE=( "$DEPLOY_PATH/scripts/compose-prod.sh" )

if [ ! -f .env.prod ]; then
  echo ".env.prod not found, run scripts/write-env-from-ci.sh first" >&2
  exit 1
fi

bash "$DEPLOY_PATH/scripts/setup-server-compose-links.sh" "$DEPLOY_PATH"

WEB_PORT="$(grep -E '^WEB_PORT=' .env.prod | cut -d= -f2)"
WEB_PORT="${WEB_PORT:-4040}"

case "$MODE" in
  build)
    echo "Building images and starting services"
    "${COMPOSE[@]}" up -d --build --remove-orphans
    ;;
  nobuild)
    echo "Starting services without rebuild"
    "${COMPOSE[@]}" up -d --remove-orphans
    ;;
  *)
    echo "Unknown mode: $MODE (expected build|nobuild)" >&2
    exit 1
    ;;
esac

docker image prune -f >/dev/null || true

echo "Waiting for http://127.0.0.1:${WEB_PORT}/health"
for attempt in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${WEB_PORT}/health" >/dev/null 2>&1; then
    echo "Healthcheck passed (attempt $attempt)"
    "${COMPOSE[@]}" ps
    exit 0
  fi
  sleep 3
done

echo "Healthcheck failed" >&2
"${COMPOSE[@]}" ps >&2 || true
"${COMPOSE[@]}" logs --tail 100 api platform-bot web >&2 || true
exit 1
