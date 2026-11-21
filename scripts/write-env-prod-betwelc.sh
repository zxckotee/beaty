#!/usr/bin/env bash
# Собирает .env.prod для betwelc.ru (HTTPS + Mini App).
# На сервере:
#   TELEGRAM_SECRET=<platform bot token> bash scripts/write-env-prod-betwelc.sh [/root/beaty]
#
# Берёт POSTGRES_PASSWORD, TOKEN_ENCRYPTION_KEY, JWT_SECRET из .secrets.env (не перезаписывает файл).
set -euo pipefail

DEPLOY_PATH="${1:-$(pwd)}"
cd "$DEPLOY_PATH"

export PUBLIC_HTTPS_URL="${PUBLIC_HTTPS_URL:-https://betwelc.ru}"
export PUBLIC_WEB_URL="${PUBLIC_WEB_URL:-https://betwelc.ru}"
export TENANT_UI_MODE="${TENANT_UI_MODE:-both}"
export WEB_PORT="${WEB_PORT:-4040}"
export WEB_UI_PORT="${WEB_UI_PORT:-3030}"
export WEB_DEFAULT_TENANT="${WEB_DEFAULT_TENANT:-}"
export PUBLIC_HOST="${PUBLIC_HOST:-88.218.121.216}"

: "${TELEGRAM_SECRET:?Set TELEGRAM_SECRET (platform bot token, same as GitHub secret)}"

exec bash scripts/write-env-from-ci.sh "$DEPLOY_PATH"