#!/usr/bin/env bash
# One-time (or renew) Let's Encrypt for betwelc.ru on host nginx.
# Usage on VPS:
#   CERTBOT_EMAIL=you@example.com bash scripts/enable-ssl-betwelc.sh [/root/beaty]
#
# Prerequisites: DNS A betwelc.ru -> this host, nginx vhost from deploy-edge-nginx-betwelc.sh

set -euo pipefail

DOMAIN="${BETWELC_DOMAIN:-betwelc.ru}"
DEPLOY_PATH="${1:-/root/beaty}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

if [ -z "$CERTBOT_EMAIL" ]; then
  echo "Set CERTBOT_EMAIL (for Let's Encrypt expiry notices)." >&2
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx is not installed" >&2
  exit 1
fi

if [ -f "$DEPLOY_PATH/scripts/deploy-edge-nginx-betwelc.sh" ]; then
  bash "$DEPLOY_PATH/scripts/deploy-edge-nginx-betwelc.sh" "$DEPLOY_PATH"
fi

if ! command -v certbot >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y certbot python3-certbot-nginx
fi

echo ">>> Requesting certificate for $DOMAIN"
certbot --nginx -d "$DOMAIN" \
  --non-interactive --agree-tos \
  --email "$CERTBOT_EMAIL" \
  --redirect

# certbot edits nginx, but a plain HTTP deploy/*.edge.conf overwrites TLS; pin vhost from repo.
if [ -f "$DEPLOY_PATH/deploy/nginx-betwelc.edge.https.conf" ]; then
  echo ">>> Installing tracked HTTPS nginx vhost (SNI for $DOMAIN on :443)"
  bash "$DEPLOY_PATH/scripts/deploy-edge-nginx-betwelc.sh" "$DEPLOY_PATH"
fi

nginx -t
systemctl reload nginx

echo ">>> TLS certificate name (must be $DOMAIN, not swingfox.ru)"
if ! echo | openssl s_client -connect "${DOMAIN}:443" -servername "$DOMAIN" 2>/dev/null \
  | openssl x509 -noout -subject 2>/dev/null | grep -q "CN = ${DOMAIN}"; then
  echo "ERROR: nginx still serves the wrong certificate for SNI $DOMAIN." >&2
  echo "Check: grep -R 'listen.*443' /etc/nginx/sites-enabled/ — betwelc must have ssl_certificate for $DOMAIN." >&2
  exit 1
fi

echo ">>> HTTPS check"
curl -fsS "https://${DOMAIN}/health" | head -3

echo ""
echo "Next steps:"
echo "  1. GitHub Secret PUBLIC_HTTPS_URL=https://${DOMAIN}"
echo "  2. cd $DEPLOY_PATH && ./scripts/redeploy.sh nobuild"
echo "  3. Telegram: Mini App requires HTTPS; test Web App button in bot"