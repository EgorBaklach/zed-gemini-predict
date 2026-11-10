#!/usr/bin/env bash
set -euo pipefail

cd ~/zed-gemini-predict
git fetch origin
git reset --hard origin/main
cp ~/zed-gemini-predict/systemd/zed-fim-proxy.service ~/.config/systemd/user/zed-fim-proxy.service
systemctl --user daemon-reload
systemctl --user enable --now zed-fim-proxy.service
systemctl --user restart zed-fim-proxy.service
systemctl --user status zed-fim-proxy.service --no-pager -l | head -n 15
