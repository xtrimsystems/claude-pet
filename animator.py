"""Animation state machine for Claude Pet.

Manages frame counting, state transitions, and timing for
the desktop pet's animation states.
"""

from dataclasses import dataclass


@dataclass
class StateConfig:
    """Configuration for a single animation state."""
    frame_count: int
    frame_delay_ms: int
    loop: bool
    next_state: str | None = None


# All available animation states and their configurations
STATE_CONFIGS: dict[str, StateConfig] = {
    "idle": StateConfig(frame_count=4, frame_delay_ms=400, loop=True),
    "thinking": StateConfig(frame_count=4, frame_delay_ms=350, loop=True),
    "working": StateConfig(frame_count=6, frame_delay_ms=150, loop=True),
    "attention": StateConfig(frame_count=6, frame_delay_ms=120, loop=True),
    "celebrating": StateConfig(frame_count=8, frame_delay_ms=200, loop=False, next_state="idle"),
    "error": StateConfig(frame_count=4, frame_delay_ms=300, loop=False, next_state="idle"),
}

DEFAULT_STATE = "idle"


class Animator:
    """Animation state machine that tracks current state and frame.

    Manages frame advancement with per-state timing. Looping states
    wrap their frame counter; non-looping states transition to their
    configured next_state when the animation completes.
    """

    def __init__(self) -> None:
        self._state: str = DEFAULT_STATE
        self._frame: int = 0
        self._elapsed_ms: float = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def frame(self) -> int:
        return self._frame

    @property
    def config(self) -> StateConfig:
        return STATE_CONFIGS[self._state]

    def set_state(self, state: str) -> None:
        """Change to a new animation state, resetting the frame counter.

        If the requested state is unknown, falls back to the default state.
        No-op if already in the requested state.
        """
        if state not in STATE_CONFIGS:
            state = DEFAULT_STATE
        if state == self._state:
            return
        self._state = state
        self._frame = 0
        self._elapsed_ms = 0.0

    def tick(self, delta_ms: float) -> tuple[str, int]:
        """Advance the animation by delta_ms milliseconds.

        Returns the current (state, frame) pair after advancement.
        Handles frame wrapping for looping states and automatic
        state transitions for non-looping states that have completed.
        """
        cfg = self.config
        self._elapsed_ms += delta_ms

        # Advance as many frames as the elapsed time allows
        while self._elapsed_ms >= cfg.frame_delay_ms:
            self._elapsed_ms -= cfg.frame_delay_ms
            self._frame += 1

            if self._frame >= cfg.frame_count:
                if cfg.loop:
                    self._frame = 0
                else:
                    # Non-looping animation finished: transition
                    next_state = cfg.next_state or DEFAULT_STATE
                    self._state = next_state
                    self._frame = 0
                    self._elapsed_ms = 0.0
                    cfg = self.config  # Update cfg for the new state
                    break

        return (self._state, self._frame)
