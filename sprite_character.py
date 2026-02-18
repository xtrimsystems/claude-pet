"""Sprite-based character using Shijima-Qt / Shimeji mascot packs.

Loads PNG sprite sheets from a mascot directory and maps them to
both Claude states (idle, thinking, working, ...) and movement
states (walk, sit, climb, fall, ceiling).

Movement animations play when Claude state is "idle".
Claude state animations override movement when active.

Conforms to the Character protocol expected by PetWindow.
"""

from __future__ import annotations

import os

import cairo


class SpriteCharacter:
    """Character driven by Shimeji-style PNG sprites.

    Loads shime1.png .. shimeN.png from ``mascot_path/img/``.
    """

    _TICK_MS: int = 1000 // 60  # ~16ms, must match FRAME_INTERVAL_MS

    def __init__(self, mascot_path: str) -> None:
        self.state: str = "idle"
        self.frame: int = 0
        self.facing: int = -1      # -1 = left (default), 1 = right
        self.move_state: str = ""   # set by PetWindow: walk, sit, climb, fall, ceiling
        self._tick_accum: int = 0
        self._loops_done: int = 0

        # Load all sprites
        self._sprites: dict[int, cairo.ImageSurface] = {}
        # Support both flat dir and mascot/img/ layout
        img_dir = os.path.join(mascot_path, "img")
        if not os.path.isdir(img_dir):
            img_dir = mascot_path
        # Scan up to 200 to handle gaps in numbering
        for i in range(1, 200):
            path = os.path.join(img_dir, f"shime{i}.png")
            if os.path.exists(path):
                # Skip blank/transparent sprites (fully transparent PNGs are tiny)
                if os.path.getsize(path) < 500:
                    continue
                self._sprites[i] = cairo.ImageSurface.create_from_png(path)

        # State-override animations (triggered by Claude hooks or wander engine)
        # These freeze movement and take priority over move animations.
        # sprites: list of shime indices, delay: ms per frame
        self._state_config: dict[str, dict] = {
            "idle": {
                "sprites": [1],
                "delay": 500,
            },
            "thinking": {
                "sprites": [42, 43],
                "delay": 350,
            },
            "working": {
                "sprites": [47, 48, 48, 48, 47],
                "delay": 600,
            },
            "attention": {
                "sprites": [11, 15],
                "delay": 300,
            },
            "celebrating": {
                "sprites": [49, 50],
                "delay": 300,
                "loop": False,
                "next": "idle",
            },
            "error": {
                "sprites": [43, 43, 38, 39, 40, 41, 41, 11, 11, 11, 42],
                "delay": 250,
                "loop": False,
                "loops": 1,
                "next": "idle",
            },
            "doubling": {
                "sprites": [44, 45, 46],
                "delay": 400,
                "loop": False,
                "loops": 1,
                "next": "clone_frozen",
            },
            "clone_frozen": {
                "sprites": [43],
                "delay": 500,
            },
            "clone_dying": {
                "sprites": [19, 18, 20],
                "delay": 300,
                "loop": False,
                "loops": 1,
                "next": "idle",
            },
        }

        # Movement animations (used when Claude state is "idle")
        self._move_config: dict[str, dict] = {
            "walk": {
                "sprites": [1, 2, 1, 3],
                "delay": 120,
            },
            "sit": {
                "sprites": [11],
                "delay": 500,
            },
            "climb": {
                "sprites": [14, 12, 13],
                "delay": 200,
            },
            "ceiling": {
                "sprites": [25, 23, 24],
                "delay": 200,
            },
            "kick": {
                "sprites": [37],
                "delay": 150,
            },
            "jump_launch": {
                "sprites": [22],
                "delay": 150,
            },
            "fall": {
                "sprites": [4],
                "delay": 200,
            },
            "drag": {
                "sprites": [5],
                "delay": 200,
            },
            "drag_left_slow": {
                "sprites": [6],
                "delay": 200,
            },
            "drag_left_fast": {
                "sprites": [8],
                "delay": 200,
            },
            "drag_left_vfast": {
                "sprites": [10],
                "delay": 200,
            },
            "drag_right_slow": {
                "sprites": [7],
                "delay": 200,
            },
            "drag_right_fast": {
                "sprites": [9],
                "delay": 200,
            },
            "bad_land": {
                "sprites": [18, 19],
                "delay": 250,
            },
            "good_land": {
                "sprites": [1],
                "delay": 500,
            },
            "hard_land": {
                "sprites": [18, 20, 21, 21, 19],
                "delay": 200,
            },
        }

        # Replace missing sprite indices with fallback (first available sprite)
        if self._sprites:
            fallback = min(self._sprites.keys())
            for configs in (self._state_config, self._move_config):
                for cfg in configs.values():
                    cfg["sprites"] = [
                        s if s in self._sprites else fallback
                        for s in cfg["sprites"]
                    ]

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        if state != self.state and state in self._state_config:
            self.state = state
            self.frame = 0
            self._tick_accum = 0
            self._loops_done = 0

    def set_movement(self, move: str, facing: int) -> None:
        """Called by PetWindow each frame with wander state and direction."""
        self.move_state = move
        self.facing = facing

    @property
    def is_busy(self) -> bool:
        cfg = self._active_config()
        return not cfg.get("loop", True)

    def _active_config(self) -> dict:
        """Get the config for the currently playing animation."""
        if self.state != "idle":
            return self._state_config[self.state]
        if self.move_state in self._move_config:
            return self._move_config[self.move_state]
        return self._state_config["idle"]

    def tick(self) -> None:
        cfg = self._active_config()
        n_frames = len(cfg["sprites"])
        self._tick_accum += self._TICK_MS

        while self._tick_accum >= cfg["delay"]:
            self._tick_accum -= cfg["delay"]
            self.frame += 1

            if self.frame >= n_frames:
                if cfg.get("loop", True):
                    self.frame = 0
                else:
                    self._loops_done += 1
                    if self._loops_done < cfg.get("loops", 2):
                        self.frame = 0
                    else:
                        self.state = cfg.get("next", "idle")
                        self.frame = 0
                        self._tick_accum = 0
                        self._loops_done = 0
                        break

    def get_frame_delay(self) -> int:
        return self._active_config()["delay"]

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, ctx: cairo.Context, width: int, height: int) -> None:
        cfg = self._active_config()
        sprites = cfg["sprites"]
        idx = sprites[self.frame % len(sprites)]
        surface = self._sprites.get(idx)
        if surface is None:
            return

        sprite_w = surface.get_width()
        sprite_h = surface.get_height()

        ctx.save()

        # Scale sprite to fill the window
        sx = width / sprite_w
        sy = height / sprite_h

        # Flip horizontally when facing right (sprites face left by default)
        if self.facing > 0:
            ctx.translate(width, 0)
            ctx.scale(-sx, sy)
        else:
            ctx.scale(sx, sy)

        ctx.set_source_surface(surface, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_NEAREST)
        ctx.paint()
        ctx.restore()
