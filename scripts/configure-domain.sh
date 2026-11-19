#!/usr/bin/env bash
# Points infrastructure/nginx/nginx.conf at a new domain: server_name, the
# certificate paths and the HTTP->HTTPS redirect port. Used by INSTALL.md
# on a fresh server; the domain is otherwise written literally in nginx.conf.
#
# Usage: scripts/configure-domain.sh <dominio> [porta-https]
#   scripts/configure-domain.sh sos.cliente.it          # server dedicato, 443
#   scripts/configure-domain.sh sos.cliente.it 8443     # 443 occupata da altro
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN="${1:?uso: scripts/configure-domain.sh <dominio> [porta-https]}"
HTTPS_PORT="${2:-443}"
CONF="infrastructure/nginx/nginx.conf"

if [ "$HTTPS_PORT" = "443" ]; then PORT_SUFFIX=""; else PORT_SUFFIX=":$HTTPS_PORT"; fi

# The HTTPS server block is the one with `listen 443 ssl`.
sed -i -E \
  -e "/listen 443 ssl/,/ssl_certificate_key/ s|^(\s*server_name ).*;|\1$DOMAIN _;|" \
  -e "s|/etc/letsencrypt/live/[^/]+/|/etc/letsencrypt/live/$DOMAIN/|g" \
  -e "s|return 301 https://\\\$host(:[0-9]+)?\\\$request_uri;|return 301 https://\$host$PORT_SUFFIX\$request_uri;|" \
  "$CONF"

echo "==> $CONF ora punta a $DOMAIN (porta HTTPS $HTTPS_PORT):"
grep -nE 'server_name|ssl_certificate|return 301' "$CONF"
