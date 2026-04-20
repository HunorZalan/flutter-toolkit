#!/usr/bin/env bash
# macOS double-click wrapper for install.sh.
#
# When double-clicked from Finder, cwd is / or $HOME - not useful.
# We do NOT cd to the script directory (that breaks project detection).
# Instead, we stay in $HOME and let install.sh's registry fallback
# find the registered project automatically.
#
# If the user hasn't registered a project yet, install.sh will print
# instructions on how to do it.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Run install.sh from $HOME (not the scripts dir).
# The registry fallback in install.sh will locate the project.
cd "$HOME"
bash "$SCRIPT_DIR/install.sh"

echo ""
echo "Press any key to close..."
read -n 1 -s
