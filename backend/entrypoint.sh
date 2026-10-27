#!/bin/sh
set -e

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  alembic upgrade head
fi

if [ "${RUN_SEED_IF_EMPTY:-false}" = "true" ]; then
  python -m scripts.seed || true
fi

exec "$@"
