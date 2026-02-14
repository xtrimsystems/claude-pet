#!/bin/bash
# Claude Pet Installer
#
# Checks dependencies, sets permissions, installs Claude Code hooks,
# and prints i3 configuration hints.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Claude Pet Installer ==="
echo ""

# 1. Check dependencies
echo "[1/4] Checking dependencies..."
python3 -c "import gi; gi.require_version('Gtk', '3.0')" 2>/dev/null || {
    echo "ERROR: python3-gi (PyGObject) is not installed."
    echo "Install with: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"
    exit 1
}
python3 -c "import cairo" 2>/dev/null || {
    echo "ERROR: python3-cairo is not installed."
    echo "Install with: sudo apt install python3-gi-cairo"
    exit 1
}
echo "  All dependencies found"

# 2. Make scripts executable
echo "[2/4] Setting permissions..."
chmod +x "$SCRIPT_DIR/main.py" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/hooks/state-hook.sh"
chmod +x "$SCRIPT_DIR/hooks/install-hooks.sh"
chmod +x "$SCRIPT_DIR/hooks/uninstall-hooks.sh"
echo "  Permissions set"

# 3. Install Claude Code hooks
echo "[3/4] Installing Claude Code hooks..."
bash "$SCRIPT_DIR/hooks/install-hooks.sh"

# 4. Print i3 config suggestion
echo "[4/4] i3 window manager configuration"
echo ""
echo "  Add this to your i3 config (~/.config/i3/config or ~/.config/regolith3/i3/config.d/):"
echo ""
echo '  # Claude Pet - floating desktop companion'
echo '  for_window [class="Claude-pet"] floating enable, border none, sticky enable'
echo '  for_window [title="Claude Pet"] floating enable, border none, sticky enable'
echo ""

# 5. Create launcher script
echo "Creating launcher..."
cat > "$SCRIPT_DIR/claude-pet" << 'LAUNCHER'
#!/bin/bash
cd "$(dirname "$0")"
exec python3 main.py "$@"
LAUNCHER
chmod +x "$SCRIPT_DIR/claude-pet"
echo "  Launcher created: $SCRIPT_DIR/claude-pet"

echo ""
echo "=== Installation complete! ==="
echo ""
echo "To run:  $SCRIPT_DIR/claude-pet"
echo "         or: make run (from $SCRIPT_DIR)"
echo ""
echo "To auto-start with Claude Code, add to your shell rc:"
echo "  # Start Claude Pet in background"
echo "  claude-pet() { nohup $SCRIPT_DIR/claude-pet &>/dev/null & }"
echo ""
