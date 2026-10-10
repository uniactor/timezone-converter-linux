#!/usr/bin/env bash
# 从桌面删除时区插件。个人地点设置默认保留。
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

PATTERN='^/usr/bin/python3 .*/timezone_desk\.py$'
if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  pkill -f "$PATTERN" || true
  sleep 0.3
fi

rm -f "$DATA_HOME/applications/timezone-desk.desktop"
rm -f "$CONFIG_HOME/autostart/timezone-desk.desktop"
rm -rf "$DATA_HOME/timezone-desk"
update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true

if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$CONFIG_HOME/timezone-desk"
  echo "时区插件和已保存的地点都已删除。"
else
  echo "时区插件已从桌面删除。"
  echo "地点设置仍留在 $CONFIG_HOME/timezone-desk/ 。若要一并清掉，再运行一次并加上 --purge。"
fi
