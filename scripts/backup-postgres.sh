#!/usr/bin/env bash
# Dump Beaty PostgreSQL (docker compose prod). Retain last 14 daily backups.
set -euo pipefail

DEPLOY_PATH="${1:-$(pwd)}"
BACKUP_DIR="${BACKUP_DIR:-$DEPLOY_PATH/backups}"
COMPOSE="docker compose -p beaty -f $DEPLOY_PATH/docker-compose.yml"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/beaty-$STAMP.sql.gz"

mkdir -p "$BACKUP_DIR"
$COMPOSE exec -T postgres pg_dump -U beaty -d beaty | gzip > "$OUT"
echo "Backup written: $OUT"

find "$BACKUP_DIR" -name 'beaty-*.sql.gz' -mtime +14 -delete 2>/dev/null || true
