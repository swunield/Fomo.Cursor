#!/bin/bash
set -euo pipefail
cd /opt/Fomo
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
install -m 644 /opt/Fomo/deploy/fomo.service /etc/systemd/system/fomo.service
install -m 644 /opt/Fomo/deploy/nginx-fomo.conf /etc/nginx/conf.d/fomo.conf
systemctl daemon-reload
systemctl enable --now fomo
nginx -t
systemctl enable --now nginx
systemctl reload nginx
