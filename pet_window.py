"""GTK3 transparent floating window for the Claude Pet desktop companion.

Creates a borderless, always-on-top, RGBA-transparent window suitable
for X11 with a picom compositor. Wanders across the screen like a
Shimeji desktop pet with climbing, falling, and edge awareness.
Supports multi-monitor setups.
"""

from __future__ import annotations

import enum
import logging
import random
import subprocess
from typing import Protocol

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


class CharacterProto(Protocol):
    state: str
    frame: int
    is_busy: bool
    def draw(self, ctx: cairo.Context, width: int, height: int) -> None: ...
    def tick(self) -> None: ...
    def set_state(self, state: str) -> None: ...
    def set_movement(self, move: str, facing: int) -> None: ...


class ClaudeBridgeProto(Protocol):
    def get_state(self) -> str: ...
    def start_watching(self, callback: object) -> None: ...
    def stop_watching(self) -> None: ...


FRAME_INTERVAL_MS = 1000 // 60
TEST_STATES = ("idle", "thinking", "working", "attention", "celebrating")
SPRITE_BASE = 128  # Shimeji sprites are 128x128
SCALE_OPTIONS = (0.5, 1.0, 1.5, 2.0)
LABEL_HEIGHT = 20  # Extra height below sprite for project name label


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

    # Behavior weights (higher = more likely to be chosen)
    #   sit:   stay put          walk:  walk on ground
    #   climb: climb nearest edge
    CALM_WEIGHTS   = {"sit": 200, "walk": 50, "climb": 10, "kick": 6, "jump": 2, "clone_kill": 2, "error": 2}
    ACTIVE_WEIGHTS = {"sit":  50, "walk": 150, "climb": 40, "kick": 18, "jump": 7, "clone_kill": 5, "error": 5}
    STUMBLE_CHANCE = 0.0003      # per frame while walking (~2% per second)
    STUMBLE_CHANCE_CLOSE = 0.003  # per frame when another pet is very close (~16% per second)

    # Sit durations (frames at 60 fps)
    CALM_SIT   = (600, 2400)   # 10–40 s
    ACTIVE_SIT = (180, 480)    # 3–8 s

    # Walk durations (frames) — walk for a while, then pick next behavior
    CALM_WALK   = (120, 360)   # 2–6 s
    ACTIVE_WALK = (240, 900)   # 4–15 s

    FALL_CHANCE_TOP = 0.0008   # per-frame chance to fall while on ceiling

    def __init__(self, monitors: list[tuple[int, int, int, int]],
                 pet_size: int, pet_height: int | None = None,
                 margin: int = 2,
                 active: bool = False) -> None:
        self._monitors = monitors
        self._pet_size = pet_size
        self._pet_height = pet_height or pet_size
        self._margin = margin
        self.active_mode = active
        self._social_block_sit = False  # set by PetWindow from social directive
        self._social_peer_nearby = False  # True when another pet is very close

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

    def _pick_behavior(self, block_sit: bool = False) -> Move:
        weights = dict(self.ACTIVE_WEIGHTS if self.active_mode else self.CALM_WEIGHTS)
        if block_sit:
            weights.pop("sit", None)
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
                elif behavior in ("clone_kill", "error"):
                    return behavior
        return Move.SIT

    def _sit_range(self) -> tuple[int, int]:
        return self.ACTIVE_SIT if self.active_mode else self.CALM_SIT

    def _walk_range(self) -> tuple[int, int]:
        return self.ACTIVE_WALK if self.active_mode else self.CALM_WALK

    # --- tick ---

    def tick(self, anim_state: str) -> tuple[int, int]:
        if anim_state in ("working", "thinking", "error", "attention",
                          "doubling", "clone_frozen", "stumble",
                          "celebrating", "attack"):
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

        self.x = max(self.x_min, min(self.x, self.x_max))
        self.y = max(self.y_min, min(self.y, self.y_max))
        return int(self.x), int(self.y)

    # --- movement states ---

    def _do_walk_ground(self) -> None:
        self.y = self.y_max
        self.x += self._walk_speed * self.direction

        # Random stumble while walking (more likely when another pet is very close)
        chance = self.STUMBLE_CHANCE_CLOSE if self._social_peer_nearby else self.STUMBLE_CHANCE
        if random.random() < chance:
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
        nxt = self._pick_behavior(block_sit=self._social_block_sit)
        if nxt in ("clone_kill", "error"):
            self.pending_anim = nxt
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
# Clone window (temporary sprite overlay for clone-kill animation)
# ======================================================================

class CloneWindow(Gtk.Window):
    """Lightweight temporary window that plays a sprite animation and calls back."""

    def __init__(self, sprites: dict, indices: list[int], delay: int,
                 size: int, x: int, y: int, facing: int,
                 on_done: callable) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self._sprites = sprites
        self._indices = indices
        self._delay = delay
        self._size = size
        self._facing = facing
        self._frame = 0
        self._on_done = on_done

        self.set_default_size(size, size)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)

        self._da = Gtk.DrawingArea()
        self._da.set_size_request(size, size)
        self._da.connect("draw", self._on_draw)
        self.add(self._da)

        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.connect("realize", self._on_realize)
        self.move(x, y)
        self.show_all()
        self._timer = GLib.timeout_add(delay, self._tick)

    def _on_realize(self, widget: Gtk.Window) -> None:
        try:
            xid = self.get_window().get_xid()
            subprocess.Popen(
                ["xprop", "-id", str(xid),
                 "-f", "_COMPTON_SHADOW", "32c",
                 "-set", "_COMPTON_SHADOW", "0"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _on_draw(self, widget: Gtk.DrawingArea, ctx: cairo.Context) -> bool:
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)

        idx = self._indices[self._frame % len(self._indices)]
        surface = self._sprites.get(idx)
        if surface is None:
            return True

        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        sw = surface.get_width()
        sh = surface.get_height()

        ctx.save()
        sx = w / sw
        sy = h / sh
        if self._facing > 0:
            ctx.translate(w, 0)
            ctx.scale(-sx, sy)
        else:
            ctx.scale(sx, sy)
        ctx.set_source_surface(surface, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_NEAREST)
        ctx.paint()
        ctx.restore()
        return True

    def _tick(self) -> bool:
        self._frame += 1
        if self._frame >= len(self._indices):
            self._on_done(self)
            return False
        self._da.queue_draw()
        return True


# ======================================================================
# Main window
# ======================================================================

class PetWindow(Gtk.Window):
    """Transparent floating pet window for X11/i3.

    Uses POPUP type to bypass the window manager — no struts, no tiling,
    always rendered on top. Supports multi-monitor.
    """

    def __init__(
        self,
        character: CharacterProto,
        bridge: ClaudeBridgeProto,
        size: int = 192,
        debug: bool = False,
        sprites_dir: str | None = None,
        mascot_path: str | None = None,
        project_name: str | None = None,
        social_engine: object | None = None,
    ) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)

        self.character = character
        self.bridge = bridge
        self._size = size
        self._debug = debug
        self._sprites_dir = sprites_dir
        self._mascot_path = mascot_path
        self._project_name = project_name
        self._social = social_engine
        self._label_height = LABEL_HEIGHT if project_name else 0

        self._drag_active = False
        self._drag_offset_x = 0.0
        self._drag_offset_y = 0.0
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
        self._wander_anim_timer_id: int | None = None

        self._frame_timer_id: int | None = None
        self._wander: WanderEngine | None = None
        self._draw_offset_x: int = 0
        self._draw_offset_y: int = 0
        self._label_on_top: bool = True
        self._clone_window: CloneWindow | None = None
        self._clone_falling: bool = False
        self._last_social_directive = None
        self._pending_throw: tuple[float, float] | None = None

        self._setup_window()
        self._setup_drawing()
        self._setup_input()
        self._place_on_screen()
        self._init_wander()
        self._start_timers()
        self._start_bridge()

    # ------------------------------------------------------------------
    # Window configuration
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.set_default_size(self._size, self._size + self._label_height)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
            logger.debug("RGBA visual enabled")
        else:
            logger.warning("RGBA visual not available")

        self.set_app_paintable(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.connect("realize", self._on_realize)
        self.connect("destroy", self._on_destroy)

    def _setup_drawing(self) -> None:
        self._drawing_area = Gtk.DrawingArea()
        self._drawing_area.set_size_request(self._size, self._size + self._label_height)
        self._drawing_area.connect("draw", self._on_draw)
        self.add(self._drawing_area)

    def _setup_input(self) -> None:
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion)

    def _get_monitor_geometries(self) -> list[tuple[int, int, int, int]]:
        """Get (x, y, width, height) for every connected monitor."""
        screen = self.get_screen()
        monitors = []
        for i in range(screen.get_n_monitors()):
            g = screen.get_monitor_geometry(i)
            monitors.append((g.x, g.y, g.width, g.height))
        return monitors

    def _get_primary_monitor_geometry(self) -> Gdk.Rectangle:
        screen = self.get_screen()
        monitor = screen.get_primary_monitor()
        return screen.get_monitor_geometry(monitor)

    def _place_on_screen(self) -> None:
        geom = self._get_primary_monitor_geometry()
        margin = 50
        x = random.randint(geom.x + margin, geom.x + geom.width - self._size - margin)
        y = geom.y + geom.height - self._size - self._label_height - margin
        self.move(x, y)
        logger.debug("Window placed at (%d, %d)", x, y)

    # ------------------------------------------------------------------
    # Wandering
    # ------------------------------------------------------------------

    def _init_wander(self) -> None:
        monitors = self._get_monitor_geometries()
        self._wander = WanderEngine(
            monitors=monitors,
            pet_size=self._size,
            pet_height=self._size + self._label_height,
            active=self._debug,
        )
        logger.debug("Monitors: %s", monitors)
        logger.debug("Active monitor: %d, mode: %s",
                      self._wander._active_idx,
                      "active" if self._debug else "calm")
        logger.debug("Bounds: x=[%.0f, %.0f] y=[%.0f, %.0f]",
                      self._wander.x_min, self._wander.y_min,
                      self._wander.x_max, self._wander.y_max)
        win_x, win_y = self.get_position()
        self._wander.x = float(win_x)
        self._wander.y = float(win_y)
        # Snap to ground so we don't start floating
        self._wander.y = self._wander.y_max
        self.move(int(self._wander.x), int(self._wander.y))

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _start_timers(self) -> None:
        self._frame_timer_id = GLib.timeout_add(FRAME_INTERVAL_MS, self._on_frame_tick)

    def _stop_timers(self) -> None:
        if self._frame_timer_id is not None:
            GLib.source_remove(self._frame_timer_id)
            self._frame_timer_id = None

    def _on_frame_tick(self) -> bool:
        prev_state = self.character.state
        self.character.tick()

        # If a non-looping animation just finished (state changed),
        # clear the manual override so the bridge can take over again.
        if self._manual_override and prev_state != self.character.state:
            if not self.character.is_busy:
                self._manual_override = False
                logger.debug("Manual override cleared (animation finished)")

        # Clear social fight when attack -> celebrating transition happens
        if prev_state == "attack" and self.character.state == "celebrating":
            if self._social:
                self._social.clear_fight()

        # Detect doubling finished → spawn clone
        if (prev_state == "doubling"
                and self.character.state == "clone_frozen"
                and self._clone_window is None):
            self._spawn_clone()

        # Update pendulum swing during drag (keeps swinging when mouse stops)
        if self._drag_active:
            spring = -self._drag_swing * 0.05
            damping = -self._drag_swing_vel * 0.25
            self._drag_swing_vel += spring + damping
            self._drag_swing += self._drag_swing_vel
            swing = self._drag_swing
            speed = abs(swing)
            if speed < 0.2:
                move = "drag"
            elif swing < 0:
                if speed < 0.6:
                    move = "drag_left_slow"
                elif speed < 1.5:
                    move = "drag_left_fast"
                else:
                    move = "drag_left_vfast"
            else:
                if speed < 0.6:
                    move = "drag_right_slow"
                else:
                    move = "drag_right_fast"
            self.character.set_movement(move, -1)

        # Social engine: write position every N frames
        if self._social and self._wander is not None:
            move_name = {
                Move.SIT: "sit", Move.WALK_GROUND: "walk",
                Move.WALK_TOP: "walk", Move.CLIMB_LEFT: "climb",
                Move.CLIMB_RIGHT: "climb", Move.FALL: "fall",
                Move.THROW: "fall",
            }.get(self._wander.move_state, "")
            self._social.write_position(
                self._wander.x, self._wander.y,
                self._wander.direction, self.character.state,
                move_name, self._wander._active_idx,
            )

        # Move unless dragging, wander disabled, or character is busy
        if (self._wander_enabled
                and not self._drag_active
                and not self._clone_falling
                and not self.character.is_busy
                and self._wander is not None):
            new_x, new_y = self._wander.tick(self.character.state)

            # Social engine: get directive for social behaviors
            social_directive = None
            self._last_social_directive = None
            if self._social and self.character.state == "idle":
                move_name = {
                    Move.SIT: "sit", Move.WALK_GROUND: "walk",
                    Move.WALK_TOP: "walk",
                }.get(self._wander.move_state, "")
                social_directive = self._social.tick(
                    self._wander.x, self._wander.y,
                    self._wander.direction, self.character.state,
                    self._wander._active_idx, move_name,
                )
                # Handle fight directives
                if social_directive.fight_role == "attacker":
                    self._manual_override = True
                    # Face toward the defender
                    if social_directive.fight_peer_x > self._wander.x:
                        self._wander.direction = 1
                    else:
                        self._wander.direction = -1
                    self.character.set_state("attack")
                elif social_directive.fight_role == "defender":
                    # Face toward the attacker first (see the hit coming)
                    if social_directive.fight_peer_x > self._wander.x:
                        self._wander.direction = 1
                        throw_dir = -1
                    else:
                        self._wander.direction = -1
                        throw_dir = 1
                    # Compute throw to clear proximity zone
                    from social_engine import SocialEngine
                    clear_dist = SocialEngine.PROXIMITY_FIGHT * self._size * 1.3
                    throw_vy = -2.5
                    air_frames = 2 * abs(throw_vy) / WanderEngine.THROW_GRAVITY
                    throw_vx = clear_dist / max(air_frames, 1) * throw_dir
                    # Delayed throw — face attacker briefly, then get shoved
                    self._pending_throw = (throw_vx, throw_vy)
                    GLib.timeout_add(250, self._on_fight_throw_start)

            # Check if wander wants to trigger a character animation
            # Only apply during idle — don't override bridge states like attention
            if self._wander.pending_anim:
                anim = self._wander.pending_anim
                self._wander.pending_anim = None
                if self.character.state == "idle":
                    if anim == "clone_kill":
                        if self._clone_window is None:
                            self._manual_override = True
                            self.character.set_state("doubling")
                    else:
                        self.character.set_state(anim)

            # Store directive for facing override in movement sync
            self._last_social_directive = social_directive

            # Social: pass flags to wander engine
            if social_directive and social_directive.block_sit:
                self._wander._social_block_sit = True
            else:
                self._wander._social_block_sit = False
            # Peer very close = almost overlapping (half a sprite width)
            if social_directive:
                self._wander._social_peer_nearby = social_directive.nearest_peer_dist < self._size * 0.5
            else:
                self._wander._social_peer_nearby = False

            # Shift sprite inside the window to hug screen edges
            # Window stays put, character moves within it
            ms = self._wander.move_state
            if ms == Move.CLIMB_LEFT:
                self._draw_offset_x = -int(self._size * 0.50)
                self._draw_offset_y = 0
                self._label_on_top = True
            elif ms == Move.CLIMB_RIGHT:
                self._draw_offset_x = int(self._size * 0.50)
                self._draw_offset_y = 0
                self._label_on_top = True
            elif ms == Move.WALK_TOP:
                self._draw_offset_x = 0
                self._draw_offset_y = -int(self._size * 0.40)
                self._label_on_top = False
            else:
                self._draw_offset_x = 0
                self._draw_offset_y = 0
                self._label_on_top = True
            self.move(new_x, new_y)

        # Sync movement state to character (for sprite selection)
        # Skip during drag — drag sprites are set by _on_motion
        if self._wander is not None and not self._drag_active and not self._clone_falling:
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
            }
            move_name = move_map.get(self._wander.move_state, "")
            # Climb sprites face left; face toward the wall
            if self._wander.move_state == Move.CLIMB_LEFT:
                facing = -1
            elif self._wander.move_state == Move.CLIMB_RIGHT:
                facing = 1
            else:
                facing = self._wander.direction

            # Social: override facing toward peer when sitting
            if (self._social and move_name == "sit"
                    and self._last_social_directive
                    and self._last_social_directive.face_toward is not None):
                facing = self._last_social_directive.face_toward

            self.character.set_movement(move_name, facing)

        self._drawing_area.queue_draw()
        return True

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
        if new_state and new_state != self.character.state:
            logger.debug("Bridge callback: %s -> %s", self.character.state, new_state)
            # "doubling" triggers clone-kill — lock out bridge until animation finishes
            if new_state == "doubling" and self._clone_window is None:
                self._manual_override = True
            self.character.set_state(new_state)
        return False

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_draw(self, widget: Gtk.DrawingArea, ctx: cairo.Context) -> bool:
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)

        width = widget.get_allocated_width()

        # Label on top: sprite shifts down; label on bottom: sprite stays at 0
        sprite_y = self._label_height if self._label_on_top else 0

        # Draw sprite (shifted to hug screen edges + label offset)
        ctx.save()
        ctx.translate(self._draw_offset_x, self._draw_offset_y + sprite_y)
        self.character.draw(ctx, width, self._size)
        ctx.restore()

        # Draw project name label — positioned relative to sprite's draw offsets
        if self._project_name and self._label_height > 0:
            ctx.save()
            ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            ctx.set_font_size(11)
            extents = ctx.text_extents(self._project_name)

            # Follow sprite x-offset partially (stay near sprite, slightly toward center)
            label_x_shift = self._draw_offset_x * 0.3
            text_x = (width - extents.width) / 2 - extents.x_bearing + label_x_shift

            if self._label_on_top:
                text_y = sprite_y - 5
            else:
                # Just below the sprite's visual bottom
                text_y = self._draw_offset_y + self._size + 6

            # Dark outline for readability on any background
            ctx.set_source_rgba(0, 0, 0, 0.8)
            for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                ctx.move_to(text_x + dx, text_y + dy)
                ctx.show_text(self._project_name)

            # White text
            ctx.set_source_rgba(1, 1, 1, 0.95)
            ctx.move_to(text_x, text_y)
            ctx.show_text(self._project_name)
            ctx.restore()

        return True

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _on_button_press(self, widget: Gtk.Window, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self._drag_active = True
            self._drag_offset_x = event.x_root
            self._drag_offset_y = event.y_root
            win_x, win_y = self.get_position()
            self._drag_offset_x -= win_x
            self._drag_offset_y -= win_y
            self._drag_prev_x = event.x_root
            self._drag_prev_y = event.y_root
            self._drag_vel_x = 0.0
            self._drag_vel_y = 0.0
            self._drag_swing = 0.0
            self._drag_swing_vel = 0.0
            self._draw_offset_x = 0
            self._draw_offset_y = 0
            self.character.set_movement("drag", -1)
            return True
        elif event.button == 3:
            self._show_context_menu(event)
            return True
        return False

    def _on_button_release(self, widget: Gtk.Window, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self._drag_active = False
            if self._wander is not None:
                win_x, win_y = self.get_position()
                self._wander.x = float(win_x)
                self._wander.y = float(win_y)
                # Detect monitor switch on drop
                self._wander.set_active_monitor_at(win_x, win_y)

                # On the ground already?
                if self._wander.y >= self._wander.y_max - 5:
                    self._wander.y = self._wander.y_max
                    self._wander._start_sit()
                else:
                    # Throw or drop based on release velocity
                    speed = (self._drag_vel_x ** 2 + self._drag_vel_y ** 2) ** 0.5
                    if speed > 0.3:
                        # Scale up velocity for satisfying throw feel
                        self._wander._start_throw(
                            self._drag_vel_x * 1.0,
                            self._drag_vel_y * 1.0,
                        )
                    else:
                        self._wander._start_fall()
            return True
        return False

    def _on_motion(self, widget: Gtk.Window, event: Gdk.EventMotion) -> bool:
        if self._drag_active:
            new_x = int(event.x_root - self._drag_offset_x)
            new_y = int(event.y_root - self._drag_offset_y)
            self.move(new_x, new_y)

            # Track real velocity for throw detection
            dx = event.x_root - self._drag_prev_x
            dy = event.y_root - self._drag_prev_y
            self._drag_prev_x = event.x_root
            self._drag_prev_y = event.y_root
            self._drag_vel_x = self._drag_vel_x * 0.3 + dx * 0.7
            self._drag_vel_y = self._drag_vel_y * 0.3 + dy * 0.7
            push = dx * 0.01                         # mouse drags the swing
            spring = -self._drag_swing * 0.025       # spring pulls back to center @60fps
            damping = -self._drag_swing_vel * 0.06   # friction @60fps
            self._drag_swing_vel += push + spring + damping
            self._drag_swing += self._drag_swing_vel

            swing = self._drag_swing
            speed = abs(swing)
            if speed < 0.2:
                move = "drag"
            elif swing < 0:  # swinging left
                if speed < 0.6:
                    move = "drag_left_slow"
                elif speed < 1.5:
                    move = "drag_left_fast"
                else:
                    move = "drag_left_vfast"
            else:  # swinging right
                if speed < 0.6:
                    move = "drag_right_slow"
                else:
                    move = "drag_right_fast"
            self.character.set_movement(move, -1)
            return True
        return False

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()

        # Project name header (non-clickable)
        if self._project_name:
            name_item = Gtk.MenuItem(label=self._project_name)
            name_item.set_sensitive(False)
            menu.append(name_item)
            menu.append(Gtk.SeparatorMenuItem())

        # Auto mode — follow bridge
        auto_item = Gtk.CheckMenuItem(label="Auto (follow Claude)")
        auto_item.set_active(not self._manual_override)
        auto_item.connect("toggled", self._on_menu_auto)
        menu.append(auto_item)

        # Wander toggle
        wander_item = Gtk.CheckMenuItem(label="Wander")
        wander_item.set_active(self._wander_enabled)
        wander_item.connect("toggled", self._on_menu_toggle_wander)
        menu.append(wander_item)

        # Scale submenu
        scale_item = Gtk.MenuItem(label="Scale")
        scale_sub = Gtk.Menu()
        current_scale = self._size / SPRITE_BASE
        group = None
        for s in SCALE_OPTIONS:
            label = f"{s:.1f}x"
            if s == current_scale:
                label += " *"
            radio = Gtk.RadioMenuItem(label=label, group=group)
            group = radio
            radio.set_active(abs(s - current_scale) < 0.01)
            radio.connect("toggled", self._on_menu_scale, s)
            scale_sub.append(radio)
        scale_item.set_submenu(scale_sub)
        menu.append(scale_item)

        # Mascot submenu (if sprites_dir is set and has multiple mascots)
        if self._sprites_dir:
            mascots = self._list_mascots()
            if len(mascots) > 1:
                mascot_item = Gtk.MenuItem(label="Mascot")
                mascot_sub = Gtk.Menu()
                group = None
                for name, path in mascots:
                    radio = Gtk.RadioMenuItem(label=name, group=group)
                    group = radio
                    radio.set_active(path == self._mascot_path)
                    radio.connect("toggled", self._on_menu_mascot, path)
                    mascot_sub.append(radio)
                mascot_item.set_submenu(mascot_sub)
                menu.append(mascot_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Movement actions
        kick_item = Gtk.MenuItem(label="Kick!")
        kick_item.connect("activate", self._on_menu_kick)
        menu.append(kick_item)

        jump_item = Gtk.MenuItem(label="Jump!")
        jump_item.connect("activate", self._on_menu_jump)
        menu.append(jump_item)

        clone_item = Gtk.MenuItem(label="Clone & Kill!")
        clone_item.connect("activate", self._on_menu_clone_kill)
        menu.append(clone_item)

        menu.append(Gtk.SeparatorMenuItem())

        for state_name in TEST_STATES:
            item = Gtk.MenuItem(label=state_name.capitalize())
            item.connect("activate", self._on_menu_set_state, state_name)
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_menu_quit)
        menu.append(quit_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_fight_throw_start(self) -> bool:
        """Start the throw after facing the attacker briefly."""
        if self._wander and hasattr(self, '_pending_throw'):
            vx, vy = self._pending_throw
            del self._pending_throw
            # Flip facing away from attacker (throw direction)
            self._wander.direction = 1 if vx > 0 else -1
            self._wander._start_throw(vx, vy)
            # Clear fight after throw lands
            GLib.timeout_add(2000, self._on_fight_defend_done)
        return False

    def _on_fight_defend_done(self) -> bool:
        """Clear fight state after defender throw lands."""
        if self._social:
            self._social.clear_fight()
        return False

    def _on_wander_anim_timeout(self) -> bool:
        self._wander_anim_timer_id = None
        if not self._manual_override:
            self.character.set_state("idle")
        return False

    def _on_menu_kick(self, widget: Gtk.MenuItem) -> None:
        if self._wander is not None:
            self._wander._start_kick()

    def _on_menu_jump(self, widget: Gtk.MenuItem) -> None:
        if self._wander is not None:
            self._wander._start_jump()

    def _on_menu_clone_kill(self, widget: Gtk.MenuItem) -> None:
        if self._clone_window is not None:
            return  # already running
        self._manual_override = True
        self.character.set_state("doubling")

    def _spawn_clone(self) -> None:
        """Spawn a clone window that 'kills' the original."""
        win_x, win_y = self.get_position()
        # Clone spawns behind the original and faces it
        facing = self._wander.direction if self._wander else -1
        clone_x = win_x - facing * (self._size // 2)  # behind = opposite of facing
        clone_facing = facing  # face toward original

        # Clone has no label — offset y so sprite aligns with main window's sprite
        clone_y = win_y + (self._label_height if self._label_on_top else 0)

        # Attack animation: stand, jump, kick, kick, stand victorious
        self._clone_window = CloneWindow(
            sprites=self.character._sprites,
            indices=[27, 28, 29],
            delay=300,
            size=self._size,
            x=clone_x,
            y=clone_y,
            facing=clone_facing,
            on_done=self._on_clone_done,
        )
        logger.debug("Clone spawned at (%d, %d)", clone_x, win_y)

    def _on_clone_done(self, clone_win: CloneWindow) -> None:
        """Clone finished its attack. Original dies in place, clone stays."""
        # Keep clone alive while original plays death animation
        self.character.set_state("stumble")
        # After death sprites finish (3 frames × 300ms = 900ms), swap
        GLib.timeout_add(900, self._on_clone_death_done)
        logger.debug("Clone attack done, original dying")

    def _on_clone_death_done(self) -> bool:
        """Original finished dying. Hide it, clone takes over."""
        if self._clone_window is None:
            return False
        clone_x, clone_y = self._clone_window.get_position()
        # Hide original, then seamlessly appear at clone spot
        self.hide()
        self._clone_window.destroy()
        self._clone_window = None
        self._clone_falling = False

        if self._wander:
            self._wander.x = float(clone_x)
            self._wander.y = float(clone_y)
        self.move(clone_x, clone_y)
        self.show()

        self._manual_override = False
        self.character.set_state("idle")
        logger.debug("Clone kill complete, moved to (%d, %d)", clone_x, clone_y)
        return False

    def _on_menu_auto(self, widget: Gtk.CheckMenuItem) -> None:
        self._manual_override = not widget.get_active()
        if not self._manual_override:
            # Immediately sync with bridge
            state = self.bridge.get_state()
            if state:
                self.character.set_state(state)

    def _on_menu_toggle_wander(self, widget: Gtk.CheckMenuItem) -> None:
        self._wander_enabled = widget.get_active()

    def _on_menu_scale(self, widget: Gtk.RadioMenuItem, scale: float) -> None:
        if not widget.get_active():
            return
        new_size = int(SPRITE_BASE * scale)
        if new_size == self._size:
            return
        win_x, win_y = self.get_position()
        self._size = new_size
        total_h = new_size + self._label_height
        self._drawing_area.set_size_request(new_size, total_h)
        # set_size_request on the window itself forces the resize even when non-resizable
        self.set_size_request(new_size, total_h)
        self._init_wander()
        self._wander.x = float(win_x)
        # Snap to ground after rescale (pet size changed so old y is wrong)
        self._wander.y = self._wander.y_max
        self.move(int(self._wander.x), int(self._wander.y))
        logger.debug("Scale changed to %.1fx (%dpx)", scale, new_size)

    def _list_mascots(self) -> list[tuple[str, str]]:
        """Return sorted list of (display_name, path) for mascots in sprites_dir."""
        import os
        result = []
        for entry in sorted(os.listdir(self._sprites_dir)):
            path = os.path.join(self._sprites_dir, entry)
            if os.path.isdir(path):
                result.append((entry.replace("_", " ").title(), path))
        return result

    def _on_menu_mascot(self, widget: Gtk.RadioMenuItem, path: str) -> None:
        if not widget.get_active() or path == self._mascot_path:
            return
        from sprite_character import SpriteCharacter
        new_char = SpriteCharacter(path)
        if not new_char._sprites:
            logger.warning("No sprites in %s, ignoring", path)
            return
        self._mascot_path = path
        self.character = new_char
        logger.info("Switched mascot to %s (%d sprites)", path, len(new_char._sprites))
        # Persist selection as default
        try:
            from main import load_config, save_config
            cfg = load_config()
            cfg["mascot"] = os.path.basename(path)
            save_config(cfg)
        except Exception:
            pass

    def _on_menu_set_state(self, widget: Gtk.MenuItem, state: str) -> None:
        self._manual_override = True
        self.character.set_state(state)

        # Cancel any pending menu timeout
        if self._menu_timeout_id is not None:
            GLib.source_remove(self._menu_timeout_id)
            self._menu_timeout_id = None

        # Looping states get an auto-return to idle after ~3 loops
        cfg = self.character._state_config.get(state, {})
        if cfg.get("loop", True):
            n_frames = cfg.get("frames") or len(cfg.get("sprites", [1]))
            duration_ms = cfg["delay"] * n_frames * 3
            self._menu_timeout_id = GLib.timeout_add(
                duration_ms, self._on_menu_timeout)

    def _on_menu_timeout(self) -> bool:
        """Return to idle after a menu-selected looping animation preview."""
        self._manual_override = False
        self.character.set_state("idle")
        self._menu_timeout_id = None
        return False

    def _on_menu_quit(self, widget: Gtk.MenuItem) -> None:
        self._cleanup()
        Gtk.main_quit()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self) -> None:
        self._stop_timers()
        if self._menu_timeout_id is not None:
            GLib.source_remove(self._menu_timeout_id)
            self._menu_timeout_id = None
        try:
            self.bridge.stop_watching()
        except Exception:
            logger.exception("Error stopping bridge")
        if self._social:
            self._social.cleanup()

    def _on_realize(self, widget: Gtk.Window) -> None:
        """Disable compositor shadow/border on this window."""
        try:
            xid = self.get_window().get_xid()
            subprocess.Popen(
                ["xprop", "-id", str(xid),
                 "-f", "_COMPTON_SHADOW", "32c",
                 "-set", "_COMPTON_SHADOW", "0"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.debug("Set _COMPTON_SHADOW=0 on xid %d", xid)
        except Exception:
            logger.debug("Could not set _COMPTON_SHADOW")

    def _on_destroy(self, widget: Gtk.Window) -> None:
        self._cleanup()
        Gtk.main_quit()
