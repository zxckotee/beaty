#!/usr/bin/env bash
# Копирует deploy/env.prod -> .env.prod (подставляет секреты из .secrets.env если есть).
set -euo pipefail

DEPLOY_PATH="${1:-$(pwd)}"
SRC="$DEPLOY_PATH/deploy/env.prod"
DEST="$DEPLOY_PATH/.env.prod"
SECRETS="$DEPLOY_PATH/.secrets.env"

if [ ! -f "$SRC" ]; then
  echo "Missing $SRC" >&2
  exit 1
fi

cp "$SRC" "$DEST"
chmod 600 "$DEST"

escape_sed() {
  printf '%s' "$1" | sed -e 's/[&/\]/\\&/g'
}

if [ -f "$SECRETS" ]; then
  # shellcheck disable=SC1090
  set -a
  . "$SECRETS"
  set +a
  if [ -n "${POSTGRES_PASSWORD:-}" ]; then
    pg="$(escape_sed "$POSTGRES_PASSWORD")"
    sed -i "s/CHANGEME_POSTGRES/${pg}/g" "$DEST"
  fi
  if [ -n "${TOKEN_ENCRYPTION_KEY:-}" ]; then
    sed -i "s/CHANGEME_TOKEN_ENC/$(escape_sed "$TOKEN_ENCRYPTION_KEY")/g" "$DEST"
  fi
  if [ -n "${JWT_SECRET:-}" ]; then
    sed -i "s/CHANGEME_JWT/$(escape_sed "$JWT_SECRET")/g" "$DEST"
  fi
fi

if [ -n "${TELEGRAM_SECRET:-}" ]; then
  sed -i "s/CHANGEME_PLATFORM_BOT/$(escape_sed "$TELEGRAM_SECRET")/g" "$DEST"
fi

echo "Installed $DEST (set PLATFORM_BOT_TOKEN if still CHANGEME)"