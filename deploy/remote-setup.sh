#!/bin/bash
set -euo pipefail
cd /opt/Fomo
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
install -m 644 /opt/Fomo/deploy/fomo.service /etc/systemd/system/fomo.service
install -m 644 /opt/Fomo/deploy/nginx-fomo.conf /etc/nginx/conf.d/fomo.conf
install -m 644 /opt/Fomo/deploy/nginx-fomo-ip.conf /etc/nginx/conf.d/fomo-ip.conf
# Certbot may mark the domain :80 block as default_server and 404 other hosts.
sed -i 's/listen 80 default_server;/listen 80;/' /etc/nginx/conf.d/fomo.conf || true
sed -i 's/listen \[::\]:80 default_server;/listen [::]:80;/' /etc/nginx/conf.d/fomo.conf || true
systemctl daemon-reload
systemctl enable --now fomo
systemctl restart fomo
nginx -t
systemctl enable --now nginx
systemctl reload nginx
