#!/bin/bash
# Claude Pet state hook
# Usage: state-hook.sh <state>
# Called by Claude Code hooks to update the pet's state.
# Reads the hook JSON from stdin to track which sessions are alive.
#
# One pet for the whole desktop: the first session starts it, every session
# feeds it states, and it is only stopped when the last session ends.
# Valid states: idle, thinking, working, attention, celebrating, doubling, stop

PET_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="/tmp/claude-pet-state"
PID_FILE="/tmp/claude-pet.pid"
SESSIONS_DIR="/tmp/claude-pet-sessions"

if [ -z "$1" ]; then
    echo "Usage: state-hook.sh <state>" >&2
    exit 1
fi

SESSION_ID=$(python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('session_id', ''))
except Exception:
    print('')
" 2>/dev/null)
SESSION_ID=${SESSION_ID//[^A-Za-z0-9_-]/}

mkdir -p "$SESSIONS_DIR"

pet_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null
}

start_pet() {
    nohup python3 "$PET_DIR/main.py" &>/dev/null &
    disown
    sleep 0.5  # give main.py time to write its PID file
}

stop_pet() {
    if [ -f "$PID_FILE" ]; then
        kill "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null
        rm -f "$PID_FILE"
    fi
    rm -f "$STATE_FILE"
}

if [ "$1" = "stop" ]; then
    [ -n "$SESSION_ID" ] && rm -f "$SESSIONS_DIR/$SESSION_ID"
    # Sessions killed without a SessionEnd would keep the pet alive forever,
    # so also stop when no claude process is left at all.
    if [ -z "$(ls -A "$SESSIONS_DIR" 2>/dev/null)" ] || ! pgrep -x claude >/dev/null; then
        rm -f "$SESSIONS_DIR"/*
        stop_pet
    fi
    exit 0
fi

[ -n "$SESSION_ID" ] && touch "$SESSIONS_DIR/$SESSION_ID"
pet_running || start_pet
echo "$1" > "$STATE_FILE"
