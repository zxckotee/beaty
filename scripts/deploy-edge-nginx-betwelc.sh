#!/usr/bin/env bash
# Install host nginx vhost for betwelc.ru (HTTP; certbot adds HTTPS).
# Usage: bash scripts/deploy-edge-nginx-betwelc.sh [/root/beaty]

set -euo pipefail

SOURCE_PATH="${1:-/root/beaty}"
DOMAIN="${BETWELC_DOMAIN:-betwelc.ru}"
LE_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
HTTP_CONF="$SOURCE_PATH/deploy/nginx-betwelc.edge.conf"
HTTPS_CONF="$SOURCE_PATH/deploy/nginx-betwelc.edge.https.conf"
SITE_NAME="${DOMAIN}.conf"

if ! command -v nginx >/dev/null 2>&1; then
  echo ">>> nginx not found; install nginx on the host first"
  exit 1
fi

if [ -f "$LE_CERT" ] && [ -f "$HTTPS_CONF" ]; then
  NGINX_CONF_SRC="$HTTPS_CONF"
  echo ">>> Let's Encrypt cert found — installing HTTPS edge config for $DOMAIN"
elif [ -f "$HTTP_CONF" ]; then
  NGINX_CONF_SRC="$HTTP_CONF"
  echo ">>> Installing HTTP edge config for $DOMAIN (run enable-ssl-betwelc.sh for TLS)"
else
  echo "ERROR: no nginx template under $SOURCE_PATH/deploy/" >&2
  exit 1
fi

install -m 644 "$NGINX_CONF_SRC" "/etc/nginx/sites-available/$SITE_NAME"
ln -sf "/etc/nginx/sites-available/$SITE_NAME" "/etc/nginx/sites-enabled/$SITE_NAME"

nginx -t
if systemctl is-active --quiet nginx; then
  systemctl reload nginx
else
  systemctl start nginx
fi
echo ">>> Edge nginx OK (betwelc.ru). Run: certbot --nginx -d betwelc.ru"