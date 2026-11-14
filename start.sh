#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

PORT="${PORT:-8787}"

echo "=================================================="
echo "HGH 个人拍机助手已启动: http://127.0.0.1:${PORT}"
echo "若已开启 Tailscale，手机浏览器访问: http://<本机Tailscale_IP>:${PORT}"
echo "=================================================="

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
