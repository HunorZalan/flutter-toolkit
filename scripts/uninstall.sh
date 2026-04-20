#!/usr/bin/env bash
# flutter-toolkit uninstaller (macOS / Linux).
# Usage:  bash scripts/uninstall.sh
set -e
cd "$(dirname "$0")/.."

echo ""
echo "=== flutter-toolkit uninstaller ==="
echo ""

PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then echo "[ERROR] Python not found."; exit 1; fi

echo "[1/4] Stopping background service if present..."
case "$(uname -s)" in
Darwin*)
    PLIST_PATH="$HOME/Library/LaunchAgents/com.flutter-toolkit.server.plist"
    if [ -f "$PLIST_PATH" ]; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        rm -f "$PLIST_PATH"
        echo "      LaunchAgent removed."
    fi
    ;;
Linux*)
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl --user is-enabled flutter-toolkit.service >/dev/null 2>&1; then
            systemctl --user disable --now flutter-toolkit.service || true
            rm -f "$HOME/.config/systemd/user/flutter-toolkit.service"
            systemctl --user daemon-reload || true
            echo "      systemd --user unit removed."
        fi
    fi
    ;;
esac
# Kill anything still listening on the default port
if command -v lsof >/dev/null 2>&1; then
    pid=$(lsof -ti :8742 2>/dev/null || true)
    if [ -n "$pid" ]; then kill -9 $pid 2>/dev/null || true; fi
fi

echo "[2/4] Removing flutter-toolkit Python package..."
$PY -m pip uninstall -y flutter-toolkit || true

echo "[3/4] Cleaning PATH entries from shell rc files..."
for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile"; do
    [ -f "$rc" ] || continue
    if grep -q "flutter-toolkit: added by install.sh" "$rc"; then
        tmp=$(mktemp)
        awk '
            /^# flutter-toolkit: added by install\.sh/ { skip=3; next }
            skip > 0 { skip--; next }
            { print }
        ' "$rc" > "$tmp" && mv "$tmp" "$rc"
        echo "      Cleaned $rc"
    fi
done

echo "[4/4] Registry folder: ~/.ftk"
read -p "      Remove the ftk registry (project list)? [y/N] " ans
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    rm -rf "$HOME/.ftk"
    echo "      Removed."
else
    echo "      Kept."
fi

echo ""
echo "Done."
