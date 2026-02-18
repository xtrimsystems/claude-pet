# Claude Pet - Project Guide

Shimeji-style desktop pet for Claude Code. A transparent, always-on-top GTK3 window that reflects Claude Code's state through pixel art animations. Runs on X11 with picom compositor on Linux/i3.

## Architecture

4 Python files, no build system (runs directly with system python3):

- **main.py** - Entry point. Parses args (`--project-name`, `--pid-file`, `--state-file`, etc.), loads config from `~/.config/claude-pet/config.json`, resolves mascot path, creates `SpriteCharacter` + `ClaudeBridge` + `PetWindow`, starts GTK main loop. Per-project single-instance via PID files at `/tmp/claude-pet-{hash}.pid`.
- **pet_window.py** - The core. Contains `PetWindow` (GTK POPUP window), `WanderEngine` (movement AI), and `CloneWindow` (temporary overlay for clone-kill animation). Runs at 60fps via GLib timer.
- **sprite_character.py** - Loads shime*.png sprites from mascot directories. Defines two animation config dicts: `_state_config` (Claude states) and `_move_config` (movement animations). Handles frame advancement, looping, and state transitions.
- **claude_bridge.py** - Polls the state file (per-project: `/tmp/claude-pet-{hash}-state`) every 300ms for state changes. Has a 60-second idle timeout that auto-transitions to idle if no state change occurs. Valid states: idle, thinking, working, attention, celebrating, doubling.

## Animation System (sprite_character.py)

### Two config dicts drive all animations:

**`_state_config`** - State-override animations (thinking, working, celebrating, error, etc.). Triggered by Claude hooks or wander engine. Freeze movement and take priority over move animations.
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
- **`"loop": False`** - plays a **finite number of times** (controlled by `"loops"`, default 2), then auto-transitions to `"next"` state. Used for one-shot animations: celebrating, error, doubling, clone_dying.
- The `"loops"` default of 2 is set in `tick()` line 220: `cfg.get("loops", 2)`.

### Animation priority (in `_active_config()`):
1. If Claude state is NOT "idle" -> plays from `_state_config` (working, thinking, etc.)
2. If Claude state IS "idle" AND there's an active movement -> plays from `_move_config` (walk, climb, etc.)
3. If Claude state IS "idle" AND no movement -> plays static `_state_config["idle"]`

### Movement freezing:
When Claude state is working, thinking, error, attention, doubling, clone_frozen, or clone_dying, the `WanderEngine.tick()` returns current position without moving (line 197-200 of pet_window.py). The pet stays put while these animations play.

## State Triggering - Three Sources

### 1. Claude Code hooks (claude_bridge.py)
Hooks are configured in `~/.claude/settings.json` (global) and call `hooks/state-hook.sh` which reads JSON from stdin to extract `cwd`, derives a per-project hash, and writes to per-project state files (`/tmp/claude-pet-{hash}-state`). Bridge polls this file every 300ms.

Current hook mapping (in `~/.claude/settings.json`, installed by `hooks/install-hooks.sh`):
- **SessionStart** -> "idle" (pet resets when Claude session begins; auto-starts the pet if not running)
- **UserPromptSubmit** -> "thinking" (user sent a message, Claude is processing the prompt)
- **PreToolUse** -> "working" (tool is about to execute - the actual work)
- **PermissionRequest** -> "attention" (Claude needs permission approval)
- **Stop** -> "celebrating" (Claude finished - plays celebrate animation, then auto-transitions to idle)
- **PreCompact** -> "doubling" (Claude is compacting context - triggers clone-kill animation)
- **SessionEnd** -> "stop" (kills the pet for this project and cleans up state/PID files)

The typical flow: UserPromptSubmit(thinking) -> PreToolUse(working) -> PreToolUse(working) -> ... -> Stop(celebrating) -> idle.

Note: PostToolUse and PostToolUseFailure are intentionally not hooked — they fire rapidly between each tool call which caused distracting animation flickering.

- Bridge has a 60s idle timeout: if no state change for 60s, auto-transitions to idle.
- Bridge respects `_manual_override` flag - won't change state while user is controlling via menu.

### 2. Right-click context menu (pet_window.py `_on_menu_set_state`)
- Sets `_manual_override = True` so bridge won't interfere.
- For **looping** states (loop:True): sets a GLib timer for 3 full cycles, then returns to idle and clears override.
- For **non-looping** states (loop:False): the animation plays its `"loops"` count and auto-transitions via `tick()`. Override is cleared in `_on_frame_tick` when it detects the state changed and `is_busy` is False.

### 3. Wander engine random behaviors (pet_window.py `WanderEngine._pick_behavior`)
- During idle, the wander engine randomly picks behaviors using weighted probabilities.
- Besides movement (sit, walk, climb, kick, jump), it can also pick: **clone_kill, celebrating, error, thinking**.
- These are set as `pending_anim` on the wander engine, then picked up by `_on_frame_tick` and applied via `set_state()`.
- Weights differ between calm mode (default) and active mode (--debug flag):
  - Calm: sit=200, walk=50, climb=10, kick=6, jump=2, clone_kill=2, celebrating=3, error=2, thinking=5
  - Active: sit=50, walk=150, climb=40, kick=18, jump=7, clone_kill=5, celebrating=8, error=5, thinking=10

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
| 18-21 | Bad landing / hard landing / clone death |
| 22 | Jump (big jump sprite) |
| 23-25 | Ceiling walk |
| 37 | Kick (small jump / air kick sprite) |
| 38-41 | Error animation frames |
| 42-43 | Thinking animation / error bookend |
| 44-46 | Doubling (clone spawn) animation |
| 47-48 | Working animation (at laptop) |
| 49-50 | Celebrating animation |

## Clone-Kill Animation Sequence

1. `set_state("doubling")` -> plays sprites [44, 45, 46] once, transitions to "clone_frozen"
2. `_on_frame_tick` detects doubling->clone_frozen transition -> calls `_spawn_clone()`
3. `CloneWindow` spawns behind original, plays attack sprites [27, 28, 29], calls `_on_clone_done`
4. Original plays "clone_dying" [19, 18, 20], then after 900ms `_on_clone_death_done` swaps positions
5. Original teleports to clone position, clone window destroyed, state returns to idle

## Multi-Instance Support

Each Claude Code session spawns its own pet, identified by project folder:

- `state-hook.sh` reads `cwd` from hook stdin JSON, derives `project_name` (basename) and an 8-char MD5 hash of the full path
- Per-project files: `/tmp/claude-pet-{hash}-state` and `/tmp/claude-pet-{hash}.pid`
- `main.py` accepts `--project-name`, `--pid-file`, `--state-file` args
- `SessionEnd` hook kills the pet for that specific project
- `make stop` kills all pet instances (globs `/tmp/claude-pet*.pid`)

## Project Name Label

When `--project-name` is set, a floating label is drawn near the sprite via cairo:

- **LABEL_HEIGHT = 20** — extra window height for the label
- **Label on top** by default (sprite shifted down by `LABEL_HEIGHT`)
- **Label on bottom** when on the ceiling (`_label_on_top = False`)
- **Label follows sprite x-offset** at 30% intensity during wall climbs (stays near sprite, slightly toward center)
- White bold text with dark outline (4-corner shadow) for readability on any background
- `WanderEngine` uses separate `pet_size` (width) and `pet_height` (height) so the label height doesn't affect x-bounds
- Project name also shown as a disabled menu item at the top of the right-click context menu

## Key Technical Details

- **GTK POPUP window** - bypasses window manager (no tiling in i3). Uses `Gdk.WindowTypeHint.DOCK`.
- **60fps frame timer** - `FRAME_INTERVAL_MS = 1000 // 60 = 16ms`. Character `_TICK_MS` matches this.
- **Sprite fallback** - if a sprite index is missing, falls back to the lowest available sprite number (line 167-175 of sprite_character.py). This means animations work even if a mascot is missing some sprites.
- **Multi-monitor** - WanderEngine tracks active monitor, switches on drag-drop. Pet is constrained to one monitor at a time.
- **Config persistence** - mascot selection saved to `~/.config/claude-pet/config.json`.
- **Sprites skip tiny files** - PNGs under 500 bytes are skipped (assumed blank/transparent).
- **Picom shadow disabled** - uses xprop to set `_COMPTON_SHADOW=0` on the window.

## Running

```bash
make run          # foreground
make debug        # with debug logging (activates "active" wander mode)
make start        # background
make stop         # kill all pet instances
make test-states  # cycle through all states
make test-working # set a specific state
make install      # install hooks + launcher
make uninstall    # remove hooks
```

No Docker needed - this uses system python3 with python3-gi (PyGObject) and python3-gi-cairo.
