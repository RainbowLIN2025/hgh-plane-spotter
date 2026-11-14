#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_LABEL="com.hgh.planespotter"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_DIR="${PROJECT_DIR}/logs"
PORT="${PORT:-8787}"

mkdir -p "$HOME/Library/LaunchAgents" "${LOG_DIR}"

if [ ! -x "${PROJECT_DIR}/.venv/bin/uvicorn" ]; then
  python3 -m venv "${PROJECT_DIR}/.venv"
  "${PROJECT_DIR}/.venv/bin/pip" install -q -r "${PROJECT_DIR}/requirements.txt"
fi

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PROJECT_DIR}/.venv/bin/uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>${PORT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AIRLABS_API_KEY</key>
        <string>${AIRLABS_API_KEY:-}</string>
        <key>BARK_URL</key>
        <string>${BARK_URL:-}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/stderr.log</string>
</dict>
</plist>
EOF

# 若之前已加载，先卸载再重新加载
launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"

echo "=================================================="
echo "已安装并启动后台服务: ${PLIST_LABEL}"
echo "本机访问: http://127.0.0.1:${PORT}"
echo "日志目录: ${LOG_DIR}"
echo "停止并关闭服务请运行: ${PROJECT_DIR}/scripts/uninstall_launchd.sh"
echo "=================================================="
