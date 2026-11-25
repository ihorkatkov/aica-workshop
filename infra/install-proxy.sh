#!/bin/sh
set -eu
cd /home/boxd/aica-model-proxy
curl -fsSL https://github.com/router-for-me/CLIProxyAPI/releases/download/v8.1.3/CLIProxyAPI_8.1.3_linux_amd64.tar.gz -o release.tar.gz
curl -fsSL https://github.com/router-for-me/CLIProxyAPI/releases/download/v8.1.3/checksums.txt -o checksums.txt
expected=$(awk '/CLIProxyAPI_8.1.3_linux_amd64.tar.gz$/{print $1}' checksums.txt)
test -n "$expected"
printf '%s  release.tar.gz\n' "$expected" | sha256sum -c -
tar -xzf release.tar.gz
chmod 700 auth
chmod 600 auth/*.json config.yaml
sudo tee /etc/systemd/system/aica-model-proxy.service >/dev/null <<'UNIT'
[Unit]
Description=AICA workshop CLIProxyAPI (Codex)
After=network-online.target
Wants=network-online.target
[Service]
User=boxd
WorkingDirectory=/home/boxd/aica-model-proxy
ExecStart=/home/boxd/aica-model-proxy/cli-proxy-api -config /home/boxd/aica-model-proxy/config.yaml
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/boxd/aica-model-proxy
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now aica-model-proxy
sudo systemctl is-active aica-model-proxy
