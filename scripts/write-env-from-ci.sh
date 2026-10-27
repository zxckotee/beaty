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
PUBLIC_HTTPS_URL="${PUBLIC_HTTPS_URL:-}"
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

cat > "$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=beaty
ENVIRONMENT=production
WEB_PORT=${WEB_PORT}

POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATABASE_URL=postgresql+asyncpg://beaty:${POSTGRES_PASSWORD}@postgres:5432/beaty
REDIS_URL=redis://redis:6379/0

PLATFORM_BOT_TOKEN=${TELEGRAM_SECRET}
TELEGRAM_PROXY=${TELEGRAM_PROXY}

TOKEN_ENCRYPTION_KEY=${TOKEN_ENCRYPTION_KEY}
JWT_SECRET=${JWT_SECRET}

WEBHOOK_BASE_URL=${PUBLIC_URL}
MINIAPP_PUBLIC_URL=${PUBLIC_URL}
SENTRY_DSN=${SENTRY_DSN}
EOF
chmod 600 "$ENV_FILE"

# Legacy `docker-compose` on the server reads docker-compose.yml and .env by default.
# Git tracks the dev compose file; re-link after each deploy (git reset --hard restores dev files).
ln -sf .env.prod "$DEPLOY_PATH/.env"
ln -sf docker-compose.prod.yml "$DEPLOY_PATH/docker-compose.yml"

echo "Wrote $ENV_FILE (public URL: $PUBLIC_URL)"
echo "Linked .env and docker-compose.yml for plain docker-compose logs/ps on the server"
