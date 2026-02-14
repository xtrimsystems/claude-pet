#!/bin/bash
# Uninstall Claude Pet hooks and cleanup

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Claude Pet Uninstaller ==="
echo ""

# Remove hooks from Claude Code settings
bash "$SCRIPT_DIR/hooks/uninstall-hooks.sh"

# Remove state file
rm -f /tmp/claude-pet-state
echo "  State file removed"

# Remove launcher if it exists
rm -f "$SCRIPT_DIR/claude-pet"
echo "  Launcher removed"

echo ""
echo "Manual steps:"
echo "  - Remove the i3 config rules for Claude Pet"
echo "  - Remove any shell aliases you created"
echo ""
echo "=== Done ==="
