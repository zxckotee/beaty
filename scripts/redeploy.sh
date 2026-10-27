#!/usr/bin/env bash
# Usage: redeploy.sh [build|nobuild]
set -euo pipefail

MODE="${1:-build}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_PATH="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$DEPLOY_PATH"

COMPOSE=("$SCRIPT_DIR/compose-prod.sh")

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "Docker Compose is not installed" >&2
  exit 1
fi

# docker-compose 1.29.x + modern Docker Engine raises KeyError: 'ContainerConfig'
# when recreating containers. Stop and remove the stack first so `up` creates
# fresh containers instead of hitting the recreate path.
legacy_compose_up() {
  if [ "${DC[0]}" = "docker-compose" ]; then
    echo "Legacy docker-compose detected: stopping stack before up (ContainerConfig workaround)"
    "${COMPOSE[@]}" down --remove-orphans || true
  fi
  "${COMPOSE[@]}" up -d --remove-orphans "$@"
}

if [ ! -f .env.prod ]; then
  echo ".env.prod not found, run scripts/write-env-from-ci.sh first" >&2
  exit 1
fi

WEB_PORT="$(grep -E '^WEB_PORT=' .env.prod | cut -d= -f2)"
WEB_PORT="${WEB_PORT:-4040}"

case "$MODE" in
  build)
    echo "Building images and starting services"
    legacy_compose_up --build
    ;;
  nobuild)
    echo "Starting services without rebuild"
    legacy_compose_up
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
