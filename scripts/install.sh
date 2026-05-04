#!/usr/bin/env bash
# =========================================================================
#  flutter-toolkit - one-shot installer (macOS / Linux).
#
#  Run from your Flutter project root for the full setup:
#      cd /path/to/my-flutter-app
#      bash /path/to/flutter-toolkit/scripts/install.sh
#
#  If the service is already installed and you just added a new project,
#  re-running this script will register the project and restart the service
#  automatically — a full reinstall is NOT needed.
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

PLIST_LABEL="com.flutter-toolkit.server"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
SYSTEMD_UNIT="$HOME/.config/systemd/user/flutter-toolkit.service"

echo ""
echo -e "${CYA}=== flutter-toolkit installer ($OS_KIND) ===${RST}"
echo "Toolkit : $TOOLKIT_DIR"
echo "Project : $PROJECT_DIR"
echo ""

# =========================================================================
# launchctl helpers — Ventura+ (macOS 13+) requires bootstrap/bootout.
# Falls back to the legacy load/unload on older systems.
# =========================================================================
_launchctl_load() {
    local plist="$1" label="$2" uid
    uid=$(id -u)
    if launchctl bootstrap "gui/$uid" "$plist" 2>/dev/null; then
        return 0
    fi
    launchctl load "$plist" 2>/dev/null || true
}

_launchctl_unload() {
    local plist="$1" label="$2" uid
    uid=$(id -u)
    launchctl bootout "gui/$uid/$label" 2>/dev/null \
        || launchctl unload "$plist" 2>/dev/null \
        || true
    # Kill any leftover process holding the port
    if command -v lsof >/dev/null 2>&1; then
        local pid
        pid=$(lsof -ti :8742 2>/dev/null || true)
        [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
    fi
}

_service_installed() {
    case "$OS_KIND" in
    macos) [ -f "$PLIST_PATH" ];;
    linux) systemctl --user is-enabled flutter-toolkit.service >/dev/null 2>&1;;
    *) return 1;;
    esac
}

# =========================================================================
# Detect Python
# =========================================================================
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
    echo "        Debian:  sudo apt install python3 python3-pip"
    echo "        Fedora:  sudo dnf install python3 python3-pip"
    exit 1
fi

# =========================================================================
# FAST PATH — service already installed, just add project + restart
# =========================================================================
if _service_installed; then
    if [ -f "$PROJECT_DIR/ftk.yaml" ]; then
        echo -e "${CYA}Service is already installed. Registering project and restarting...${RST}"
        # Install package upgrade silently if needed
        ( cd "$TOOLKIT_DIR" && $PY -m pip install -e ".[all]" --upgrade -q ) || true
        $PY -m ftk projects add "$PROJECT_DIR" >/dev/null 2>&1 || true

        case "$OS_KIND" in
        macos)
            _launchctl_unload "$PLIST_PATH" "$PLIST_LABEL"
            sleep 1
            _launchctl_load "$PLIST_PATH" "$PLIST_LABEL"
            ;;
        linux)
            systemctl --user daemon-reload
            systemctl --user restart flutter-toolkit.service
            ;;
        esac

        echo -e "${GRN}Done. Project registered and service restarted.${RST}"
        echo "URL : http://127.0.0.1:8742"
        echo ""
        exit 0
    fi
fi

# =========================================================================
# FULL INSTALL
# =========================================================================
echo -e "[1/5] $($PY --version 2>&1) at $(command -v $PY)"

if ! $PY -m pip --version >/dev/null 2>&1; then
    echo -e "${RED}[ERROR]${RST} pip is not available for $PY."
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

# ---- PATH ---------------------------------------------------------------
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
        [ $added -eq 0 ] && echo -e "      ${YEL}No shell rc found.${RST} Add manually: export PATH=\"$SCRIPTS_DIR:\$PATH\""
        export PATH="$SCRIPTS_DIR:$PATH"
        ;;
esac

# ---- Verify -------------------------------------------------------------
echo "[4/5] Verifying ftk install..."
$PY -m ftk --version

# ---- Detect project (cwd -> registry fallback) -------------------------
if [ ! -f "$PROJECT_DIR/ftk.yaml" ]; then
    echo -e "${YEL}[INFO]${RST}  No ftk.yaml here. Checking registry..."
    FALLBACK=$($PY -c "
from ftk.projects import get_last_project_id, find_project, list_projects
import os
ps = list_projects()
fb = ps[0] if ps else None
e = find_project(get_last_project_id() or '') or fb
print(e.root if e and os.path.isdir(e.root) and os.path.isfile(os.path.join(e.root,'ftk.yaml')) else '')
" 2>/dev/null || echo "")
    [ -n "$FALLBACK" ] && PROJECT_DIR="$FALLBACK" && echo -e "      ${GRN}Found: $PROJECT_DIR${RST}"
fi

if [ ! -f "$PROJECT_DIR/ftk.yaml" ]; then
    echo ""
    echo -e "${YEL}=== Toolkit installed, no project autostart configured ===${RST}"
    echo ""
    echo "To enable autostart, cd into your Flutter project and re-run:"
    echo "  cd /path/to/my-flutter-app && bash $SCRIPT_DIR/install.sh"
    echo ""
    echo "Or register first, then re-run from anywhere:"
    echo "  ftk projects add /path/to/my-flutter-app"
    echo "  bash $SCRIPT_DIR/install.sh"
    echo ""
    echo "Manual start: ftk server"
    exit 0
fi

# =========================================================================
# Step 5 — install service
# =========================================================================
echo "[5/5] Installing background service for: $PROJECT_DIR"

$PY -m ftk projects add "$PROJECT_DIR" >/dev/null 2>&1 || true
PROJECT_ID="$($PY -c "from ftk.config import load_config; print(load_config(r'''$PROJECT_DIR''').id)" 2>/dev/null || echo "")"

FTK_BIN="$SCRIPTS_DIR/ftk"
if [ ! -x "$FTK_BIN" ]; then
    echo -e "${RED}[ERROR]${RST} ftk not found at $FTK_BIN"
    exit 1
fi

# Remove quarantine flag — prevents "undefined developer" warning on macOS
if [ "$OS_KIND" = "macos" ] && command -v xattr >/dev/null 2>&1; then
    xattr -dr com.apple.quarantine "$FTK_BIN" 2>/dev/null || true
fi

LOG_DIR="$PROJECT_DIR/.ftk"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/server.log"

# ---- Detect system language ---------------------------------------------
if [ -n "${LANG:-}" ]; then
    LAUNCH_LANG="$LANG"
elif [ "$OS_KIND" = "macos" ] && command -v defaults >/dev/null 2>&1; then
    SYS_LANG=$(defaults read NSGlobalDomain AppleLanguages 2>/dev/null \
        | grep -o '"[a-z][a-z]' | head -1 | tr -d '"' || echo "en")
    case "$SYS_LANG" in
        hu) LAUNCH_LANG="hu_HU.UTF-8";;
        ro) LAUNCH_LANG="ro_RO.UTF-8";;
        de) LAUNCH_LANG="de_DE.UTF-8";;
        fr) LAUNCH_LANG="fr_FR.UTF-8";;
        es) LAUNCH_LANG="es_ES.UTF-8";;
        it) LAUNCH_LANG="it_IT.UTF-8";;
        pt) LAUNCH_LANG="pt_PT.UTF-8";;
        nl) LAUNCH_LANG="nl_NL.UTF-8";;
        pl) LAUNCH_LANG="pl_PL.UTF-8";;
        ru) LAUNCH_LANG="ru_RU.UTF-8";;
        cs) LAUNCH_LANG="cs_CZ.UTF-8";;
        sk) LAUNCH_LANG="sk_SK.UTF-8";;
        sv) LAUNCH_LANG="sv_SE.UTF-8";;
        da) LAUNCH_LANG="da_DK.UTF-8";;
        fi) LAUNCH_LANG="fi_FI.UTF-8";;
        nb|no) LAUNCH_LANG="nb_NO.UTF-8";;
        tr) LAUNCH_LANG="tr_TR.UTF-8";;
        ja) LAUNCH_LANG="ja_JP.UTF-8";;
        ko) LAUNCH_LANG="ko_KR.UTF-8";;
        zh) LAUNCH_LANG="zh_CN.UTF-8";;
        ar) LAUNCH_LANG="ar_SA.UTF-8";;
        *)  LAUNCH_LANG="en_US.UTF-8";;
    esac
else
    LAUNCH_LANG="en_US.UTF-8"
fi

LAUNCH_PATH="$PATH"
LAUNCH_HOME="$HOME"

# =========================================================================
# macOS — LaunchAgent
# =========================================================================
case "$OS_KIND" in
macos)
    mkdir -p "$HOME/Library/LaunchAgents"

    # Build ProgramArguments XML tags
    PA_TAGS="        <string>$FTK_BIN</string>"
    if [ -n "$PROJECT_ID" ]; then
        PA_TAGS="$PA_TAGS
        <string>--project</string>
        <string>$PROJECT_ID</string>"
    fi
    PA_TAGS="$PA_TAGS
        <string>server</string>"

    # Unload existing agent before rewriting the plist
    if [ -f "$PLIST_PATH" ]; then
        _launchctl_unload "$PLIST_PATH" "$PLIST_LABEL"
        sleep 1
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
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key><false/>
        <key>Crashed</key><true/>
    </dict>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>ProcessType</key><string>Background</string>
    <key>StandardOutPath</key><string>$LOG_FILE</string>
    <key>StandardErrorPath</key><string>$LOG_FILE</string>
</dict>
</plist>
EOF

    _launchctl_load "$PLIST_PATH" "$PLIST_LABEL"
    echo "      LaunchAgent : $PLIST_PATH"
    ;;

# =========================================================================
# Linux — systemd user unit
# =========================================================================
linux)
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"

    SERVE_ARGS="server"
    [ -n "$PROJECT_ID" ] && SERVE_ARGS="--project $PROJECT_ID server"

    cat > "$SYSTEMD_UNIT" <<EOF
[Unit]
Description=flutter-toolkit web UI
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PATH"
Environment="LANG=$LAUNCH_LANG"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$FTK_BIN $SERVE_ARGS
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now flutter-toolkit.service
    echo "      systemd unit : $SYSTEMD_UNIT"
    ;;

*)
    echo -e "${YEL}[WARN]${RST} OS '$OS' not supported for service install."
    [ -n "$PROJECT_ID" ] && echo "      Manual start: $FTK_BIN --project $PROJECT_ID server" \
                         || echo "      Manual start: $FTK_BIN server"
    exit 0
    ;;
esac

# ---- Wait for server ----------------------------------------------------
UP=1
for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    curl -sf http://127.0.0.1:8742/api/health >/dev/null 2>&1 && UP=0 && break
done

echo ""
if [ "$UP" = "0" ]; then
    echo -e "${GRN}=== Done - server is running ===${RST}"
    echo "URL       : http://127.0.0.1:8742"
    echo "Restart   : bash $SCRIPT_DIR/reset.sh"
    echo "Uninstall : bash $SCRIPT_DIR/uninstall.sh"
    [ "$OS_KIND" = "macos" ] && open http://127.0.0.1:8742 2>/dev/null || true
    [ "$OS_KIND" = "linux" ] && xdg-open http://127.0.0.1:8742 2>/dev/null || true
else
    echo -e "${YEL}=== Done - service installed, give it a few seconds ===${RST}"
    echo "URL  : http://127.0.0.1:8742"
    echo "Logs : $LOG_FILE"
fi
echo ""
