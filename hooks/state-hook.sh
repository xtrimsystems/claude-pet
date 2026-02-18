#!/bin/bash
# Claude Pet state hook
# Usage: state-hook.sh <state>
# Called by Claude Code hooks to update pet state.
#
# Auto-starts the pet if not already running (uses PID file).
# Valid states: idle, thinking, working, attention, celebrating, doubling

STATE_FILE="/tmp/claude-pet-state"
PID_FILE="/tmp/claude-pet.pid"
PET_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$1" ]; then
    echo "Usage: state-hook.sh <state>" >&2
    exit 1
fi

# Auto-start pet if not running (PID file check)
need_start=true
if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        need_start=false
    fi
fi

if $need_start; then
    # Ensure DISPLAY is set for GTK (hooks may not inherit it)
    export DISPLAY="${DISPLAY:-:0}"
    nohup python3 "$PET_DIR/main.py" &>/dev/null &
    disown
    sleep 0.5  # give main.py time to write its own PID file
fi

echo "$1" > "$STATE_FILE"
