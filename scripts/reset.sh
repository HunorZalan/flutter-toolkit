#!/usr/bin/env bash
# flutter-toolkit - restart the running server.
# Tries the OS-level service first; falls back to /api/restart over HTTP.
set -e

OS="$(uname -s)"
PLIST_LABEL="com.flutter-toolkit.server"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

case "$OS" in
Darwin*)
    if [ -f "$PLIST_PATH" ]; then
        uid=$(id -u)
        echo "Restarting LaunchAgent $PLIST_LABEL..."
        # Use bootout/bootstrap (Ventura+), fall back to unload/load
        launchctl bootout "gui/$uid/$PLIST_LABEL" 2>/dev/null \
            || launchctl unload "$PLIST_PATH" 2>/dev/null \
            || true
        # Kill any process still holding the port
        if command -v lsof >/dev/null 2>&1; then
            pid=$(lsof -ti :8742 2>/dev/null || true)
            [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
        fi
        sleep 1
        launchctl bootstrap "gui/$uid" "$PLIST_PATH" 2>/dev/null \
            || launchctl load "$PLIST_PATH"
        echo "Done."
        exit 0
    fi
    ;;
Linux*)
    if command -v systemctl >/dev/null 2>&1 && \
       systemctl --user is-enabled flutter-toolkit.service >/dev/null 2>&1; then
        echo "Restarting systemd --user service flutter-toolkit..."
        systemctl --user restart flutter-toolkit.service
        systemctl --user status --no-pager flutter-toolkit.service | head -5
        exit 0
    fi
    ;;
esac

echo "No installed service found. Calling /api/restart..."
if curl -s -X POST http://127.0.0.1:8742/api/restart | grep -q '"ok":true'; then
    echo "Server restarted."
else
    echo "Server not reachable at 127.0.0.1:8742"
    exit 1
fi
