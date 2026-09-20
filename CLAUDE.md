# Claude Pet - Project Guide

Shimeji-style desktop pet for Claude Code. A transparent, click-through overlay that reflects Claude Code's state through pixel art animations. Native Wayland: GTK4 + wlr-layer-shell (gtk4-layer-shell), developed on Hyprland/Omarchy. One pet for the whole desktop, shared by every Claude Code session.

## Architecture

4 Python files, no build system (runs directly with system python3):

- **main.py** - Entry point. Re-execs itself with `libgtk4-layer-shell` in `LD_PRELOAD` (the library must load before libwayland-client, which a language binding can't guarantee — this is the documented approach), parses args (`--size`, `--mascot`, `--state-file`, `--pid-file`, `--debug`), loads config from `~/.config/claude-pet/config.json`, resolves the mascot, creates `SpriteCharacter` + `ClaudeBridge` + `Pet`, runs a GLib main loop. Single instance via `/tmp/claude-pet.pid` (the PID file is only removed by the process that owns it).
- **pet_window.py** - The core. `MonitorOverlay` (one full-output layer-shell surface per monitor, `overlay` layer, transparent, input region limited to the sprite), `SpriteArea` (a small `Gtk.DrawingArea` moved inside a `Gtk.Fixed`), `WanderEngine` (movement AI) and `Pet` (the controller: 60fps GLib timer, drag/throw gestures, right-click `Gtk.PopoverMenu`, clone-kill animation, bridge integration). Positions are global desktop coordinates; each overlay shows the sprite only if it touches its monitor, so dragging across monitors just works.
- **sprite_character.py** - Loads shime*.png sprites from mascot directories. Defines two animation config dicts: `_state_config` (Claude states) and `_move_config` (movement animations). Handles frame advancement, looping, and state transitions.
- **claude_bridge.py** - Polls the state file (`/tmp/claude-pet-state`) every 300ms for state changes. Has a 60-second idle timeout that auto-transitions to idle if no state change occurs. Valid states: idle, thinking, working, attention, celebrating, doubling.

## Animation System (sprite_character.py)

### Two config dicts drive all animations:

**`_state_config`** - State-override animations (thinking, working, celebrating, error, etc.). Triggered by Claude hooks, the menu, or the wander engine. Freeze movement and take priority over move animations.
**`_move_config`** - Movement animations (walk, sit, climb, kick, jump, fall, drag, etc.)

### Config format:
```python
{
    "sprites": [47, 48, 48, 48, 47],  # shime indices to play
    "delay": 600,                       # ms per frame
    "loop": True,                       # default True; False = finite plays
    "loops": 2,                         # only for loop:False; default 2; how many times to play
    "next": "idle",                     # only for loop:False; state to transition to after done
}
```

### Loop behavior:
- **`"loop": True`** (default if omitted) - loops **forever** until state changes externally. Used for ongoing states: idle, thinking, working, attention.
- **`"loop": False`** - plays a **finite number of times** (controlled by `"loops"`, default 2), then auto-transitions to `"next"` state. Used for one-shot animations: celebrating, error, doubling, stumble.
- The `"loops"` default of 2 is set in `tick()` line 220: `cfg.get("loops", 2)`.

### Animation priority (in `_active_config()`):
1. If Claude state is NOT "idle" -> plays from `_state_config` (working, thinking, etc.)
2. If Claude state IS "idle" AND there's an active movement -> plays from `_move_config` (walk, climb, etc.)
3. If Claude state IS "idle" AND no movement -> plays static `_state_config["idle"]`

### Movement freezing:
When Claude state is working, thinking, error, attention, doubling, clone_frozen, stumble, or attack, the `WanderEngine.tick()` returns current position without moving. The pet stays put while these animations play.

## State Triggering - Three Sources

### 1. Claude Code hooks (claude_bridge.py)
Hooks are configured in each Claude Code config dir's `settings.json` (`hooks/install-hooks.sh ~/.claude ~/.claude-work`) and call `hooks/state-hook.sh`, which reads the hook JSON from stdin for the `session_id`, keeps `/tmp/claude-pet-sessions/<session_id>` as the set of live sessions, starts the pet if it is not running, and writes the state to `/tmp/claude-pet-state`. Bridge polls this file every 300ms. All sessions (including subagents in other folders) feed the same pet — last writer wins.

Current hook mapping (installed by `hooks/install-hooks.sh`):
- **SessionStart** -> "idle" (registers the session; auto-starts the pet if not running)
- **UserPromptSubmit** -> "thinking" (user sent a message, Claude is processing the prompt)
- **PreToolUse** -> "working" (tool is about to execute - the actual work)
- **PermissionRequest** -> "attention" (Claude needs permission approval)
- **Stop** -> "celebrating" (Claude finished - plays celebrate animation, then auto-transitions to idle)
- **PreCompact** -> "doubling" (Claude is compacting context - triggers clone-kill animation)
- **SessionEnd** -> "stop" (unregisters the session; the pet is killed only when no sessions remain, or when no `claude` process exists at all — sessions that died without SessionEnd)

The typical flow: UserPromptSubmit(thinking) -> PreToolUse(working) -> PreToolUse(working) -> ... -> Stop(celebrating) -> idle.

Note: PostToolUse and PostToolUseFailure are intentionally not hooked — they fire rapidly between each tool call which caused distracting animation flickering.

- Bridge has a 60s idle timeout: if no state change for 60s, auto-transitions to idle.
- Bridge respects `_manual_override` flag - won't change state while user is controlling via menu.

### 2. Right-click context menu (pet_window.py `_on_menu_set_state`, a `Gtk.PopoverMenu` over `Gio.Menu` + `Gio.SimpleActionGroup` "pet")
- Sets `_manual_override = True` so bridge won't interfere.
- For **looping** states (loop:True): sets a GLib timer for 3 full cycles, then returns to idle and clears override.
- For **non-looping** states (loop:False): the animation plays its `"loops"` count and auto-transitions via `tick()`. Override is cleared in `_on_frame_tick` when it detects the state changed and `is_busy` is False.

### 3. Wander engine random behaviors (pet_window.py `WanderEngine._pick_behavior`)
- During idle, the wander engine randomly picks behaviors using weighted probabilities.
- Besides movement (sit, walk, climb, kick, jump), it can also pick: **clone_kill, error**.
- These are set as `pending_anim` on the wander engine, then picked up by `_on_frame_tick` and applied via `set_state()`.
- Weights differ between calm mode (default) and active mode (--debug flag):
  - Calm: sit=200, walk=50, climb=10, kick=6, jump=2, clone_kill=2, error=2
  - Active: sit=50, walk=150, climb=40, kick=18, jump=7, clone_kill=5, error=5
- **Stumble**: Random chance per frame while walking on the ground. Base ~0.03% per frame (~2%/s), boosted to ~0.3% per frame (~16%/s) when another pet is very close (within half a sprite width). Interrupts the walk mid-stride with the stumble animation [19, 18, 20], then returns to idle.

## Sprite Mapping (Deadpool mascot, current)

| Sprites | Purpose |
|---------|---------|
| 1-3 | Walking frames |
| 4 | Falling |
| 5 | Drag (neutral) |
| 6-10 | Drag directions (left slow/fast/vfast, right slow/fast) |
| 11 | Sitting |
| 12-14 | Climbing |
| 15 | Action pose (used in attention) |
| 1 | Good landing (standing pose after kick/jump) |
| 18, 20-21 | Bad landing / hard landing / clone death |
| 22 | Jump (big jump sprite) |
| 23-25 | Ceiling walk |
| 37 | Kick (small jump / air kick sprite) |
| 38-41 | Error animation frames |
| 42-43 | Thinking animation / error bookend |
| 44-46 | Doubling (clone spawn) animation |
| 47-48 | Working animation (at laptop) |
| 27-29 | Attack animation (used in clone-kill) |
| 49-50 | Celebrating animation |

## Clone-Kill Animation Sequence

1. `set_state("doubling")` -> plays sprites [44, 45, 46] once, transitions to "clone_frozen"
2. `_on_frame_tick` detects doubling->clone_frozen transition -> calls `_spawn_clone()`
3. A clone sprite (`Pet._clone`, drawn by each overlay's second `SpriteArea`) appears behind the original, plays attack sprites [27, 28, 29] on a 300ms timer, then `_on_clone_done`
4. Original plays "stumble" [19, 18, 20], then after 900ms `_on_clone_death_done` swaps positions
5. Original teleports to the clone position, clone sprite hidden, state returns to idle

## Key Technical Details

- **Layer-shell overlays** - one `Gtk.Window` per monitor, anchored to all four edges with exclusive zone -1 (covers the whole output, including bar areas), layer `overlay` (above fullscreen windows), keyboard mode `none`, namespace `claude-pet` (visible in `hyprctl layers`). Transparent via CSS `window.claude-pet { background-color: transparent; }`. `Gdk.Surface.set_input_region` is updated whenever a sprite moves so only the sprite rectangles take clicks.
- **Drawing cost** - only the 128x128 `SpriteArea` nodes are redrawn (`queue_draw` on the sprite, not the window), and only when position, frame or state changed; the timer itself runs at 60fps. Idle CPU ~1%.
- **Gestures** - `Gtk.GestureDrag` (button 1) for drag/throw with the implicit grab, so the drag keeps tracking when the pointer leaves the sprite or the monitor; `Gtk.GestureClick` (button 3) for the menu.
- **Monitor hotplug** - `Gdk.Display.get_monitors()` "items-changed" rebuilds the overlays and the wander bounds.
- **60fps frame timer** - `FRAME_INTERVAL_MS = 1000 // 60 = 16ms`. Character `_TICK_MS` matches this.
- **Sprite fallback** - if a sprite index is missing, falls back to the lowest available sprite number (line 167-175 of sprite_character.py). This means animations work even if a mascot is missing some sprites.
- **Multi-monitor** - WanderEngine tracks the active monitor (global coordinates), switches on drag-drop. Pet is constrained to one monitor at a time.
- **Config persistence** - mascot selection saved to `~/.config/claude-pet/config.json`.
- **Sprites skip tiny files** - PNGs under 500 bytes are skipped (assumed blank/transparent).

## Running

```bash
make run          # foreground
make debug        # with debug logging (activates "active" wander mode)
make start        # background
make stop         # kill the pet
make test-states  # cycle through all states
make test-working # set a specific state
make install      # install hooks (into ~/.claude and ~/.claude-work)
make uninstall    # remove hooks
```

No Docker needed - this uses system python3 with python3-gi (PyGObject) and python3-gi-cairo.

## Documentation Policy

When making changes that affect behavior, flags, architecture, or features, **always update both CLAUDE.md and README.md** in the same change. Keep them in sync with the code.
