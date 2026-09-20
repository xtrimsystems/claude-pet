#!/bin/bash
# Uninstall Claude Pet hooks and cleanup
# Usage: uninstall.sh [claude-config-dir ...]   (default: ~/.claude)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Claude Pet Uninstaller ==="
echo ""

bash "$SCRIPT_DIR/hooks/uninstall-hooks.sh" "$@"

make -s -C "$SCRIPT_DIR" stop
rm -f "$SCRIPT_DIR/claude-pet"

echo ""
echo "=== Done ==="
