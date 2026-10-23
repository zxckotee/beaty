#!/usr/bin/env bash
# View logs for the CI/production stack (project name: beaty).
# Examples:
#   scripts/logs.sh
#   scripts/logs.sh -f api
#   scripts/logs.sh --tail=200 worker platform-bot
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$#" -eq 0 ]; then
  exec "$SCRIPT_DIR/compose-prod.sh" logs -f --tail=200
fi
exec "$SCRIPT_DIR/compose-prod.sh" logs "$@"
