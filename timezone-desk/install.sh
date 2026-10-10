#!/usr/bin/env bash
# 把时区插件加载到 Ubuntu 桌面，并在登录时自动出现。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DEST="$DATA_HOME/timezone-desk"
APP_DIR="$DATA_HOME/applications"
AUTO_DIR="$CONFIG_HOME/autostart"
LOG="$CONFIG_HOME/timezone-desk/run.log"

mkdir -p "$DEST" "$APP_DIR" "$AUTO_DIR" "$(dirname "$LOG")"
cp -f "$ROOT/timezone_desk.py" "$ROOT/cities.py" "$ROOT/clockfmt.py" "$ROOT/style.css" "$ROOT/icon.svg" "$DEST/"
chmod 755 "$DEST/timezone_desk.py"

DESKTOP_BODY="$(cat <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=时区
GenericName=时区转换
Comment=在桌面上转换柏林、上海和其他城市的时间
Exec=/usr/bin/python3 $DEST/timezone_desk.py
Icon=$DEST/icon.svg
Terminal=false
Categories=Utility;Clock;
Keywords=时区;timezone;clock;柏林;上海;
StartupNotify=false
StartupWMClass=com.toolkit.TimezoneDesk
EOF
)"

printf '%s\n' "$DESKTOP_BODY" > "$APP_DIR/timezone-desk.desktop"
printf '%s\nX-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=2\n' "$DESKTOP_BODY" > "$AUTO_DIR/timezone-desk.desktop"
chmod 644 "$APP_DIR/timezone-desk.desktop" "$AUTO_DIR/timezone-desk.desktop"
update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true

PATTERN='^/usr/bin/python3 .*/timezone_desk\.py$'
if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  pkill -f "$PATTERN" || true
  sleep 0.3
fi

setsid /usr/bin/python3 "$DEST/timezone_desk.py" >>"$LOG" 2>&1 </dev/null &
sleep 0.4

echo "时区插件已加载到桌面。"
echo "拖动卡片可以换位置。点时间可以换算，点 + 可以添加地点。"
echo "删除插件：$(dirname "$0")/uninstall.sh"
