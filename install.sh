#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
user="$(id -un)"
home_dir="$(getent passwd "$user" | cut -d: -f6)"
data_dir="$home_dir/.local/share/ai-power-dashboard"
if [[ -z "$home_dir" || "$user" == root ]]; then
  echo 'Run installer as the regular Ubuntu account, not root.' >&2
  exit 1
fi
sudo install -d -m 755 /opt/ai-power-dashboard
install -d -m 700 "$data_dir"
sudo install -m 755 app.py /opt/ai-power-dashboard/app.py
sudo install -m 644 index.html /opt/ai-power-dashboard/index.html
if [[ ! -e /etc/systemd/system/ai-power-dashboard.service ]]; then
  sed -e "s|User=CHANGE_ME|User=$user|" -e "s|CHANGE_DATA_DIR|$data_dir|g" ai-power-dashboard.service | sudo tee /etc/systemd/system/ai-power-dashboard.service >/dev/null
  echo 'Installed a new systemd service, bound to localhost by default.'
else
  echo 'Preserving existing systemd service (including LAN bindings and overrides).'
fi
sudo systemctl daemon-reload
sudo systemctl enable ai-power-dashboard
sudo systemctl restart ai-power-dashboard
sudo systemctl --no-pager status ai-power-dashboard
printf '\nDatabase: %s/history.sqlite3\n' "$data_dir"
