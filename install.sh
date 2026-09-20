#!/bin/bash
# Claude Pet Installer
#
# Checks dependencies, sets permissions and installs the Claude Code hooks.
# Usage: install.sh [claude-config-dir ...]   (default: ~/.claude)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Claude Pet Installer ==="
echo ""

echo "[1/3] Checking dependencies..."
python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Gtk4LayerShell', '1.0')" 2>/dev/null || {
    echo "ERROR: GTK4 + gtk4-layer-shell Python bindings not found."
    echo "Install with: sudo pacman -S python-gobject gtk4 gtk4-layer-shell"
    exit 1
}
python3 -c "import cairo" 2>/dev/null || {
    echo "ERROR: python-cairo is not installed."
    echo "Install with: sudo pacman -S python-cairo"
    exit 1
}
[ -n "$WAYLAND_DISPLAY" ] || echo "WARNING: WAYLAND_DISPLAY is not set — the pet needs a Wayland compositor with wlr-layer-shell (Hyprland, sway, ...)"
echo "  All dependencies found"

echo "[2/3] Setting permissions..."
chmod +x "$SCRIPT_DIR/main.py" "$SCRIPT_DIR/hooks/"*.sh
echo "  Permissions set"

echo "[3/3] Installing Claude Code hooks..."
bash "$SCRIPT_DIR/hooks/install-hooks.sh" "$@"

echo ""
echo "=== Installation complete! ==="
echo ""
echo "The pet starts automatically with your next Claude Code session."
echo "Run it by hand:  make run   (from $SCRIPT_DIR)"
