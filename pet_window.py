"""Wayland layer-shell overlay for the Claude Pet desktop companion.

One transparent, click-through surface per monitor on the `overlay` layer
(wlr-layer-shell via gtk4-layer-shell). The sprite is a small widget moved
inside a Gtk.Fixed, so the compositor only re-renders the sprite, and the
surface's input region is limited to the sprite so everything else clicks
through. Wanders across the screen like a Shimeji desktop pet with climbing,
falling, and edge awareness. Supports multi-monitor.
"""

from __future__ import annotations

import enum
import logging
import os
import random
import time
from typing import Protocol

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Gtk4LayerShell as LayerShell  # noqa: E402

logger = logging.getLogger(__name__)


class CharacterProto(Protocol):
    state: str
    frame: int
    move_state: str
    facing: int
    is_busy: bool
    _sprites: dict
    _state_config: dict
    def draw(self, ctx: cairo.Context, width: int, height: int) -> None: ...
    def tick(self) -> None: ...
    def set_state(self, state: str) -> None: ...
    def set_movement(self, move: str, facing: int) -> None: ...
    def supports(self, animation: str) -> bool: ...
    def animation_ms(self, state: str) -> int: ...


class ClaudeBridgeProto(Protocol):
    def get_state(self) -> str: ...
    def start_watching(self, callback: object) -> None: ...
    def stop_watching(self) -> None: ...


FRAME_INTERVAL_MS = 1000 // 60
TEST_STATES = ("idle", "thinking", "working", "attention", "celebrating")
SPRITE_BASE = 128  # Shimeji sprites are 128x128
SCALE_OPTIONS = (0.5, 1.0, 1.5, 2.0)
NAP_AFTER_IDLE_S = 300
NAP_LENGTH_S = (60, 180)
ONGOING_CLAUDE_STATES = ("thinking", "working", "attention")
NAP_STATES = ("nap_start", "napping", "nap_wake")
DOZE_AFTER_WORKING_S = 90
DOZE_MEAN_WAIT_S = 120
DOZE_COOLDOWN_S = 300
TRICKS = (("Finger gun", "finger_gun"), ("The fly", "fly_gag"), ("Vibing", "vibing"),
          ("Head pop", "head_pop"), ("Nap", "nap_start"), ("Dozing at the laptop", "laptop_doze"))

TRANSPARENT_CSS = b"window.claude-pet { background-color: transparent; }"


def _gdk_rect(x: int, y: int, width: int, height: int) -> Gdk.Rectangle:
    # PyGObject ignores Gdk.Rectangle(x, y, w, h) arguments (all zeros), so set the fields.
    rect = Gdk.Rectangle()
    rect.x, rect.y, rect.width, rect.height = x, y, width, height
    return rect


# ======================================================================
# Movement state machine — Shimeji-style
# ======================================================================

class Move(enum.Enum):
    WALK_GROUND = "walk_ground"
    WALK_TOP = "walk_top"
    CLIMB_LEFT = "climb_left"
    CLIMB_RIGHT = "climb_right"
    KICK = "kick"
    JUMP = "jump"
    FALL = "fall"
    THROW = "throw"
    BAD_LAND = "bad_land"
    GOOD_LAND = "good_land"
    HARD_LAND = "hard_land"
    SIT = "sit"
    SCOOTER = "scooter"
    UNICORN = "unicorn"


RIDES = {"scooter": Move.SCOOTER, "unicorn": Move.UNICORN}
STATE_BEHAVIORS = {"clone_kill": "clone_kill", "error": "error", "finger_gun": "finger_gun",
                   "fly_gag": "fly_gag", "vibing": "vibing", "head_pop": "head_pop", "teleport": "teleport_out"}
OPTIONAL_BEHAVIORS = {"scooter", "unicorn", "teleport", "finger_gun", "fly_gag", "vibing", "head_pop"}


class WanderEngine:
    """Shimeji-style movement engine with climbing, falling, and edge awareness.

    Constrained to a single monitor at a time.  Drag-drop to another
    monitor switches the active monitor.  Uses weighted probabilistic
    behavior selection inspired by Shimeji-ee (sit ≫ walk ≫ climb).

    Two modes:
      - **calm** (default): mostly idle, occasional short walks.
      - **active** (--debug): moves frequently, great for testing.
    """

    WALK_SPEED_MIN = 0.6        # px/frame @60fps
    WALK_SPEED_MAX = 1.4        # px/frame @60fps
    CLIMB_SPEED = 0.8           # px/frame @60fps (~48 px/sec)
    FALL_SPEED_INIT = 1.5       # px/frame initial fall
    FALL_ACCEL = 0.35           # px/frame² gravity @60fps (heavy)
    FALL_SPEED_MAX = 8.0        # terminal velocity @60fps
    THROW_GRAVITY = 0.30        # gravity during throw @60fps
    THROW_FRICTION = 0.994      # horizontal drag per frame @60fps
    JUMP_VY_SMALL = (-3.5, -5.0)   # small jump range
    JUMP_VY_BIG = (-8.0, -11.0)   # big jump range
    JUMP_VX_SMALL = 1.5            # horizontal push for small jumps
    JUMP_VX_BIG = 7.0              # horizontal push for big jumps (wider arc)
    JUMP_GRAVITY = 0.12            # gravity during jump
    RIDE_SPEED_START = 1.0         # px/frame when setting off
    RIDE_SPEED_MAX = 4.5           # px/frame cruising (~270 px/sec)
    RIDE_ACCEL = 0.06              # px/frame² until cruising speed
    RIDE_BRAKE = 0.05              # speed cap per px left to the edge

    # Behavior weights (higher = more likely to be chosen)
    #   sit:   stay put          walk:  walk on ground
    #   climb: climb nearest edge
    #   scooter / unicorn: ride across the screen to the far edge
    #   teleport: vanish in smoke, reappear elsewhere on the ground
    CALM_WEIGHTS   = {"sit": 120, "walk": 80, "climb": 20, "kick": 10, "jump": 4, "scooter": 6, "unicorn": 4, "teleport": 4,
                      "finger_gun": 4, "fly_gag": 3, "vibing": 4, "head_pop": 3, "clone_kill": 3, "error": 3}
    ACTIVE_WEIGHTS = {"sit":  50, "walk": 150, "climb": 40, "kick": 18, "jump": 7, "scooter": 12, "unicorn": 8, "teleport": 8,
                      "finger_gun": 6, "fly_gag": 5, "vibing": 6, "head_pop": 5, "clone_kill": 5, "error": 5}
    STUMBLE_CHANCE = 0.0003      # per frame while walking (~2% per second)

    # Sit durations (frames at 60 fps)
    CALM_SIT   = (360, 1500)   # 6–25 s
    ACTIVE_SIT = (180, 480)    # 3–8 s

    # Walk durations (frames) — walk for a while, then pick next behavior
    CALM_WALK   = (180, 480)   # 3–8 s
    ACTIVE_WALK = (240, 900)   # 4–15 s

    FALL_CHANCE_TOP = 0.0008   # per-frame chance to fall while on ceiling

    def __init__(self, monitors: list[tuple[int, int, int, int]],
                 pet_size: int, margin: int = 2,
                 active: bool = False) -> None:
        self._monitors = monitors
        self._pet_size = pet_size
        self._pet_height = pet_size
        self._margin = margin
        self.active_mode = active

        # Start on primary monitor (index 0)
        self._active_idx = 0
        self._update_bounds()

        self.x = self.x_max - 40
        self.y = self.y_max          # ground
        self.direction = -1
        self.move_state = Move.SIT   # start sitting
        self._sit_timer = random.randint(300, 900)  # 5–15 s initial sit
        self._walk_timer = 0
        self._walk_speed = random.uniform(self.WALK_SPEED_MIN, self.WALK_SPEED_MAX)
        self._fall_speed = 0.0
        self._land_timer = 0
        self._throw_vx = 0.0
        self._throw_vy = 0.0
        self._fall_start_y = 0.0
        self._jump_vx = 0.0
        self._jump_vy = 0.0
        self._jump_peak_y = 0.0
        self._ride_speed = 0.0
        self.extras: set[str] = set()
        self.pending_anim: str | None = None

    # --- active monitor ---

    def _update_bounds(self) -> None:
        """Recalculate bounds from the active monitor."""
        m = self._monitors[self._active_idx]
        mx, my, mw, mh = m
        self.x_min = mx + self._margin
        self.x_max = mx + mw - self._pet_size - self._margin
        self.y_min = my + self._margin
        self.y_max = my + mh - self._pet_height - self._margin

    def set_active_monitor_at(self, x: float, y: float) -> None:
        """Switch active monitor to the one containing (x, y)."""
        cx = x + self._pet_size / 2
        cy = y + self._pet_size / 2
        for i, m in enumerate(self._monitors):
            mx, my, mw, mh = m
            if mx <= cx < mx + mw and my <= cy < my + mh:
                if i != self._active_idx:
                    self._active_idx = i
                    self._update_bounds()
                    logger.debug("Switched to monitor %d: %s", i, m)
                return

    # --- behavior selection (Shimeji-style weighted random) ---

    def _pick_behavior(self) -> Move:
        weights = {behavior: weight
                   for behavior, weight in (self.ACTIVE_WEIGHTS if self.active_mode else self.CALM_WEIGHTS).items()
                   if behavior not in OPTIONAL_BEHAVIORS or behavior in self.extras}
        total = sum(weights.values())
        roll = random.random() * total
        cumulative = 0.0
        for behavior, weight in weights.items():
            cumulative += weight
            if roll < cumulative:
                if behavior == "sit":
                    return Move.SIT
                elif behavior == "walk":
                    return Move.WALK_GROUND
                elif behavior == "climb":
                    # Only climb if near an edge
                    if self.x <= self.x_min + 20:
                        return Move.CLIMB_LEFT
                    elif self.x >= self.x_max - 20:
                        return Move.CLIMB_RIGHT
                    return Move.WALK_GROUND  # not near edge, walk
                elif behavior == "kick":
                    return Move.KICK
                elif behavior == "jump":
                    return Move.JUMP
                elif behavior in RIDES:
                    return RIDES[behavior]
                elif behavior in STATE_BEHAVIORS:
                    return behavior
        return Move.SIT

    def _sit_range(self) -> tuple[int, int]:
        return self.ACTIVE_SIT if self.active_mode else self.CALM_SIT

    def _walk_range(self) -> tuple[int, int]:
        return self.ACTIVE_WALK if self.active_mode else self.CALM_WALK

    # --- tick ---

    def tick(self, anim_state: str) -> tuple[int, int]:
        if anim_state != "idle":
            return int(self.x), int(self.y)

        if self.move_state == Move.WALK_GROUND:
            self._do_walk_ground()
        elif self.move_state == Move.WALK_TOP:
            self._do_walk_top()
        elif self.move_state == Move.CLIMB_LEFT:
            self._do_climb_left()
        elif self.move_state == Move.CLIMB_RIGHT:
            self._do_climb_right()
        elif self.move_state == Move.KICK:
            self._do_kick()
        elif self.move_state == Move.JUMP:
            self._do_jump()
        elif self.move_state == Move.FALL:
            self._do_fall()
        elif self.move_state == Move.THROW:
            self._do_throw()
        elif self.move_state == Move.BAD_LAND:
            self._do_land()
        elif self.move_state == Move.GOOD_LAND:
            self._do_land()
        elif self.move_state == Move.HARD_LAND:
            self._do_hard_land()
        elif self.move_state == Move.SIT:
            self._do_sit()
        elif self.move_state in (Move.SCOOTER, Move.UNICORN):
            self._do_ride()

        self.x = max(self.x_min, min(self.x, self.x_max))
        self.y = max(self.y_min, min(self.y, self.y_max))
        return int(self.x), int(self.y)

    # --- movement states ---

    def _do_walk_ground(self) -> None:
        self.y = self.y_max
        self.x += self._walk_speed * self.direction

        if random.random() < self.STUMBLE_CHANCE:
            self.pending_anim = "stumble"
            self._start_sit()
            return

        # Hit an edge?
        if self.x <= self.x_min:
            self.x = self.x_min
            self.direction = 1
            self._transition()
        elif self.x >= self.x_max:
            self.x = self.x_max
            self.direction = -1
            self._transition()
        else:
            self._walk_timer -= 1
            if self._walk_timer <= 0:
                self._transition()

    def _do_walk_top(self) -> None:
        self.y = self.y_min
        self.x += self._walk_speed * self.direction

        if self.x <= self.x_min:
            self.x = self.x_min
            self.direction = 1
        elif self.x >= self.x_max:
            self.x = self.x_max
            self.direction = -1

        if random.random() < self.FALL_CHANCE_TOP:
            self._start_fall()

        self._walk_timer -= 1
        if self._walk_timer <= 0:
            self._start_fall()  # get off the ceiling

    def _do_climb_left(self) -> None:
        self.x = self.x_min
        self.y -= self.CLIMB_SPEED
        if self.y <= self.y_min:
            self.y = self.y_min
            self.direction = 1
            self.move_state = Move.WALK_TOP
            lo, hi = self._walk_range()
            self._walk_timer = random.randint(lo, hi)
        if random.random() < 0.0006:
            self._start_fall()

    def _do_climb_right(self) -> None:
        self.x = self.x_max
        self.y -= self.CLIMB_SPEED
        if self.y <= self.y_min:
            self.y = self.y_min
            self.direction = -1
            self.move_state = Move.WALK_TOP
            lo, hi = self._walk_range()
            self._walk_timer = random.randint(lo, hi)
        if random.random() < 0.0006:
            self._start_fall()

    def _do_fall(self) -> None:
        self._fall_speed = min(self._fall_speed + self.FALL_ACCEL, self.FALL_SPEED_MAX)
        self.y += self._fall_speed
        if self.y >= self.y_max:
            self.y = self.y_max
            self._fall_speed = 0.0
            self._land_from_fall()

    def _land_from_fall(self) -> None:
        """Pick normal or hard landing based on fall distance."""
        fall_dist = self.y_max - self._fall_start_y
        screen_height = self.y_max - self.y_min
        # Hard land if fell more than 40% of screen height
        if fall_dist > screen_height * 0.4:
            self.move_state = Move.HARD_LAND
            self._land_timer = 66
        else:
            self.move_state = Move.BAD_LAND
            self._land_timer = 30     # 1 frame × 500ms delay

    def _do_land(self) -> None:
        self._land_timer -= 1
        if self._land_timer <= 0:
            self.move_state = Move.SIT
            self._sit_timer = random.randint(60, 120)  # 1–2 seconds

    def _do_hard_land(self) -> None:
        self._land_timer -= 1
        if self._land_timer <= 0:
            self.move_state = Move.SIT
            self._sit_timer = random.randint(60, 120)

    def _do_sit(self) -> None:
        self._sit_timer -= 1
        if self._sit_timer <= 0:
            self._transition()

    # --- transitions ---

    def _transition(self) -> None:
        """Pick the next behavior using weighted random selection."""
        nxt = self._pick_behavior()
        if nxt in STATE_BEHAVIORS:
            self.pending_anim = STATE_BEHAVIORS[nxt]
            self._start_sit()
        elif nxt == Move.SIT:
            self._start_sit()
        elif nxt == Move.WALK_GROUND:
            self._start_walk()
        elif nxt in (Move.CLIMB_LEFT, Move.CLIMB_RIGHT):
            self.move_state = nxt
        elif nxt == Move.KICK:
            self._start_kick()
        elif nxt == Move.JUMP:
            self._start_jump()
        elif nxt in (Move.SCOOTER, Move.UNICORN):
            self._start_ride(nxt)
        else:
            self._start_walk()

    def _start_sit(self) -> None:
        self.move_state = Move.SIT
        lo, hi = self._sit_range()
        self._sit_timer = random.randint(lo, hi)

    def _start_walk(self) -> None:
        self.move_state = Move.WALK_GROUND
        self.direction = random.choice([-1, 1])
        self._walk_speed = random.uniform(self.WALK_SPEED_MIN, self.WALK_SPEED_MAX)
        lo, hi = self._walk_range()
        self._walk_timer = random.randint(lo, hi)

    def _start_ride(self, ride: Move) -> None:
        self.move_state = ride
        room_left = self.x - self.x_min
        room_right = self.x_max - self.x
        self.direction = 1 if room_right > room_left else -1
        self._ride_speed = self.RIDE_SPEED_START

    def _do_ride(self) -> None:
        self.y = self.y_max
        distance_to_edge = (self.x_max - self.x) if self.direction > 0 else (self.x - self.x_min)
        self._ride_speed = min(self._ride_speed + self.RIDE_ACCEL,
                               self.RIDE_SPEED_MAX,
                               self.RIDE_SPEED_START + distance_to_edge * self.RIDE_BRAKE)
        self.x += self._ride_speed * self.direction
        if self.x_min < self.x < self.x_max:
            return
        self.x = max(self.x_min, min(self.x, self.x_max))
        self.direction = -self.direction
        self._start_sit()

    def teleport(self) -> None:
        span = self.x_max - self.x_min
        self.x = self.x_min + (self.x - self.x_min + random.uniform(span / 4, span * 3 / 4)) % span
        self.y = self.y_max
        self.direction = random.choice([-1, 1])
        self._start_sit()

    def _start_kick(self) -> None:
        self.move_state = Move.KICK
        vy = random.uniform(*self.JUMP_VY_SMALL)
        vx = self.JUMP_VX_SMALL
        self._jump_vx = vx * self.direction
        self._jump_vy = vy
        self._jump_peak_y = self.y
        self._fall_start_y = self.y

    def _do_kick(self) -> None:
        self._jump_vy += self.JUMP_GRAVITY
        self.x += self._jump_vx
        self.y += self._jump_vy

        if self.y < self._jump_peak_y:
            self._jump_peak_y = self.y

        if self.y >= self.y_max:
            self.y = self.y_max
            self.move_state = Move.GOOD_LAND
            self._land_timer = 30
            return

        if self.x <= self.x_min:
            self.x = self.x_min
            self.move_state = Move.CLIMB_LEFT
            return

        if self.x >= self.x_max:
            self.x = self.x_max
            self.move_state = Move.CLIMB_RIGHT
            return

    def _start_jump(self) -> None:
        self.move_state = Move.JUMP
        vy = random.uniform(*self.JUMP_VY_BIG)
        vx = self.JUMP_VX_BIG
        self._jump_vx = vx * self.direction
        self._jump_vy = vy
        self._jump_peak_y = self.y
        self._fall_start_y = self.y

    def _do_jump(self) -> None:
        self._jump_vy += self.JUMP_GRAVITY
        self.x += self._jump_vx
        self.y += self._jump_vy

        if self.y < self._jump_peak_y:
            self._jump_peak_y = self.y

        # Hit ground?
        if self.y >= self.y_max:
            self.y = self.y_max
            if random.random() < 0.5:
                # Nailed the landing — hold standing pose before next behavior
                self.move_state = Move.GOOD_LAND
                self._land_timer = 40
            else:
                # Faceplant
                self._fall_start_y = self._jump_peak_y
                self._land_from_fall()
            return

        # Hit left wall? Stick and climb!
        if self.x <= self.x_min:
            self.x = self.x_min
            self.move_state = Move.CLIMB_LEFT
            return

        # Hit right wall? Stick and climb!
        if self.x >= self.x_max:
            self.x = self.x_max
            self.move_state = Move.CLIMB_RIGHT
            return

        # Hit ceiling? Stick!
        if self.y <= self.y_min:
            self.y = self.y_min
            self.direction = 1 if self._jump_vx > 0 else -1
            self.move_state = Move.WALK_TOP
            lo, hi = self._walk_range()
            self._walk_timer = random.randint(lo, hi)
            return

    def _start_fall(self) -> None:
        self.move_state = Move.FALL
        self._fall_speed = self.FALL_SPEED_INIT
        self._fall_start_y = self.y

    def _start_throw(self, vx: float, vy: float) -> None:
        self.move_state = Move.THROW
        self._throw_vx = vx
        self._throw_vy = vy
        self.direction = 1 if vx > 0 else -1
        self._fall_start_y = self.y

    def _do_throw(self) -> None:
        self._throw_vy += self.THROW_GRAVITY
        self._throw_vx *= self.THROW_FRICTION
        self.x += self._throw_vx
        self.y += self._throw_vy

        # Hit ground?
        if self.y >= self.y_max:
            self.y = self.y_max
            self._land_from_fall()
            return

        # Hit ceiling? Stick and walk on ceiling!
        if self.y <= self.y_min:
            self.y = self.y_min
            self.direction = 1 if self._throw_vx > 0 else -1
            self.move_state = Move.WALK_TOP
            lo, hi = self._walk_range()
            self._walk_timer = random.randint(lo, hi)
            return

        # Hit left wall? Stick and climb!
        if self.x <= self.x_min:
            self.x = self.x_min
            self.move_state = Move.CLIMB_LEFT
            return

        # Hit right wall? Stick and climb!
        if self.x >= self.x_max:
            self.x = self.x_max
            self.move_state = Move.CLIMB_RIGHT
            return

        # Horizontal velocity died out? Just fall
        if abs(self._throw_vx) < 0.06:
            self._fall_speed = max(self._throw_vy, self.FALL_SPEED_INIT)
            self.move_state = Move.FALL



# ======================================================================
# Monitors
# ======================================================================

Rect = tuple[int, int, int, int]


def _monitor_rect(monitor: Gdk.Monitor) -> Rect:
    g = monitor.get_geometry()
    return (g.x, g.y, g.width, g.height)


def _intersects(a: Rect, b: Rect) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


class SpriteArea(Gtk.DrawingArea):
    """A fixed-size drawing area that renders one sprite frame."""

    def __init__(self, size: int) -> None:
        super().__init__()
        self._draw_sprite = None
        self.active = False   # False: stays where it is but paints fully transparent
        self.set_size(size)
        self.set_draw_func(self._on_draw)

    def set_size(self, size: int) -> None:
        self.set_content_width(size)
        self.set_content_height(size)

    def set_painter(self, painter) -> None:
        self._draw_sprite = painter

    def _on_draw(self, area: Gtk.DrawingArea, ctx: cairo.Context, width: int, height: int) -> None:
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)
        if self.active and self._draw_sprite is not None:
            self._draw_sprite(ctx, width, height)


class MonitorOverlay(Gtk.Window):
    """Full-output transparent layer surface for one monitor.

    Hosts the pet sprite (and the temporary clone) as children of a Gtk.Fixed,
    positioned in monitor-local coordinates. Only the sprite rectangles are
    part of the input region, so the rest of the screen stays interactive.
    """

    def __init__(self, monitor: Gdk.Monitor, size: int) -> None:
        super().__init__()
        self.monitor = monitor
        self.rect = _monitor_rect(monitor)
        self.add_css_class("claude-pet")
        self.set_decorated(False)

        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, "claude-pet")
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_monitor(self, monitor)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
        LayerShell.set_exclusive_zone(self, -1)
        for edge in (LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT,
                     LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM):
            LayerShell.set_anchor(self, edge, True)

        self._fixed = Gtk.Fixed()
        self.set_child(self._fixed)

        self.sprite = SpriteArea(size)
        self.clone = SpriteArea(size)
        self.canvas = self._fixed   # stable coordinate space for gestures and popovers
        self._fixed.put(self.sprite, 0, 0)
        self._fixed.put(self.clone, 0, 0)
        self._positions: dict[SpriteArea, tuple[int, int]] = {}
        self._input_rects: list[Rect] = []
        self.connect("realize", lambda w: self._apply_input_region())

    def place(self, area: SpriteArea, global_x: int, global_y: int, size: int) -> bool:
        """Show `area` at a global desktop position if it touches this monitor."""
        mx, my, _, _ = self.rect
        if not _intersects((global_x, global_y, size, size), self.rect):
            self.park(area)
            return False
        self._fixed.move(area, global_x - mx, global_y - my)
        self._positions[area] = (global_x - mx, global_y - my)
        area.active = True
        area.queue_draw()
        return True

    def park(self, area: SpriteArea) -> None:
        """Blank `area` in place.

        Hiding or moving the widget away leaves its last frame on screen: with
        nothing left to draw, GTK skips the frame and the compositor keeps the
        old buffer. Painting the same spot transparent forces a real repaint.
        """
        if area in self._positions:
            del self._positions[area]
            area.active = False
            area.queue_draw()

    def update_input_region(self) -> None:
        rects = []
        for area, (x, y) in self._positions.items():
            rects.append((x, y, area.get_content_width(), area.get_content_height()))
        if rects != self._input_rects:
            self._input_rects = rects
            self._apply_input_region()

    def _apply_input_region(self) -> None:
        surface = self.get_surface()
        if surface is None:
            return
        region = cairo.Region()
        for x, y, w, h in self._input_rects:
            region.union(cairo.RectangleInt(x, y, w, h))
        surface.set_input_region(region)


# ======================================================================
# Pet controller
# ======================================================================

class Pet:
    """Drives the sprite across all monitors and reacts to Claude Code state."""

    def __init__(
        self,
        character: CharacterProto,
        bridge: ClaudeBridgeProto,
        size: int = 128,
        debug: bool = False,
        sprites_dir: str | None = None,
        mascot_path: str | None = None,
        monitor: str | None = None,
        on_quit=None,
    ) -> None:
        self.character = character
        self._preferred_monitor = monitor
        self.bridge = bridge
        self._size = size
        self._debug = debug
        self._sprites_dir = sprites_dir
        self._mascot_path = mascot_path
        self._on_quit = on_quit

        self._drag_active = False
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0
        self._drag_prev_x = 0.0
        self._drag_prev_y = 0.0
        self._drag_vel_x = 0.0       # actual mouse velocity for throw
        self._drag_vel_y = 0.0
        self._drag_swing = 0.0       # pendulum position (visual only)
        self._drag_swing_vel = 0.0
        self._wander_enabled = True

        # When True, bridge poll won't override the current state.
        # Set when user picks a state from the menu; cleared when the
        # animation finishes (non-looping) or user picks "Auto".
        self._manual_override = False
        self._menu_timeout_id: int | None = None
        self._frame_timer_id: int | None = None
        self._wander: WanderEngine | None = None
        self._draw_offset_x: int = 0
        self._draw_offset_y: int = 0

        # Clone-kill animation: a second sprite drawn next to the pet
        self._clone: dict | None = None
        self._clone_timer_id: int | None = None

        self._last_activity = time.monotonic()
        self._after_nap: str | None = None
        self._nap_ends_at: float | None = None
        self._menu_move = False
        self._working_since: float | None = None
        self._last_doze = -DOZE_COOLDOWN_S

        self._overlays: list[MonitorOverlay] = []
        self._display = Gdk.Display.get_default()
        self._install_css()
        self._actions = self._build_actions()
        self._build_overlays()
        self._monitors_model = self._display.get_monitors()
        self._monitors_model.connect("items-changed", self._on_monitors_changed)
        self._init_wander()
        self._start_timers()
        self._start_bridge()

    # ------------------------------------------------------------------
    # Overlays (one per monitor)
    # ------------------------------------------------------------------

    def _install_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(TRANSPARENT_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self._display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build_overlays(self) -> None:
        for overlay in self._overlays:
            overlay.destroy()
        self._overlays = []
        monitors = self._display.get_monitors()
        for i in range(monitors.get_n_items()):
            overlay = MonitorOverlay(monitors.get_item(i), self._size)
            overlay.insert_action_group("pet", self._actions)
            self._attach_input(overlay)
            overlay.present()
            self._overlays.append(overlay)
        logger.debug("Monitors: %s", [o.rect for o in self._overlays])

    def _on_monitors_changed(self, model, position, removed, added) -> None:
        logger.debug("Monitor layout changed, rebuilding overlays")
        self._build_overlays()
        self._init_wander()

    def _monitor_rects(self) -> list[Rect]:
        return [o.rect for o in self._overlays]

    def _spawn_rect(self) -> Rect:
        """The preferred monitor (by connector name, e.g. DP-6), else the first one."""
        for overlay in self._overlays:
            if overlay.monitor.get_connector() == self._preferred_monitor:
                return overlay.rect
        return self._overlays[0].rect

    # ------------------------------------------------------------------
    # Wandering
    # ------------------------------------------------------------------

    def _init_wander(self) -> None:
        prev = self._wander
        self._wander = WanderEngine(
            monitors=self._monitor_rects(),
            pet_size=self._size,
            active=self._debug,
        )
        if prev is not None:
            self._wander.x = prev.x
            self._wander.set_active_monitor_at(prev.x, prev.y)
        else:
            gx, gy, gw, gh = self._spawn_rect()
            margin = 50
            self._wander.x = float(random.randint(gx + margin, gx + gw - self._size - margin))
        # Snap to ground so we don't start floating
        self._wander.y = self._wander.y_max
        self._sync_extras()
        logger.debug("Bounds: x=[%.0f, %.0f] y=[%.0f, %.0f], mode: %s",
                     self._wander.x_min, self._wander.x_max,
                     self._wander.y_min, self._wander.y_max,
                     "active" if self._debug else "calm")
        self._render()

    def _sync_extras(self) -> None:
        if self._wander is not None:
            self._wander.extras = {behavior for behavior in OPTIONAL_BEHAVIORS
                                   if self.character.supports(STATE_BEHAVIORS.get(behavior, behavior))}

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _start_timers(self) -> None:
        self._frame_timer_id = GLib.timeout_add(FRAME_INTERVAL_MS, self._on_frame_tick)

    def _stop_timers(self) -> None:
        if self._frame_timer_id is not None:
            GLib.source_remove(self._frame_timer_id)
            self._frame_timer_id = None

    def _on_animation_finished(self, finished: str) -> None:
        if finished == "teleport_out" and self._wander is not None:
            self._wander.teleport()
            self._draw_offset_x = self._draw_offset_y = 0
            self._render()
        elif finished == "nap_wake":
            self._last_activity = time.monotonic()
            if self._after_nap:
                self.character.set_state(self._after_nap)
                self._after_nap = None
        elif finished == "laptop_doze":
            self._resume_claude_state()

    def _resume_claude_state(self) -> None:
        claude_state = self.bridge.get_state()
        self.character.set_state(claude_state if claude_state in ONGOING_CLAUDE_STATES else "idle")

    def _track_activity(self) -> None:
        if self.character.state != "idle" and self.character.state not in NAP_STATES:
            self._last_activity = time.monotonic()

    def _maybe_fall_asleep(self) -> None:
        if (self.character.state == "idle"
                and not self._drag_active
                and self._wander is not None
                and self._wander.move_state == Move.SIT
                and self.character.supports("nap_start")
                and time.monotonic() - self._last_activity > NAP_AFTER_IDLE_S):
            self.character.set_state("nap_start")

    def _maybe_wake_up(self) -> None:
        if self.character.state != "napping":
            self._nap_ends_at = None
            return
        now = time.monotonic()
        if self._nap_ends_at is None:
            self._nap_ends_at = now + random.uniform(*NAP_LENGTH_S)
        elif now >= self._nap_ends_at:
            self.character.set_state("nap_wake")

    def _finish_menu_move(self) -> None:
        if self._menu_move and self._wander is not None and self._wander.move_state == Move.SIT:
            self._menu_move = False
            self._manual_override = False
            self._resume_claude_state()

    def _maybe_doze(self) -> None:
        now = time.monotonic()
        if self.character.state != "working":
            self._working_since = None
            return
        if self._working_since is None:
            self._working_since = now
        if (now - self._working_since > DOZE_AFTER_WORKING_S
                and now - self._last_doze > DOZE_COOLDOWN_S
                and self.character.supports("laptop_doze")
                and random.random() < FRAME_INTERVAL_MS / 1000 / DOZE_MEAN_WAIT_S):
            self._last_doze = now
            self.character.set_state("laptop_doze")

    def _visual_key(self) -> tuple:
        c = self.character
        return (c.state, c.frame, c.move_state, c.facing)

    def _on_frame_tick(self) -> bool:
        prev_state = self.character.state
        prev_visual = self._visual_key()
        self.character.tick()

        # If a non-looping animation just finished (state changed),
        # clear the manual override so the bridge can take over again.
        if self._manual_override and prev_state != self.character.state:
            if not self.character.is_busy:
                self._manual_override = False
                logger.debug("Manual override cleared (animation finished)")

        # Detect doubling finished → spawn clone
        if (prev_state == "doubling"
                and self.character.state == "clone_frozen"
                and self._clone is None):
            self._spawn_clone()

        if prev_state != self.character.state:
            self._on_animation_finished(prev_state)
        self._track_activity()
        self._maybe_fall_asleep()
        self._maybe_wake_up()
        self._maybe_doze()

        # Update pendulum swing during drag (keeps swinging when mouse stops)
        if self._drag_active:
            spring = -self._drag_swing * 0.05
            damping = -self._drag_swing_vel * 0.25
            self._drag_swing_vel += spring + damping
            self._drag_swing += self._drag_swing_vel
            self.character.set_movement(self._swing_sprite(), -1)

        moved = False
        # Move unless dragging, wander disabled, or character is busy
        if ((self._wander_enabled or self._menu_move)
                and not self._drag_active
                and self._clone is None
                and not self.character.is_busy
                and self._wander is not None):
            old = (int(self._wander.x), int(self._wander.y))
            new = self._wander.tick(self.character.state)
            moved = new != old
            self._finish_menu_move()

            # Check if wander wants to trigger a character animation
            # Only apply during idle — don't override bridge states like attention
            if self._wander.pending_anim:
                anim = self._wander.pending_anim
                self._wander.pending_anim = None
                if self.character.state == "idle":
                    if anim == "clone_kill":
                        self._manual_override = True
                        self.character.set_state("doubling")
                    else:
                        self.character.set_state(anim)

            # Shift the sprite to hug screen edges while climbing / on the ceiling
            ms = self._wander.move_state
            if ms == Move.CLIMB_LEFT:
                offsets = (-int(self._size * 0.50), 0)
            elif ms == Move.CLIMB_RIGHT:
                offsets = (int(self._size * 0.50), 0)
            elif ms == Move.WALK_TOP:
                offsets = (0, -int(self._size * 0.40))
            else:
                offsets = (0, 0)
            if offsets != (self._draw_offset_x, self._draw_offset_y):
                self._draw_offset_x, self._draw_offset_y = offsets
                moved = True

        # Sync movement state to character (for sprite selection)
        # Skip during drag — drag sprites are set by the drag gesture
        if self._wander is not None and not self._drag_active and self._clone is None:
            move_map = {
                Move.WALK_GROUND: "walk",
                Move.WALK_TOP: "ceiling",
                Move.CLIMB_LEFT: "climb",
                Move.CLIMB_RIGHT: "climb",
                Move.FALL: "fall",
                Move.THROW: "fall",
                Move.BAD_LAND: "bad_land",
                Move.GOOD_LAND: "good_land",
                Move.HARD_LAND: "hard_land",
                Move.SIT: "sit",
                Move.KICK: "kick",
                Move.JUMP: "jump_launch",
                Move.SCOOTER: "scooter",
                Move.UNICORN: "unicorn",
            }
            move_name = move_map.get(self._wander.move_state, "")
            # Climb sprites face left; face toward the wall
            if self._wander.move_state == Move.CLIMB_LEFT:
                facing = -1
            elif self._wander.move_state == Move.CLIMB_RIGHT:
                facing = 1
            else:
                facing = self._wander.direction
            self.character.set_movement(move_name, facing)

        if moved or self._drag_active:
            self._render()
        elif self._visual_key() != prev_visual:
            self._redraw_sprite()
        return True

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _sprite_pos(self) -> tuple[int, int]:
        return (int(self._wander.x) + self._draw_offset_x,
                int(self._wander.y) + self._draw_offset_y)

    def _render(self) -> None:
        """Position the sprite (and clone) on the active monitor.

        The edge-hugging offsets push the sprite past the screen edge while it
        climbs, so it is clipped to its monitor — only a drag may span monitors.
        """
        x, y = self._sprite_pos()
        active = None if self._drag_active else self._overlays[self._wander._active_idx]
        for overlay in self._overlays:
            if active is not None and overlay is not active:
                overlay.park(overlay.sprite)
                overlay.park(overlay.clone)
                overlay.update_input_region()
                continue
            overlay.sprite.set_painter(self.character.draw)
            overlay.place(overlay.sprite, x, y, self._size)
            if self._clone is not None:
                overlay.clone.set_painter(self._draw_clone)
                overlay.place(overlay.clone, self._clone["x"], self._clone["y"], self._size)
            else:
                overlay.park(overlay.clone)
            overlay.update_input_region()

    def _redraw_sprite(self) -> None:
        for overlay in self._overlays:
            overlay.sprite.queue_draw()

    def _draw_clone(self, ctx: cairo.Context, width: int, height: int) -> None:
        clone = self._clone
        if clone is None:
            return
        idx = clone["indices"][clone["frame"] % len(clone["indices"])]
        surface = self.character._sprites.get(idx)
        if surface is None:
            return
        sx = width / surface.get_width()
        sy = height / surface.get_height()
        ctx.save()
        if clone["facing"] > 0:
            ctx.translate(width, 0)
            ctx.scale(-sx, sy)
        else:
            ctx.scale(sx, sy)
        ctx.set_source_surface(surface, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_NEAREST)
        ctx.paint()
        ctx.restore()

    # ------------------------------------------------------------------
    # Bridge
    # ------------------------------------------------------------------

    def _start_bridge(self) -> None:
        def on_state_change(new_state: str) -> None:
            GLib.idle_add(self._apply_bridge_state, new_state)
        try:
            self.bridge.start_watching(on_state_change)
        except Exception:
            logger.exception("Failed to start bridge watcher")

    def _apply_bridge_state(self, new_state: str) -> bool:
        if self._manual_override:
            return False
        if self.character.state in NAP_STATES:
            if new_state and new_state != "idle":
                self._after_nap = new_state
                self.character.set_state("nap_wake")
            return False
        if self.character.state == "laptop_doze" and new_state == "working":
            return False
        if new_state and new_state != self.character.state:
            logger.debug("Bridge callback: %s -> %s", self.character.state, new_state)
            # "doubling" triggers clone-kill — lock out bridge until animation finishes
            if new_state == "doubling" and self._clone is None:
                self._manual_override = True
            self.character.set_state(new_state)
        return False

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _attach_input(self, overlay: MonitorOverlay) -> None:
        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin, overlay)
        drag.connect("drag-update", self._on_drag_update, overlay)
        drag.connect("drag-end", self._on_drag_end, overlay)
        # Attached to the container, not the sprite: gesture offsets are relative
        # to the widget that owns the gesture, and the sprite is the thing moving.
        overlay.canvas.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(3)
        click.connect("pressed", self._on_right_click, overlay)
        overlay.canvas.add_controller(click)

    def _on_drag_begin(self, gesture, start_x: float, start_y: float, overlay: MonitorOverlay) -> None:
        self._drag_active = True
        self._drag_start_x = self._wander.x
        self._drag_start_y = self._wander.y
        self._drag_prev_x = 0.0
        self._drag_prev_y = 0.0
        self._drag_vel_x = 0.0
        self._drag_vel_y = 0.0
        self._drag_swing = 0.0
        self._drag_swing_vel = 0.0
        self._draw_offset_x = 0
        self._draw_offset_y = 0
        self.character.set_movement("drag", -1)
        self._last_activity = time.monotonic()
        if self.character.state in ("nap_start", "napping"):
            self.character.set_state("nap_wake")

    def _on_drag_update(self, gesture, offset_x: float, offset_y: float, overlay: MonitorOverlay) -> None:
        if not self._drag_active:
            return
        self._wander.x = self._drag_start_x + offset_x
        self._wander.y = self._drag_start_y + offset_y

        # Track real velocity for throw detection
        dx = offset_x - self._drag_prev_x
        dy = offset_y - self._drag_prev_y
        self._drag_prev_x = offset_x
        self._drag_prev_y = offset_y
        self._drag_vel_x = self._drag_vel_x * 0.3 + dx * 0.7
        self._drag_vel_y = self._drag_vel_y * 0.3 + dy * 0.7
        push = dx * 0.01                         # mouse drags the swing
        spring = -self._drag_swing * 0.025       # spring pulls back to center @60fps
        damping = -self._drag_swing_vel * 0.06   # friction @60fps
        self._drag_swing_vel += push + spring + damping
        self._drag_swing += self._drag_swing_vel
        self.character.set_movement(self._swing_sprite(), -1)
        self._render()

    def _swing_sprite(self) -> str:
        swing = self._drag_swing
        speed = abs(swing)
        if speed < 0.2:
            return "drag"
        if swing < 0:  # swinging left
            if speed < 0.6:
                return "drag_left_slow"
            if speed < 1.5:
                return "drag_left_fast"
            return "drag_left_vfast"
        if speed < 0.6:
            return "drag_right_slow"
        return "drag_right_fast"

    def _on_drag_end(self, gesture, offset_x: float, offset_y: float, overlay: MonitorOverlay) -> None:
        if not self._drag_active:
            return
        self._drag_active = False
        # Detect monitor switch on drop
        self._wander.set_active_monitor_at(self._wander.x, self._wander.y)
        self._wander.x = max(self._wander.x_min, min(self._wander.x, self._wander.x_max))
        self._wander.y = max(self._wander.y_min, min(self._wander.y, self._wander.y_max))

        # On the ground already?
        if self._wander.y >= self._wander.y_max - 5:
            self._wander.y = self._wander.y_max
            self._wander._start_sit()
        else:
            # Throw or drop based on release velocity
            speed = (self._drag_vel_x ** 2 + self._drag_vel_y ** 2) ** 0.5
            if speed > 0.3:
                self._wander._start_throw(self._drag_vel_x, self._drag_vel_y)
            else:
                self._wander._start_fall()
        self._render()

    def _on_right_click(self, gesture, n_press: int, x: float, y: float, overlay: MonitorOverlay) -> None:
        self._show_context_menu(overlay, x, y)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _build_actions(self) -> Gio.SimpleActionGroup:
        group = Gio.SimpleActionGroup()

        auto = Gio.SimpleAction.new_stateful("auto", None, GLib.Variant.new_boolean(True))
        auto.connect("change-state", self._on_menu_auto)
        group.add_action(auto)

        wander = Gio.SimpleAction.new_stateful("wander", None, GLib.Variant.new_boolean(True))
        wander.connect("change-state", self._on_menu_toggle_wander)
        group.add_action(wander)

        scale = Gio.SimpleAction.new_stateful(
            "scale", GLib.VariantType.new("d"), GLib.Variant.new_double(self._size / SPRITE_BASE))
        scale.connect("change-state", self._on_menu_scale)
        group.add_action(scale)

        mascot = Gio.SimpleAction.new_stateful(
            "mascot", GLib.VariantType.new("s"), GLib.Variant.new_string(self._mascot_path or ""))
        mascot.connect("change-state", self._on_menu_mascot)
        group.add_action(mascot)

        for name, handler in (("kick", self._on_menu_kick), ("jump", self._on_menu_jump),
                              ("clone-kill", self._on_menu_clone_kill), ("quit", self._on_menu_quit)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            group.add_action(action)

        for name, handler in (("state", self._on_menu_set_state), ("ride", self._on_menu_ride)):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", handler)
            group.add_action(action)
        return group

    def _build_menu_model(self) -> Gio.Menu:
        menu = Gio.Menu()

        section = Gio.Menu()
        section.append("Auto (follow Claude)", "pet.auto")
        section.append("Wander", "pet.wander")
        scale_sub = Gio.Menu()
        for s in SCALE_OPTIONS:
            item = Gio.MenuItem.new(f"{s:.1f}x", None)
            item.set_action_and_target_value("pet.scale", GLib.Variant.new_double(s))
            scale_sub.append_item(item)
        section.append_submenu("Scale", scale_sub)
        mascots = self._list_mascots() if self._sprites_dir else []
        if len(mascots) > 1:
            mascot_sub = Gio.Menu()
            for name, path in mascots:
                item = Gio.MenuItem.new(name, None)
                item.set_action_and_target_value("pet.mascot", GLib.Variant.new_string(path))
                mascot_sub.append_item(item)
            section.append_submenu("Mascot", mascot_sub)
        menu.append_section(None, section)

        section = Gio.Menu()
        section.append("Kick", "pet.kick")
        section.append("Jump", "pet.jump")
        for label, ride in (("Scooter", "scooter"), ("Unicorn", "unicorn")):
            if self.character.supports(ride):
                section.append_item(self._menu_item(label, "pet.ride", ride))
        if self.character.supports("teleport_out"):
            section.append_item(self._menu_item("Teleport", "pet.state", "teleport_out"))
        section.append("Clone & Kill", "pet.clone-kill")
        tricks = Gio.Menu()
        for label, state in TRICKS:
            if self.character.supports(state):
                tricks.append_item(self._menu_item(label, "pet.state", state))
        if tricks.get_n_items():
            section.append_submenu("Tricks", tricks)
        menu.append_section(None, section)

        section = Gio.Menu()
        for state_name in TEST_STATES:
            item = Gio.MenuItem.new(state_name.capitalize(), None)
            item.set_action_and_target_value("pet.state", GLib.Variant.new_string(state_name))
            section.append_item(item)
        menu.append_section(None, section)

        section = Gio.Menu()
        section.append("Quit", "pet.quit")
        menu.append_section(None, section)
        return menu

    @staticmethod
    def _menu_item(label: str, action: str, target: str) -> Gio.MenuItem:
        item = Gio.MenuItem.new(label, None)
        item.set_action_and_target_value(action, GLib.Variant.new_string(target))
        return item

    def _show_context_menu(self, overlay: MonitorOverlay, x: float, y: float) -> None:
        self._actions.lookup_action("auto").set_state(GLib.Variant.new_boolean(not self._manual_override))
        popover = Gtk.PopoverMenu.new_from_model(self._build_menu_model())
        popover.set_parent(overlay.canvas)
        popover.set_has_arrow(False)
        popover.set_pointing_to(_gdk_rect(int(x), int(y), 1, 1))
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        popover.popup()

    def _on_wander_anim_timeout(self) -> bool:
        if not self._manual_override:
            self.character.set_state("idle")
        return False

    def _start_menu_move(self, start) -> None:
        if self._wander is None:
            return
        self._cancel_menu_timeout()
        self._after_nap = None
        self._manual_override = True
        self._menu_move = True
        self.character.set_state("idle")
        start()

    def _on_menu_kick(self, action, param) -> None:
        self._start_menu_move(lambda: self._wander._start_kick())

    def _on_menu_jump(self, action, param) -> None:
        self._start_menu_move(lambda: self._wander._start_jump())

    def _on_menu_ride(self, action, value) -> None:
        ride = RIDES[value.get_string()]
        self._start_menu_move(lambda: self._wander._start_ride(ride))

    def _on_menu_clone_kill(self, action, param) -> None:
        if self._clone is not None:
            return  # already running
        self._manual_override = True
        self.character.set_state("doubling")

    def _spawn_clone(self) -> None:
        """Spawn a clone sprite that 'kills' the original."""
        x, y = self._sprite_pos()
        # Clone spawns behind the original and faces it
        facing = self._wander.direction if self._wander else -1
        clone_x = x - facing * (self._size // 2)  # behind = opposite of facing
        # Attack animation: stand, jump, kick, kick, stand victorious
        self._clone = {"x": clone_x, "y": y, "facing": facing,
                       "indices": [27, 28, 29], "frame": 0}
        self._clone_timer_id = GLib.timeout_add(300, self._on_clone_tick)
        self._render()
        logger.debug("Clone spawned at (%d, %d)", clone_x, y)

    def _on_clone_tick(self) -> bool:
        if self._clone is None:
            return False
        self._clone["frame"] += 1
        if self._clone["frame"] >= len(self._clone["indices"]):
            self._clone_timer_id = None
            self._on_clone_done()
            return False
        self._render()
        return True

    def _on_clone_done(self) -> None:
        """Clone finished its attack. Original dies in place, clone stays."""
        # Keep clone alive while original plays death animation
        self._clone["frame"] = len(self._clone["indices"]) - 1
        self.character.set_state("stumble")
        # After death sprites finish (3 frames × 300ms = 900ms), swap
        GLib.timeout_add(900, self._on_clone_death_done)
        logger.debug("Clone attack done, original dying")

    def _on_clone_death_done(self) -> bool:
        """Original finished dying. It reappears where the clone stood."""
        if self._clone is None:
            return False
        clone_x, clone_y = self._clone["x"], self._clone["y"]
        self._clone = None
        if self._wander:
            self._wander.x = float(clone_x - self._draw_offset_x)
            self._wander.y = float(clone_y - self._draw_offset_y)
        self._manual_override = False
        self.character.set_state("idle")
        self._render()
        logger.debug("Clone kill complete, moved to (%d, %d)", clone_x, clone_y)
        return False

    def _on_menu_auto(self, action, value) -> None:
        action.set_state(value)
        self._manual_override = not value.get_boolean()
        if not self._manual_override:
            # Immediately sync with bridge
            state = self.bridge.get_state()
            if state:
                self.character.set_state(state)

    def _on_menu_toggle_wander(self, action, value) -> None:
        action.set_state(value)
        self._wander_enabled = value.get_boolean()

    def _on_menu_scale(self, action, value) -> None:
        action.set_state(value)
        new_size = int(SPRITE_BASE * value.get_double())
        if new_size == self._size:
            return
        self._size = new_size
        for overlay in self._overlays:
            overlay.sprite.set_size(new_size)
            overlay.clone.set_size(new_size)
        self._init_wander()
        logger.debug("Scale changed to %.1fx (%dpx)", value.get_double(), new_size)

    def _list_mascots(self) -> list[tuple[str, str]]:
        """Return sorted list of (display_name, path) for mascots in sprites_dir."""
        result = []
        for entry in sorted(os.listdir(self._sprites_dir)):
            path = os.path.join(self._sprites_dir, entry)
            if os.path.isdir(path):
                result.append((entry.replace("_", " ").title(), path))
        return result

    def _on_menu_mascot(self, action, value) -> None:
        path = value.get_string()
        if path == self._mascot_path:
            return
        from sprite_character import SpriteCharacter
        new_char = SpriteCharacter(path)
        if not new_char._sprites:
            logger.warning("No sprites in %s, ignoring", path)
            return
        action.set_state(value)
        self._mascot_path = path
        self.character = new_char
        self._sync_extras()
        self._render()
        logger.info("Switched mascot to %s (%d sprites)", path, len(new_char._sprites))
        # Persist selection as default
        try:
            from main import load_config, save_config
            cfg = load_config()
            cfg["mascot"] = os.path.basename(path)
            save_config(cfg)
        except Exception:
            pass

    def _on_menu_set_state(self, action, value) -> None:
        state = value.get_string()
        self._manual_override = True
        self._menu_move = False
        self._after_nap = None
        self.character.set_state(state)
        self._cancel_menu_timeout()

        # Looping states get an auto-return to idle after ~3 loops
        cfg = self.character._state_config.get(state, {})
        if cfg.get("loop", True):
            duration_ms = self.character.animation_ms(state) * 3
            self._menu_timeout_id = GLib.timeout_add(duration_ms, self._on_menu_timeout)

    def _cancel_menu_timeout(self) -> None:
        if self._menu_timeout_id is not None:
            GLib.source_remove(self._menu_timeout_id)
            self._menu_timeout_id = None

    def _on_menu_timeout(self) -> bool:
        """Return to idle after a menu-selected looping animation preview."""
        self._manual_override = False
        self.character.set_state("idle")
        self._menu_timeout_id = None
        return False

    def _on_menu_quit(self, action, param) -> None:
        self.shutdown()
        if self._on_quit is not None:
            self._on_quit()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        self._stop_timers()
        for timer in (self._menu_timeout_id, self._clone_timer_id):
            if timer is not None:
                GLib.source_remove(timer)
        self._menu_timeout_id = None
        self._clone_timer_id = None
        try:
            self.bridge.stop_watching()
        except Exception:
            logger.exception("Error stopping bridge")
        for overlay in self._overlays:
            overlay.destroy()
        self._overlays = []
