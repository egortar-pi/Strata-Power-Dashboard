#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sudo install -d -m 755 /opt/ai-power-dashboard
sudo install -m 755 app.py /opt/ai-power-dashboard/app.py
sudo install -m 644 index.html /opt/ai-power-dashboard/index.html
sed "s/^User=CHANGE_ME$/User=$(id -un)/" ai-power-dashboard.service | sudo tee /etc/systemd/system/ai-power-dashboard.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now ai-power-dashboard
sudo systemctl --no-pager status ai-power-dashboard
printf '\nConnect from Windows: ssh -L 8092:127.0.0.1:8092 %s@SERVER_IP\nOpen http://127.0.0.1:8092 in Windows browser\n' "$(id -un)"
