#!/usr/bin/env bash
# flutter-toolkit - restart the running server.
# Tries the OS-level service first; falls back to /api/restart over HTTP.
set -e

case "$(uname -s)" in
Darwin*)
    PLIST_PATH="$HOME/Library/LaunchAgents/com.flutter-toolkit.server.plist"
    if [ -f "$PLIST_PATH" ]; then
        echo "Restarting LaunchAgent com.flutter-toolkit.server..."
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        if command -v lsof >/dev/null 2>&1; then
            pid=$(lsof -ti :8742 2>/dev/null || true)
            if [ -n "$pid" ]; then kill -9 $pid 2>/dev/null || true; fi
        fi
        sleep 1
        launchctl load "$PLIST_PATH"
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
