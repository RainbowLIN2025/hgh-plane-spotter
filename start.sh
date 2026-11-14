#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

echo "=================================================="
echo "HGH 个人拍机助手已启动: http://0.0.0.0:8000"
echo "若已开启 Tailscale，手机浏览器访问: http://<本机Tailscale_IP>:8000"
echo "=================================================="

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
