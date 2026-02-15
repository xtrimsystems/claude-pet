"""
Claude Bridge - Monitors Claude Code state via a shared state file.

Claude Code hooks write state strings (e.g., "working", "thinking") to a file,
and the pet app polls that file to drive animations.

Valid states: "idle", "thinking", "working", "attention", "celebrating", "error"
"""

import os
import time

VALID_STATES = {"idle", "thinking", "working", "attention", "celebrating", "error", "doubling"}
DEFAULT_STATE = "idle"
POLL_INTERVAL_MS = 300
IDLE_TIMEOUT_S = 30


class ClaudeBridge:
    def __init__(self, state_file: str = "/tmp/claude-pet-state"):
        self.state_file = state_file
        self.current_state = DEFAULT_STATE
        self._callback = None
        self._watching = False
        self._last_mtime = 0.0
        self._timeout_id = None
        self._idle_timeout_id = None

    def get_state(self) -> str:
        """Read current state from file. Returns 'idle' if file doesn't exist
        or contains invalid data."""
        try:
            if not os.path.exists(self.state_file):
                return DEFAULT_STATE

            with open(self.state_file, "r") as f:
                raw = f.read().strip()

            if not raw:
                return DEFAULT_STATE

            # Only accept known states
            state = raw.lower()
            if state in VALID_STATES:
                return state

            return DEFAULT_STATE

        except (OSError, PermissionError, IOError):
            # File disappeared, permissions changed, etc. — just go idle.
            return DEFAULT_STATE

    def start_watching(self, callback) -> None:
        """Start polling the state file every 300ms.

        Calls callback(new_state) when the state changes.
        Uses GLib.timeout_add for GTK main-loop compatibility.

        Also starts an idle timeout: if no state change happens within 30
        seconds, automatically transition to 'idle'.
        """
        from gi.repository import GLib

        if self._watching:
            self.stop_watching()

        self._callback = callback
        self._watching = True

        # Read initial state so we don't fire a spurious callback on first poll
        self.current_state = self.get_state()
        try:
            self._last_mtime = os.path.getmtime(self.state_file)
        except OSError:
            self._last_mtime = 0.0

        # Start the poll timer
        self._timeout_id = GLib.timeout_add(POLL_INTERVAL_MS, self._check_state)

        # Start the idle-timeout timer
        self._idle_timeout_id = GLib.timeout_add_seconds(
            IDLE_TIMEOUT_S, self._idle_timeout
        )

    def stop_watching(self) -> None:
        """Stop polling and cancel all timers."""
        from gi.repository import GLib

        self._watching = False
        self._callback = None

        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

        if self._idle_timeout_id is not None:
            GLib.source_remove(self._idle_timeout_id)
            self._idle_timeout_id = None

    def _check_state(self) -> bool:
        """Poll callback.  Read the file, compare with current state,
        fire the callback if the state changed.

        Returns True to keep the GLib timeout active.
        """
        if not self._watching:
            return False  # stop the timer

        # Quick-check: skip the read if mtime hasn't changed
        try:
            mtime = os.path.getmtime(self.state_file)
        except OSError:
            mtime = 0.0

        if mtime == self._last_mtime:
            return True  # no change, keep polling

        self._last_mtime = mtime
        new_state = self.get_state()

        # Always notify on file change (mtime changed = someone wrote to it).
        # The character's set_state() handles dedup if already in that state.
        # This lets re-writing the same state (e.g. "celebrating" twice)
        # properly re-trigger animations.
        self.current_state = new_state

        # Reset the idle timeout whenever the file is touched
        self._reset_idle_timeout()

        if self._callback is not None:
            try:
                self._callback(new_state)
            except Exception:
                # Don't let a bad callback kill the poll loop
                pass

        return True  # keep polling

    def _reset_idle_timeout(self) -> None:
        """Cancel and restart the idle timeout timer."""
        from gi.repository import GLib

        if self._idle_timeout_id is not None:
            GLib.source_remove(self._idle_timeout_id)

        self._idle_timeout_id = GLib.timeout_add_seconds(
            IDLE_TIMEOUT_S, self._idle_timeout
        )

    def _idle_timeout(self) -> bool:
        """Fired when no state change has occurred for IDLE_TIMEOUT_S seconds.
        Transitions to 'idle' and notifies the callback.

        Returns False so GLib does NOT reschedule this timer automatically;
        _reset_idle_timeout will create a fresh one on the next state change.
        """
        if not self._watching:
            return False

        if self.current_state != DEFAULT_STATE:
            self.current_state = DEFAULT_STATE
            if self._callback is not None:
                try:
                    self._callback(DEFAULT_STATE)
                except Exception:
                    pass

        # Clear our own ID since we're not rescheduling
        self._idle_timeout_id = None
        return False

    def write_state(self, state: str) -> None:
        """Write a state to the file.  Useful for testing and internal use."""
        state = state.strip().lower()
        if state not in VALID_STATES:
            raise ValueError(
                f"Invalid state '{state}'. Must be one of: {', '.join(sorted(VALID_STATES))}"
            )

        try:
            with open(self.state_file, "w") as f:
                f.write(state + "\n")
        except (OSError, PermissionError, IOError) as exc:
            raise RuntimeError(
                f"Could not write to state file '{self.state_file}': {exc}"
            ) from exc
