#!/bin/bash
# Uninstall Claude Pet hooks from Claude Code settings.
#
# Removes only the claude-pet hook entries from
# ~/.claude/settings.local.json, leaving everything else untouched.

set -e

SETTINGS_FILE="$HOME/.claude/settings.local.json"

echo "  Removing Claude Code hooks..."

if [ ! -f "$SETTINGS_FILE" ]; then
    echo "  No settings file found at $SETTINGS_FILE — nothing to do."
    exit 0
fi

python3 << 'PYEOF'
import json
import os
import shutil
from pathlib import Path

settings_file = Path(os.path.expanduser("~/.claude/settings.local.json"))

if not settings_file.exists():
    print("  No settings file found — nothing to do.")
    exit(0)

try:
    with open(settings_file, "r") as f:
        settings = json.load(f)
except (json.JSONDecodeError, OSError) as exc:
    print(f"  ERROR: Could not read {settings_file}: {exc}")
    exit(1)

if not isinstance(settings, dict) or "hooks" not in settings:
    print("  No hooks found in settings — nothing to do.")
    exit(0)

# Back up before modifying
backup_path = settings_file.with_suffix(".json.bak")
shutil.copy2(settings_file, backup_path)
print(f"  Backed up settings to {backup_path}")

hooks = settings["hooks"]
removed_count = 0

def is_pet_hook(entry: dict) -> bool:
    """Check if a hook entry belongs to claude-pet."""
    cmd = entry.get("command", "")
    return "claude-pet" in cmd and "state-hook.sh" in cmd

for event_name in list(hooks.keys()):
    if not isinstance(hooks[event_name], list):
        continue

    original_len = len(hooks[event_name])
    hooks[event_name] = [e for e in hooks[event_name] if not is_pet_hook(e)]
    removed_count += original_len - len(hooks[event_name])

    # Clean up empty arrays
    if not hooks[event_name]:
        del hooks[event_name]

# Clean up empty hooks object
if not hooks:
    del settings["hooks"]

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

if removed_count > 0:
    print(f"  Removed {removed_count} claude-pet hook(s) from {settings_file}")
else:
    print("  No claude-pet hooks found — nothing removed.")
PYEOF

echo "  Done."
