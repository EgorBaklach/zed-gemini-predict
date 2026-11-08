#!/usr/bin/env bash
# Deploy the working copy (where this script lives) into the WSL runtime clone used by systemd
# and restart the service. Run inside WSL:  bash scripts/deploy_wsl.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="${ZED_BRIDGE_RUNTIME:-$HOME/zed-gemini-predict}"

if [ "$SRC" != "$DST" ]; then
  cp "$SRC/zed_fim_proxy.py" "$DST/"
  rm -rf "$DST/bridge" && cp -r "$SRC/bridge" "$DST/bridge"
  mkdir -p "$DST/tests" && cp "$SRC"/tests/*.py "$DST/tests/"
  find "$DST/bridge" -name __pycache__ -prune -exec rm -rf {} +
fi

python3 -m py_compile "$DST/zed_fim_proxy.py" "$DST"/bridge/*.py "$DST"/bridge/php/*.py
systemctl --user restart zed-fim-proxy.service
sleep 1
systemctl --user is-active zed-fim-proxy.service
journalctl --user -u zed-fim-proxy.service -n 1 --no-pager -o cat
