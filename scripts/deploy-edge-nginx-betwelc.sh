#!/usr/bin/env bash
# Install host nginx vhost for betwelc.ru (HTTP; certbot adds HTTPS).
# Usage: bash scripts/deploy-edge-nginx-betwelc.sh [/root/beaty]

set -euo pipefail

SOURCE_PATH="${1:-/root/beaty}"
NGINX_CONF_SRC="$SOURCE_PATH/deploy/nginx-betwelc.edge.conf"
SITE_NAME="betwelc.ru.conf"

if [ ! -f "$NGINX_CONF_SRC" ]; then
  echo "ERROR: $NGINX_CONF_SRC not found"
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo ">>> nginx not found; install nginx on the host first"
  exit 1
fi

echo ">>> Installing edge nginx config for betwelc.ru"
install -m 644 "$NGINX_CONF_SRC" "/etc/nginx/sites-available/$SITE_NAME"
ln -sf "/etc/nginx/sites-available/$SITE_NAME" "/etc/nginx/sites-enabled/$SITE_NAME"

nginx -t
if systemctl is-active --quiet nginx; then
  systemctl reload nginx
else
  systemctl start nginx
fi
echo ">>> Edge nginx OK (betwelc.ru). Run: certbot --nginx -d betwelc.ru"