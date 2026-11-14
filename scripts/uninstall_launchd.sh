#!/usr/bin/env bash
set -euo pipefail

PLIST_LABEL="com.hgh.planespotter"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || true
rm -f "${PLIST_PATH}"

echo "已彻底停止并关闭后台服务 (${PLIST_LABEL})，开机自启也已取消。"
