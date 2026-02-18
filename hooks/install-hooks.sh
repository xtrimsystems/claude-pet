#!/bin/bash
# Install Claude Pet hooks into Claude Code settings.
#
# Adds hook entries to ~/.claude/settings.json so Claude Code
# calls state-hook.sh on session, prompt, permission, stop, and compact events.
#
# Safe to run multiple times — existing hooks are preserved and
# claude-pet hooks are only added if not already present.

set -e

SETTINGS_FILE="$HOME/.claude/settings.json"
SETTINGS_DIR="$HOME/.claude"
HOOK_SCRIPT="$(cd "$(dirname "$0")" && pwd)/state-hook.sh"

echo "  Installing Claude Code hooks..."

# Make sure the .claude directory exists
mkdir -p "$SETTINGS_DIR"

# Use python3 for reliable JSON manipulation
python3 << PYEOF
import json
import os
import shutil
import sys
from pathlib import Path

settings_file = Path(os.path.expanduser("~/.claude/settings.json"))
hook_script = Path("$HOOK_SCRIPT")

# The hooks we want to install (new format with "hooks" array and "type": "command")
pet_hooks = {
    "SessionStart": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{hook_script} idle",
                    "timeout": 5
                }
            ]
        }
    ],
    "UserPromptSubmit": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{hook_script} thinking",
                    "timeout": 5
                }
            ]
        }
    ],
    "PreToolUse": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{hook_script} working",
                    "timeout": 5
                }
            ]
        }
    ],
    "PermissionRequest": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{hook_script} attention",
                    "timeout": 5
                }
            ]
        }
    ],
    "Stop": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{hook_script} celebrating",
                    "timeout": 5
                }
            ]
        }
    ],
    "PreCompact": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{hook_script} doubling",
                    "timeout": 5
                }
            ]
        }
    ],
    "SessionEnd": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{hook_script} stop",
                    "timeout": 5
                }
            ]
        }
    ],
}

# Load existing settings or start fresh
settings = {}
if settings_file.exists():
    try:
        with open(settings_file, "r") as f:
            settings = json.load(f)
        if not isinstance(settings, dict):
            print(f"  WARNING: {settings_file} is not a JSON object, backing up and recreating")
            settings = {}
    except json.JSONDecodeError:
        print(f"  WARNING: {settings_file} has invalid JSON, backing up and recreating")
        settings = {}

    # Back up the existing file
    backup_path = settings_file.with_suffix(".json.bak")
    shutil.copy2(settings_file, backup_path)
    print(f"  Backed up existing settings to {backup_path}")

# Ensure the hooks key exists
if "hooks" not in settings:
    settings["hooks"] = {}

hooks = settings["hooks"]

def is_pet_hook(entry: dict) -> bool:
    """Check if a hook entry belongs to claude-pet."""
    for h in entry.get("hooks", []):
        cmd = h.get("command", "")
        if "claude-pet" in cmd and "state-hook.sh" in cmd:
            return True
    return False

for event_name, new_entries in pet_hooks.items():
    if event_name not in hooks:
        hooks[event_name] = []

    existing = hooks[event_name]

    # Remove any old claude-pet hooks for this event (in case paths changed)
    existing = [e for e in existing if not is_pet_hook(e)]

    # Append the new ones
    existing.extend(new_entries)
    hooks[event_name] = existing

settings["hooks"] = hooks

# Write it back
with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

print(f"  Hooks written to {settings_file}")
print("  Installed hooks for: " + ", ".join(pet_hooks.keys()))
PYEOF

echo "  Done installing hooks."
