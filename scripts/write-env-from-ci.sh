#!/usr/bin/env bash
# Builds .env.prod for docker-compose.prod.yml from CI-provided variables.
# Long-lived secrets are generated once and kept in .secrets.env: rotating
# TOKEN_ENCRYPTION_KEY would make stored bot tokens undecryptable, and
# POSTGRES_PASSWORD is baked into the existing database volume.
set -euo pipefail

DEPLOY_PATH="${1:-$(pwd)}"
ENV_FILE="$DEPLOY_PATH/.env.prod"
SECRETS_FILE="$DEPLOY_PATH/.secrets.env"

: "${TELEGRAM_SECRET:?TELEGRAM_SECRET is required}"
PUBLIC_HOST="${PUBLIC_HOST:-localhost}"
WEB_PORT="${WEB_PORT:-4040}"
WEB_UI_PORT="${WEB_UI_PORT:-3030}"
WEB_DEFAULT_TENANT="${WEB_DEFAULT_TENANT:-}"
PUBLIC_HTTPS_URL="${PUBLIC_HTTPS_URL:-}"
PUBLIC_WEB_URL="${PUBLIC_WEB_URL:-}"
TENANT_UI_MODE="${TENANT_UI_MODE:-both}"
TELEGRAM_PROXY="${TELEGRAM_PROXY:-}"
SENTRY_DSN="${SENTRY_DSN:-}"

umask 077

if [ ! -f "$SECRETS_FILE" ]; then
  echo "Generating persistent secrets in $SECRETS_FILE"
  {
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
    echo "TOKEN_ENCRYPTION_KEY=$(openssl rand -hex 32)"
    echo "JWT_SECRET=$(openssl rand -hex 32)"
  } > "$SECRETS_FILE"
fi
chmod 600 "$SECRETS_FILE"

# shellcheck disable=SC1090
set -a
. "$SECRETS_FILE"
set +a

if [ -n "$PUBLIC_HTTPS_URL" ]; then
  PUBLIC_URL="$PUBLIC_HTTPS_URL"
else
  PUBLIC_URL="http://${PUBLIC_HOST}:${WEB_PORT}"
fi

if [ -n "$PUBLIC_WEB_URL" ]; then
  WEB_PUBLIC="$PUBLIC_WEB_URL"
elif [ -n "$PUBLIC_HTTPS_URL" ]; then
  WEB_PUBLIC="$PUBLIC_HTTPS_URL"
else
  WEB_PUBLIC=""
fi

if [ -n "$PUBLIC_HTTPS_URL" ]; then
  WEB_COOKIE_SECURE="true"
else
  WEB_COOKIE_SECURE="false"
fi

cat > "$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=beaty
ENVIRONMENT=production
WEB_PORT=${WEB_PORT}
WEB_UI_PORT=${WEB_UI_PORT}
WEB_DEFAULT_TENANT=${WEB_DEFAULT_TENANT}

POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATABASE_URL=postgresql+asyncpg://beaty:${POSTGRES_PASSWORD}@postgres:5432/beaty
REDIS_URL=redis://redis:6379/0

PLATFORM_BOT_TOKEN=${TELEGRAM_SECRET}
PLATFORM_TELEGRAM_WEBHOOK_SECRET=${PLATFORM_TELEGRAM_WEBHOOK_SECRET:-${TELEGRAM_WEBHOOK_SECRET:-$(openssl rand -hex 16)}}
TELEGRAM_PROXY=${TELEGRAM_PROXY}

TOKEN_ENCRYPTION_KEY=${TOKEN_ENCRYPTION_KEY}
JWT_SECRET=${JWT_SECRET}

WEBHOOK_BASE_URL=${PUBLIC_URL}
PUBLIC_WEB_URL=${WEB_PUBLIC}
TENANT_UI_MODE=${TENANT_UI_MODE}
WEB_COOKIE_SECURE=${WEB_COOKIE_SECURE}
SENTRY_DSN=${SENTRY_DSN}
EOF
chmod 600 "$ENV_FILE"

# Legacy `docker-compose` on the server reads docker-compose.yml and .env by default.
# Git tracks the dev compose file; re-link after each deploy (git reset --hard restores dev files).
ln -sf .env.prod "$DEPLOY_PATH/.env"
ln -sf docker-compose.prod.yml "$DEPLOY_PATH/docker-compose.yml"

echo "Wrote $ENV_FILE (public URL: $PUBLIC_URL)"
echo "Linked .env and docker-compose.yml for plain docker-compose logs/ps on the server"
