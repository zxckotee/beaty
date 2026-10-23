#!/usr/bin/env bash
# Writes env/bootstrap.env on the server (tracked in git with placeholders; overwritten each deploy).
# Long-lived secrets live in .secrets.env — do not rotate TOKEN_ENCRYPTION_KEY casually.
set -euo pipefail

DEPLOY_PATH="${1:-$(pwd)}"
ENV_FILE="$DEPLOY_PATH/env/bootstrap.env"
SECRETS_FILE="$DEPLOY_PATH/.secrets.env"

: "${TELEGRAM_SECRET:?TELEGRAM_SECRET is required}"
PUBLIC_HOST="${PUBLIC_HOST:-localhost}"
WEB_PORT="${WEB_PORT:-4040}"
PUBLIC_HTTPS_URL="${PUBLIC_HTTPS_URL:-}"
TELEGRAM_PROXY="${TELEGRAM_PROXY:-}"
SENTRY_DSN="${SENTRY_DSN:-}"

umask 077
mkdir -p "$DEPLOY_PATH/env"

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

# Backward compatibility for scripts/docs that mention .env.prod
ln -sf env/bootstrap.env "$DEPLOY_PATH/.env.prod"
ln -sf env/bootstrap.env "$DEPLOY_PATH/.env"

echo "Wrote $ENV_FILE (public URL: $PUBLIC_URL)"
