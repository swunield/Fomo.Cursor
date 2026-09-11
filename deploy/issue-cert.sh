#!/bin/bash
set -euo pipefail
DOMAIN=fomo.niceshotgame.xyz
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect
systemctl enable --now certbot-renew.timer
nginx -t
systemctl reload nginx
echo "HTTPS ready: https://$DOMAIN/"
