#!/bin/bash
# Claude Pet state hook
# Usage: state-hook.sh <state>
# Called by Claude Code hooks to update pet state.
# Reads JSON from stdin to extract cwd for per-project instance support.
#
# Auto-starts a per-project pet if not already running (uses PID file).
# Valid states: idle, thinking, working, attention, celebrating, doubling

PET_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ -z "$1" ]; then
    echo "Usage: state-hook.sh <state>" >&2
    exit 1
fi

# Read stdin JSON and extract cwd for per-project identification
PROJECT_INFO=$(python3 -c "
import json, hashlib, os, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
cwd = data.get('cwd', '')
if cwd:
    name = os.path.basename(cwd)
    h = hashlib.md5(cwd.encode()).hexdigest()[:8]
    print(f'{name}\n{h}')
else:
    print('\n')
" 2>/dev/null)

PROJECT_NAME=$(echo "$PROJECT_INFO" | head -1)
PROJECT_HASH=$(echo "$PROJECT_INFO" | tail -1)

if [ -n "$PROJECT_HASH" ]; then
    STATE_FILE="/tmp/claude-pet-${PROJECT_HASH}-state"
    PID_FILE="/tmp/claude-pet-${PROJECT_HASH}.pid"
else
    STATE_FILE="/tmp/claude-pet-state"
    PID_FILE="/tmp/claude-pet.pid"
fi

# Handle "stop" — kill the pet for this project and clean up
if [ "$1" = "stop" ]; then
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null
        fi
        rm -f "$PID_FILE"
    fi
    rm -f "$STATE_FILE"
    exit 0
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
    EXTRA_ARGS="--state-file $STATE_FILE --pid-file $PID_FILE"
    if [ -n "$PROJECT_NAME" ]; then
        EXTRA_ARGS="$EXTRA_ARGS --project-name $PROJECT_NAME"
    fi
    nohup python3 "$PET_DIR/main.py" $EXTRA_ARGS &>/dev/null &
    disown
    sleep 0.5  # give main.py time to write its own PID file
fi

echo "$1" > "$STATE_FILE"
