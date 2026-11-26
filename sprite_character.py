"""Sprite-based character using Shijima-Qt / Shimeji mascot packs.

Loads PNG sprite sheets from a mascot directory and maps them to
both Claude states (idle, thinking, working, ...) and movement
states (walk, sit, climb, fall, ceiling).

Movement animations play when Claude state is "idle".
Claude state animations override movement when active.

Conforms to the Character protocol expected by PetWindow.
"""

from __future__ import annotations

import json
import math
import os
import re

import cairo

SPRITE_FILE = re.compile(r"shime(\d+)\.png")
EXTRA_ANIMATIONS_FILE = "animations.json"


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
        self.gaze: tuple[int, int] = (0, 0)

        # Load all sprites
        self._sprites: dict[int, cairo.ImageSurface] = {}
        # Support both flat dir and mascot/img/ layout
        img_dir = os.path.join(mascot_path, "img")
        if not os.path.isdir(img_dir):
            img_dir = mascot_path
        for name in os.listdir(img_dir):
            match = SPRITE_FILE.fullmatch(name)
            path = os.path.join(img_dir, name)
            if match:
                # Skip blank/transparent sprites (fully transparent PNGs are tiny)
                if os.path.getsize(path) < 500:
                    continue
                self._sprites[int(match.group(1))] = cairo.ImageSurface.create_from_png(path)

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
                "sprites": [51, 51, 52, 53, 52, 53, 51, 51],
                "delay": 110,
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
            "stumble": {
                "sprites": [19, 18, 20],
                "delay": 300,
                "loop": False,
                "loops": 1,
                "next": "idle",
            },
            "attack": {
                "sprites": [27, 28, 29],
                "delay": 200,
                "loop": False,
                "loops": 1,
                "next": "celebrating",
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
                "sprites": [18],
                "delay": 500,
            },
            "good_land": {
                "sprites": [1],
                "delay": 500,
            },
            "hard_land": {
                "sprites": [18, 20, 20, 21, 21],
                "delay": 250,
            },
        }

        self._right_facing: dict[int, int] = {}
        self._looks: dict[int, dict] = {}
        self._heads: dict[int, list] = {}
        self._hats: dict[str, tuple[cairo.ImageSurface, tuple[int, int], int]] = {}
        self._fronts: dict[int, cairo.ImageSurface] = {}
        self._headroom: dict[tuple[str, int], int] = {}
        self.hat: str | None = None
        self._load_extra_animations(mascot_path)

        # Replace missing sprite indices with fallback (first available sprite)
        if self._sprites:
            fallback = min(self._sprites.keys())
            for configs in (self._state_config, self._move_config):
                for cfg in configs.values():
                    cfg["sprites"] = [
                        s if s in self._sprites else fallback
                        for s in cfg["sprites"]
                    ]

    def _load_extra_animations(self, mascot_path: str) -> None:
        path = os.path.join(mascot_path, EXTRA_ANIMATIONS_FILE)
        if not os.path.isfile(path):
            return
        with open(path) as f:
            extras = json.load(f)
        self._state_config.update(extras.get("states", {}))
        self._move_config.update(extras.get("moves", {}))
        self._right_facing = {int(index): twin for index, twin in extras.get("right_facing", {}).items()}
        self._looks = {int(pose): look for pose, look in extras.get("looks", {}).items()}
        self._heads = {int(index): anchor for index, anchor in extras.get("heads", {}).items()}
        self._fronts = {int(index): cairo.ImageSurface.create_from_png(os.path.join(mascot_path, path))
                        for index, path in extras.get("fronts", {}).items()
                        if os.path.isfile(os.path.join(mascot_path, path))}
        for name, origin in extras.get("hats", {}).items():
            path = os.path.join(mascot_path, "hats", f"{name}.png")
            if os.path.isfile(path):
                image = cairo.ImageSurface.create_from_png(path)
                self._hats[name] = (image, (origin[0], origin[1]), _top_of(image))

    @property
    def hats(self) -> list[str]:
        return sorted(self._hats)

    def set_hat(self, name: str | None) -> None:
        self.hat = name if name in self._hats else None

    def supports(self, animation: str) -> bool:
        return animation in self._state_config or animation in self._move_config

    def max_overhang(self, animation: str) -> int:
        cfg = self._state_config.get(animation) or self._move_config.get(animation)
        surfaces = [self._sprites[index] for index in cfg["sprites"] if index in self._sprites] if cfg else []
        return max((s.get_height() - s.get_width() for s in surfaces), default=0)

    def animation_ms(self, state: str) -> int:
        cfg = self._state_config[state]
        return sum(cfg["durations"]) if "durations" in cfg else cfg["delay"] * len(cfg["sprites"])

    def _frame_ms(self, cfg: dict) -> int:
        durations = cfg.get("durations")
        return durations[self.frame % len(durations)] if durations else cfg["delay"]

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        if state != self.state and state in self._state_config:
            self.state = state
            self.frame = 0
            self._tick_accum = 0
            self._loops_done = 0

    def set_gaze(self, dx: int, dy: int) -> None:
        self.gaze = (dx, dy)

    def eyes_at(self) -> tuple[float, float] | None:
        look = self._looks.get(self._pose())
        if look is None:
            return None
        x, y = look["eyes"]
        return (self._sprites[self._pose()].get_width() - x if self.facing > 0 else x), y

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

        while self._tick_accum >= self._frame_ms(cfg):
            self._tick_accum -= self._frame_ms(cfg)
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
        return self._frame_ms(self._active_config())

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _pose(self) -> int:
        sprites = self._active_config()["sprites"]
        return sprites[self.frame % len(sprites)]

    def shown_index(self) -> int:
        idx = self._pose()
        look = self._looks.get(idx)
        if look is not None and self.gaze != (0, 0):
            dx, dy = self.gaze
            idx = look["sprites"][(dy + 1) * 3 + (dx * -self.facing) + 1]
        if self.facing > 0:
            idx = self._right_facing.get(idx, idx)
        return idx

    def headroom(self, idx: int) -> int:
        anchor = self._heads.get(idx) if self.hat else None
        if anchor is None:
            return 0
        key = (self.hat, idx)
        if key not in self._headroom:
            image, (ox, oy), top = self._hats[self.hat]
            x, y, angle, flip = anchor
            a = math.radians(angle)
            corners = [((ox - cx) if flip else (cx - ox), cy - oy)
                       for cx in (0, image.get_width()) for cy in (top, image.get_height())]
            highest = min(y + cx * math.sin(a) + cy * math.cos(a) for cx, cy in corners)
            self._headroom[key] = max(0, math.ceil(-highest))
        return self._headroom[key]

    def overhang(self) -> int:
        idx = self.shown_index()
        surface = self._sprites.get(idx)
        return surface.get_height() - surface.get_width() + self.headroom(idx) if surface else 0

    def draw(self, ctx: cairo.Context, width: int, height: int) -> None:
        self.draw_sprite(ctx, self.shown_index(), self.facing, width, height)

    def draw_sprite(self, ctx: cairo.Context, idx: int, facing: int, width: int, height: int) -> None:
        surface = self._sprites.get(idx)
        if surface is None:
            return

        ctx.save()

        # Scale to the window width; frames taller than wide stand on the bottom edge
        scale = width / surface.get_width()
        ctx.translate(0, height - surface.get_height() * scale)

        # Flip horizontally when facing right (sprites face left by default)
        if facing > 0:
            ctx.translate(width, 0)
            ctx.scale(-scale, scale)
        else:
            ctx.scale(scale, scale)

        ctx.set_source_surface(surface, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_NEAREST)
        ctx.paint()
        if self.hat:
            self._paint_hat(ctx, idx)
            self._paint_front(ctx, idx)
        ctx.restore()

    def _paint_front(self, ctx: cairo.Context, idx: int) -> None:
        front = self._fronts.get(idx)
        if front is not None:
            ctx.set_source_surface(front, 0, 0)
            ctx.get_source().set_filter(cairo.FILTER_NEAREST)
            ctx.paint()

    def _paint_hat(self, ctx: cairo.Context, idx: int) -> None:
        anchor = self._heads.get(idx)
        if anchor is None:
            return
        image, (ox, oy), _ = self._hats[self.hat]
        x, y, angle, flip = anchor
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(math.radians(angle))
        if flip:
            ctx.scale(-1, 1)
        ctx.set_source_surface(image, -ox, -oy)
        ctx.get_source().set_filter(cairo.FILTER_GOOD if angle else cairo.FILTER_NEAREST)
        ctx.paint()
        ctx.restore()


def _top_of(image: cairo.ImageSurface) -> int:
    image.flush()
    data, stride = image.get_data(), image.get_stride()
    for y in range(image.get_height()):
        if any(data[y * stride + x * 4 + 3] for x in range(image.get_width())):
            return y
    return 0
