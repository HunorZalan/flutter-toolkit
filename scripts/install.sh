#!/usr/bin/env bash
# =========================================================================
#  flutter-toolkit - one-shot installer (macOS / Linux).
#
#  Run from your Flutter project root for the full setup:
#      cd /path/to/my-flutter-app
#      bash /path/to/flutter-toolkit/scripts/install.sh
#
#  Does, in one shot:
#    1. pip install -e ".[all]"  (installs the `ftk` package + extras)
#    2. Adds Python Scripts dir to your shell PATH (persistent)
#    3. Registers the project at the cwd (if it has ftk.yaml)
#    4. macOS  -> installs ~/Library/LaunchAgents/com.flutter-toolkit.server.plist
#       Linux  -> installs ~/.config/systemd/user/flutter-toolkit.service
#    5. Starts the service and opens http://localhost:8742
#
#  Run from a directory without ftk.yaml and only steps 1-2 run.
# =========================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLKIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(pwd)"

if [ -t 1 ]; then
    RED='\033[31m'; GRN='\033[32m'; YEL='\033[33m'; CYA='\033[36m'; RST='\033[0m'
else
    RED=''; GRN=''; YEL=''; CYA=''; RST=''
fi

OS="$(uname -s)"
case "$OS" in
    Darwin*) OS_KIND="macos";;
    Linux*)  OS_KIND="linux";;
    *)       OS_KIND="other";;
esac

echo ""
echo -e "${CYA}=== flutter-toolkit installer ($OS_KIND) ===${RST}"
echo "Toolkit : $TOOLKIT_DIR"
echo "Project : $PROJECT_DIR"
echo ""

# --- Detect Python -------------------------------------------------------
PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver=$("$cand" -c 'import sys; print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")
        case "$ver" in
            3.1[0-9]|3.[2-9][0-9]) PY="$cand"; break;;
        esac
    fi
done
if [ -z "$PY" ]; then
    echo -e "${RED}[ERROR]${RST} Python 3.10+ not found."
    echo "        macOS:   brew install python"
    echo "        Debian:  sudo apt install python3 python3-pip python3-venv"
    echo "        Fedora:  sudo dnf install python3 python3-pip"
    exit 1
fi
echo -e "[1/5] $($PY --version 2>&1) at $(command -v $PY)"

if ! $PY -m pip --version >/dev/null 2>&1; then
    echo -e "${RED}[ERROR]${RST} pip is not available for $PY."
    echo "        Try:  $PY -m ensurepip --upgrade"
    exit 1
fi

PIP_ARGS=""
if $PY -m pip install --dry-run pip 2>&1 | grep -q "externally-managed-environment"; then
    echo -e "${YEL}[WARN]${RST}  Externally-managed Python. Using --user --break-system-packages."
    PIP_ARGS="--user --break-system-packages"
fi

echo "[2/5] Installing flutter-toolkit (with all extras)..."
$PY -m pip install --upgrade pip $PIP_ARGS --quiet 2>/dev/null || true
( cd "$TOOLKIT_DIR" && $PY -m pip install -e ".[all]" --upgrade $PIP_ARGS )

# --- Add Scripts dir to PATH --------------------------------------------
if [ -n "$PIP_ARGS" ]; then
    SCRIPTS_DIR=$($PY -c "import site; print(site.USER_BASE + '/bin')")
else
    SCRIPTS_DIR=$($PY -c "import sysconfig; print(sysconfig.get_path('scripts'))")
fi
echo "[3/5] Scripts dir: $SCRIPTS_DIR"

case ":$PATH:" in
    *":$SCRIPTS_DIR:"*)
        echo "      Already on PATH."
        ;;
    *)
        added=0
        for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile"; do
            [ -f "$rc" ] || continue
            if ! grep -Fq "flutter-toolkit: added by install.sh" "$rc"; then
                {
                    echo ""
                    echo "# flutter-toolkit: added by install.sh on $(date +%Y-%m-%d)"
                    echo "export PATH=\"$SCRIPTS_DIR:\$PATH\""
                } >> "$rc"
                echo -e "      ${GRN}Added to ${rc}${RST}"
                added=1
            fi
        done
        if [ $added -eq 0 ]; then
            echo -e "      ${YEL}No shell rc file found.${RST} Add to your shell startup:"
            echo "        export PATH=\"$SCRIPTS_DIR:\$PATH\""
        fi
        export PATH="$SCRIPTS_DIR:$PATH"
        ;;
esac

# --- Verify --------------------------------------------------------------
echo "[4/5] Verifying ftk install..."
$PY -m ftk --version

# --- Detect Flutter project (cwd -> registry fallback) ------------------
if [ ! -f "$PROJECT_DIR/ftk.yaml" ]; then
    echo -e "${YEL}[INFO]${RST}  No ftk.yaml in current directory. Checking registry..."
    FALLBACK=$($PY -c "
from ftk.projects import get_last_project_id, find_project, list_projects
import os
ps = list_projects()
fb = ps[0] if ps else None
e = find_project(get_last_project_id() or '') or fb
print(e.root if e and os.path.isdir(e.root) and os.path.isfile(os.path.join(e.root, 'ftk.yaml')) else '')
" 2>/dev/null || echo "")
    if [ -n "$FALLBACK" ]; then
        PROJECT_DIR="$FALLBACK"
        echo -e "        ${GRN}Found registered project: $PROJECT_DIR${RST}"
    fi
fi

if [ ! -f "$PROJECT_DIR/ftk.yaml" ]; then
    echo ""
    echo -e "${YEL}=== Toolkit installed, no project autostart configured ===${RST}"
    echo ""
    echo "To make the web UI auto-start on every login, open a NEW terminal,"
    echo "cd into your Flutter project (the one with ftk.yaml) and re-run:"
    echo ""
    echo "  cd /path/to/my-flutter-app"
    echo "  bash $SCRIPT_DIR/install.sh"
    echo ""
    echo "Or register the project first, then re-run from anywhere:"
    echo ""
    echo "  ftk projects add /path/to/my-flutter-app"
    echo "  bash $SCRIPT_DIR/install.sh"
    echo ""
    echo "Or just start the server manually:  ftk server"
    echo ""
    exit 0
fi

# --- Install service ----------------------------------------------------
echo "[5/5] Installing background service for project at $PROJECT_DIR..."

# Register project (no-op if already there)
$PY -m ftk projects add "$PROJECT_DIR" >/dev/null 2>&1 || true

# Resolve project id
PROJECT_ID="$($PY -c "from ftk.config import load_config;print(load_config(r'''$PROJECT_DIR''').id)" 2>/dev/null || echo "")"

FTK_BIN="$SCRIPTS_DIR/ftk"
if [ ! -x "$FTK_BIN" ]; then
    echo -e "${RED}[ERROR]${RST} ftk not found at $FTK_BIN"
    exit 1
fi

LOG_DIR="$PROJECT_DIR/.ftk"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/server.log"

if [ "$PROJECT_ID" ]; then
    SERVE_CMD="$FTK_BIN --project $PROJECT_ID server"
else
    SERVE_CMD="$FTK_BIN server"
fi

case "$OS_KIND" in
macos)
    PLIST_LABEL="com.flutter-toolkit.server"
    PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
    mkdir -p "$HOME/Library/LaunchAgents"

    # Build ProgramArguments tags
    PA_TAGS="        <string>$FTK_BIN</string>"
    if [ "$PROJECT_ID" ]; then
        PA_TAGS="$PA_TAGS
        <string>--project</string>
        <string>$PROJECT_ID</string>"
    fi
    PA_TAGS="$PA_TAGS
        <string>server</string>"

    # Capture current PATH so launchd can find Flutter, Python, Homebrew, etc.
    # LaunchAgents run with a minimal environment; without this, ftk can't
    # locate flutter/dart/pod and subprocess calls fail silently.
    LAUNCH_PATH="$PATH"

    # Also capture LANG/HOME so subprocesses behave identically to a shell
    LAUNCH_LANG="${LANG:-en_US.UTF-8}"
    LAUNCH_HOME="$HOME"

    # Replace existing
    if [ -f "$PLIST_PATH" ]; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        rm -f "$PLIST_PATH"
    fi

    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>
    <key>ProgramArguments</key>
    <array>
$PA_TAGS
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$LAUNCH_PATH</string>
        <key>HOME</key>
        <string>$LAUNCH_HOME</string>
        <key>LANG</key>
        <string>$LAUNCH_LANG</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG_FILE</string>
    <key>StandardErrorPath</key><string>$LOG_FILE</string>
</dict>
</plist>
EOF
    launchctl load "$PLIST_PATH"
    echo "      LaunchAgent : $PLIST_PATH"
    ;;

linux)
    UNIT_DIR="$HOME/.config/systemd/user"
    UNIT_FILE="$UNIT_DIR/flutter-toolkit.service"
    mkdir -p "$UNIT_DIR"

    EXEC_LINE="ExecStart=$SERVE_CMD"
    cat > "$UNIT_FILE" <<EOF
[Unit]
Description=flutter-toolkit web UI
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PATH"
Environment="LANG=${LANG:-en_US.UTF-8}"
$EXEC_LINE
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now flutter-toolkit.service
    echo "      systemd unit : $UNIT_FILE"
    ;;

*)
    echo -e "${YEL}[WARN]${RST} OS '$OS' not supported for service install."
    echo "      Start the server manually:  $SERVE_CMD"
    exit 0
    ;;
esac

# Wait up to ~10s for the server to come up
UP=1
for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if curl -sf http://127.0.0.1:8742/api/health >/dev/null 2>&1; then UP=0; break; fi
done

echo ""
if [ "$UP" = "0" ]; then
    echo -e "${GRN}=== Done - server is running ===${RST}"
    echo "URL       : http://127.0.0.1:8742"
    echo "Restart   : bash $SCRIPT_DIR/reset.sh"
    echo "Uninstall : bash $SCRIPT_DIR/uninstall.sh"
    if [ "$OS_KIND" = "macos" ]; then
        open http://127.0.0.1:8742 2>/dev/null || true
    elif [ "$OS_KIND" = "linux" ]; then
        xdg-open http://127.0.0.1:8742 2>/dev/null || true
    fi
else
    echo -e "${YEL}=== Done - service installed, give it a few seconds ===${RST}"
    echo "URL       : http://127.0.0.1:8742"
    echo "Logs      : $LOG_FILE"
fi
echo ""
