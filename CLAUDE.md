# Claude Pet - Project Guide

Shimeji-style desktop pet for Claude Code. A transparent, click-through overlay that reflects Claude Code's state through pixel art animations. Native Wayland: GTK4 + wlr-layer-shell (gtk4-layer-shell), developed on Hyprland/Omarchy. One pet for the whole desktop, shared by every Claude Code session.

## Architecture

4 Python files for the pet plus the sprite generator in `tools/`, no build system (runs directly with system python3):

- **main.py** - Entry point. Re-execs itself with `libgtk4-layer-shell` in `LD_PRELOAD` (the library must load before libwayland-client, which a language binding can't guarantee — this is the documented approach), parses args (`--size`, `--mascot`, `--monitor`, `--state-file`, `--pid-file`, `--debug`), loads config from `~/.config/claude-pet/config.json`, resolves the mascot, creates `SpriteCharacter` + `ClaudeBridge` + `Pet`, runs a GLib main loop. Single instance via `/tmp/claude-pet.pid` (the PID file is only removed by the process that owns it).
- **pet_window.py** - The core. `MonitorOverlay` (one full-output layer-shell surface per monitor, `overlay` layer, transparent, input region limited to the sprite), `SpriteArea` (a small `Gtk.DrawingArea` moved inside a `Gtk.Fixed`; it grows upward while a frame is taller than wide, using `character.overhang()`, so the feet stay put), `WanderEngine` (movement AI), `HyprlandCursor` (asks Hyprland's socket where the pointer is) and `Pet` (the controller: 60fps GLib timer, drag/throw gestures, right-click `Gtk.PopoverMenu`, clone-kill animation, bridge integration, eyes following the cursor, seasonal hats). Positions are global desktop coordinates; each overlay shows the sprite only if it touches its monitor, so dragging across monitors just works.
- **sprite_character.py** - Loads every `shime<N>.png` in the mascot folder. Defines two animation config dicts: `_state_config` (Claude states) and `_move_config` (movement animations), then merges the mascot's optional `animations.json` over them. Handles frame advancement (fixed `delay` or per-frame `durations`), looping, and state transitions. `supports(name)` tells the pet which extra animations a mascot has. It also swaps in a look frame for the current gaze (`set_gaze`) and paints the worn hat (`set_hat`) over the head; `overhang()` includes the room the hat needs above the frame, and `draw_sprite()` is shared with the clone.
- **tools/** - The Deadpool sprite generator, run with `make sprites` (cairo only, system python3):
  - `build_sprites.py` - entry point. Collects every generated animation, numbers new frames from shime54 up (frames identical to an original sprite reuse its index; identical frames are shared), writes the PNGs, deletes stale generated ones, and writes `sprites/deadpool/animations.json` (plus the hat images in `sprites/deadpool/hats/` and front layers in `sprites/deadpool/front/`). A frame can be `(surface, ms, front)`: `front` is a layer of props drawn over the hat at runtime. Fails if a frame would be under 500 bytes (the loader skips those as blank). It also makes a right-facing twin of every frame with text: generated frames are drawn a second time with the text pre-mirrored (`mirror_text`), and the pack's own text is fixed by hand (`pack_text_twins`: the "?" of shime43 and the "HEY!" of shime51 flip in place; shime52/53 tilt the sign opposite ways, so each takes the other's sign, flipped).
  - `sprite_kit.py` - shared helpers: `outlined_text` (draws mirrored while `mirror_text(True)` is on), eye detection (`eye_blobs`), eyelids (`close_eyes`), moving pupils (`move_eyes`), bigger or smaller eyes (`resize_eyes`), another pose's eyes (`eyes_from`), confetti removal (`without_confetti`), crisp lean (`shear`), turning around (`mirrored`), outlined shapes (`silhouette`, `filled`), smoke `cloud`, `zzz`, `nose_bubble`, stars, sparkles, the red `exclamation` (same red as the pack's "?").
  - `draw_scooter.py` - the sitting pose (shime11) on a mint scooter with an arm on the handlebar.
  - `draw_finger_gun.py` - finger gun from the pack's own pixels: shime11 + shime15 (identical to shime26; 15's head sits 2px left / 1px lower). Lids close, gun arm rotates up from the hip, flag slides out of the barrel, heart bubble pops and beats.
  - `draw_hats.py` - the hats (`santa`, `pumpkin`) and `HeadFinder`, which finds where the hat goes in every frame: the near eye's socket gives the position, the line between the two eyes gives the tilt (or a mirrored head, as in the fourth wall), and a ray up to the edge of the head fixes the height. Closed eyes fall back to a dark socket ringed by suit red, or to the nearest frame of the same animation. No hat where it would hide a prop (the box, teleport smoke) or stick out sideways (ceiling walk).
  - `draw_extras.py` - nap, laptop doze, fly gag (the fly is also a front layer, so a hat never hides it), vibing (grey headphones, a walkman on the belt with a cable up to the near ear cup, `shear` sway), unicorn (rider is shime5 with the back foot erased and the front leg pasted back over the unicorn), head pop, teleport, and the look frames for eyes that follow the cursor (`looks`: shime1 and shime11 with `move_eyes` in 8 directions).
  - `draw_gags.py` - fourth wall (kick shime37, glass crack, then shime1 `mirrored` around his feet so he turns his back on the crack and whistles, with puckered lips shaded into the mask), zen (floating with closed eyes, glow), disco (ball, club lights only on his pixels, `shear` sway), chimichanga (it appears at his belt with sparkles, then shime50's hands at his cheeks hold it while he takes three bites, NOM, crumbs, GULP, BURP), and the neon signs `sign_effort` / `sign_nailed` drawn over shime51-53 after erasing their "HEY!" sign.
  - `draw_travel.py` - balloon (a plain blue balloon; `balloon_grab`: it drifts in from behind him, small and far away, growing as it comes closer, so it never crosses the frame edge, and the steel hook on its string catches the back of his belt, drawn behind him; he looks scared: tiny eyes with a "!", then tiny eyes looking down, trembling 1px, with a sweat drop for the whole rise; then the `balloon` move and `balloon_pop`, where the hook goes with the balloon) and box sneak (`box_on`, the `box` move, `box_peek`, `box_off`; the exit uses shime50's raised arms with its confetti removed). Some of these frames are taller than 128px (balloon 228, box on/off 248): the extra height sits above his head.
  - Style rule: Deadpool himself is only ever built from the pack's pixels (cut, shift, rotate, recolor); code draws props and effects only, in the pack's flat style (black ~2.5px outlines, suit red `#6C0000`).
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
    "durations": [600, 300, ...],       # optional instead of "delay": ms for each frame (used by animations.json)
    "loop": True,                       # default True; False = finite plays
    "loops": 2,                         # only for loop:False; default 2; how many times to play
    "next": "idle",                     # only for loop:False; state to transition to after done
}
```

### Extra animations (`<mascot>/animations.json`):
`{"states": {name: config}, "moves": {name: config}, "looks": {pose: {"eyes": [x, y], "sprites": [9 frames]}}, "right_facing": {sprite: twin}, "hats": {name: [origin_x, origin_y]}, "heads": {sprite: [x, y, angle, flipped]}, "fronts": {sprite: "front/shime<N>.png"}}`. `looks` are the gaze frames, row by row from up-left to down-right; `heads` say where the hat sits in each frame; `fronts` are props painted again after the hat so it can't hide them (the fly). States and moves are merged over the built-in dicts. The pet mirrors every sprite when it faces right, which would show text backwards, so `draw()` swaps a sprite for its `right_facing` twin (text pre-mirrored) when facing right. Generated for Deadpool by `make sprites`; never edit it by hand. A mascot without the file (e.g. a standard Shimeji pack) simply has none of the extras: they are left out of the random pool and the menu.

### Loop behavior:
- **`"loop": True`** (default if omitted) - loops **forever** until state changes externally. Used for ongoing states: idle, thinking, working, attention.
- **`"loop": False`** - plays a **finite number of times** (controlled by `"loops"`, default 2), then auto-transitions to `"next"` state. Used for one-shot animations: celebrating, error, doubling, stumble.
- The `"loops"` default of 2 is set in `tick()` line 220: `cfg.get("loops", 2)`.

### Animation priority (in `_active_config()`):
1. If Claude state is NOT "idle" -> plays from `_state_config` (working, thinking, etc.)
2. If Claude state IS "idle" AND there's an active movement -> plays from `_move_config` (walk, climb, etc.)
3. If Claude state IS "idle" AND no movement -> plays static `_state_config["idle"]`

### Movement freezing:
In any state other than idle, `WanderEngine.tick()` returns the current position without moving. The pet stays put while these animations play.

## State Triggering - Three Sources

### 1. Claude Code hooks (claude_bridge.py)
Hooks are configured in each Claude Code config dir's `settings.json` (`hooks/install-hooks.sh ~/.claude ~/.claude-work`) and call `hooks/state-hook.sh`, which reads the hook JSON from stdin for the `session_id`, keeps `/tmp/claude-pet-sessions/<session_id>` as the set of live sessions, starts the pet if it is not running, and writes the state to `/tmp/claude-pet-state`. Bridge polls this file every 300ms. All sessions (including subagents in other folders) feed the same pet — last writer wins.

Current hook mapping (installed by `hooks/install-hooks.sh`):
- **SessionStart** -> "idle" (registers the session; auto-starts the pet if not running, on the monitor that is focused at that moment — `hyprctl monitors` — so it appears next to the terminal that started it; `--monitor`/config `"monitor"` override)
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
- Items: Kick, Jump, Scooter/Unicorn/Balloon/Box sneak (`pet.ride`, `TRIP_MENU`), Teleport, Clone & Kill, and a "Tricks" submenu (`TRICKS`: finger gun, fly, vibing, head pop, fourth wall, zen, disco, chimichanga, nap, laptop doze, and the two signs for testing) that goes through `pet.state`. A "Hat" submenu (`pet.hat`) picks Seasonal, None or a hat by name. Extras only appear when the mascot `supports()` them.
- The menu always works, whatever is playing. Moves (kick, jump, rides) go through `_start_menu_move`: it drops the current state to idle (cutting a nap, a trick or a Claude state), sets `_manual_override`, and lets the wander engine run even when Wander is off. `_finish_menu_move` ends it once he sits again: override cleared, then `_resume_claude_state()` (the bridge's current thinking/working/attention, else idle).
- Sets `_manual_override = True` so bridge won't interfere.
- For **looping** states (loop:True): sets a GLib timer for 3 full cycles, then returns to idle and clears override.
- For **non-looping** states (loop:False): the animation plays its `"loops"` count and auto-transitions via `tick()`. Override is cleared in `_on_frame_tick` when it detects the state changed and `is_busy` is False.

### 3. Wander engine random behaviors (pet_window.py `WanderEngine._pick_behavior`)
- During idle, the wander engine randomly picks behaviors using weighted probabilities.
- Besides movement (sit, walk, climb, kick, jump, and the trips in `TRIPS`: scooter, unicorn, balloon, box), it can also pick state tricks: **clone_kill, error, finger_gun, fly_gag, vibing, head_pop, fourth_wall, zen, disco, chimichanga, teleport** (`STATE_BEHAVIORS` maps teleport to `teleport_out`).
- These are set as `pending_anim` on the wander engine, then picked up by `_on_frame_tick` and applied via `set_state()`.
- Optional behaviors (`OPTIONAL_BEHAVIORS`) are only picked when the mascot supports them: `Pet._sync_extras()` fills `WanderEngine.extras` at start and on mascot switch.
- Weights differ between calm mode (default) and active mode (--debug flag):
  - Calm: sit=120, walk=80, climb=20, kick=10, jump=4, scooter=6, unicorn=4, balloon=3, box=3, teleport=4, finger_gun=4, fly_gag=3, vibing=4, head_pop=3, fourth_wall=3, zen=3, disco=3, chimichanga=3, clone_kill=3, error=3
  - Active: sit=50, walk=150, climb=40, kick=18, jump=7, scooter=12, unicorn=8, balloon=5, box=5, teleport=8, finger_gun=6, fly_gag=5, vibing=6, head_pop=5, fourth_wall=5, zen=5, disco=5, chimichanga=5, clone_kill=5, error=5
- **Rides** (`Move.SCOOTER`, `Move.UNICORN`; `_start_ride`/`_do_ride`): ride along the ground toward the farther screen edge, speeding up from 1 to 4.5 px/frame (`RIDE_*`) and braking near the edge, then turn around and sit.
- **Balloon** (`Move.BALLOON`, `_start_balloon`/`_do_balloon`): `balloon_grab` plays on the ground (the balloon floats in from behind him and hooks his belt), then he rises (up to 1.6 px/frame, drifting forward) to a random height: at least `BALLOON_MIN_RISE` (45%) of the screen, at most where the balloon still fits on screen (`balloon_overhang`, set by `_sync_extras` from the frames' extra height). There `balloon_pop` plays and he falls (`_start_fall`), which always ends in the hard landing.
- **Box sneak** (`Move.BOX`, `_start_box`/`_do_box`): `box_on` (the box drops on him), then he sneaks toward the open side at 0.7 px/frame for 8-15s (`BOX_TRIP`), crouching to look around (`box_peek`) every 2.5-5.5s (`BOX_PEEK_EVERY`), and ends with `box_off` (the box flies up, arms raised) at the timer or an edge.
- **Teleport**: `teleport_out` (belt sparks, smoke, vanish) -> `Pet._on_animation_finished` calls `WanderEngine.teleport()` (a random ground spot at least a quarter of the monitor away) -> `teleport_in` (smoke clears, he's there) -> idle.
- **One-shot tricks** (~3-10s each, then idle): finger_gun (eyes close, gun from the hip, flag, heart), fly_gag (eyes follow a fly, he aims, the flag pops, the fly lands on his head), vibing (headphones and a walkman on his belt, sway, plays its cycle 3 times), head_pop (head pops off, spins, lands, dizzy stars), fourth_wall (kicks the screen, it cracks, he turns his back on it and whistles), zen (floats, glowing), disco (disco ball, club lights, sway), chimichanga (eats one in three bites, then burps).
- **Eyes follow the cursor**: while he stands idle or sits (`LOOKING_MOVES`), `Pet._follow_cursor` asks Hyprland for the pointer every `GAZE_POLL_S` (0.15s, one socket request, ~0.1ms) and picks one of 8 look frames; straight ahead when the pointer is on him (`GAZE_DEAD_ZONE`) or has not moved for `GAZE_RESET_S` (4s). Off outside Hyprland.
- **Hats**: `HAT_SEASONS` (October `pumpkin`, December `santa`); config `"hat"` is `seasonal` (default), `none` or a hat name, set from the menu. The season is checked every hour. The clone wears the hat too.
- **Signs** (Claude only, never random; `Pet._with_sign`): a new prompt ("thinking" while not already busy) shows `sign_effort` ("MAXIMUM EFFORT!") at most once per `EFFORT_SIGN_COOLDOWN_S` (10 min); thinking/working writes are ignored while it plays, then `_resume_claude_state()`. A finished turn ("celebrating") shows `sign_nailed` ("NAILED IT!") instead of the confetti with `NAILED_IT_CHANCE` (1/3).
- **Nap** (not in the random pool): `Pet._maybe_fall_asleep` starts `nap_start` -> `napping` (loop) after `NAP_AFTER_IDLE_S` (5 min) without activity while he sits on the ground. He also wakes by himself after `NAP_LENGTH_S` (1-3 min, `_maybe_wake_up`). Any non-idle bridge state, or grabbing him, plays `nap_wake` first; the bridge state is kept in `_after_nap` and applied when the wake-up ends. Idle writes are ignored while napping. Every wake-up restarts the 5 min countdown to the next nap.
- **Laptop doze** (not in the random pool): `Pet._maybe_doze` swaps `working` for `laptop_doze` after `DOZE_AFTER_WORKING_S` (90s) of continuous working, on average after another `DOZE_MEAN_WAIT_S` (2 min), at most once per `DOZE_COOLDOWN_S` (5 min). The bridge's repeated "working" writes are ignored during it; when it ends the pet takes the bridge's current state (`_resume_claude_state`).
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
| 51-53 | Attention (HEY! neon sign) |
| 15 (=26) | Finger gun + heart bubble (last frame of finger_gun) |
| 54+ | Generated by `make sprites` (scooter, finger gun, nap, laptop doze, fly, vibing, unicorn, head pop, teleport, fourth wall, zen, disco, chimichanga, signs, balloon, box sneak, look frames, and right-facing text twins). Which frames each animation plays, and for how long, is in `sprites/deadpool/animations.json`. |

## Clone-Kill Animation Sequence

1. `set_state("doubling")` -> plays sprites [44, 45, 46] once, transitions to "clone_frozen"
2. `_on_frame_tick` detects doubling->clone_frozen transition -> calls `_spawn_clone()`
3. A clone sprite (`Pet._clone`, drawn by each overlay's second `SpriteArea`) appears behind the original, plays attack sprites [27, 28, 29] on a 300ms timer, then `_on_clone_done`
4. Original plays "stumble" [19, 18, 20], then after 900ms `_on_clone_death_done` swaps positions
5. Original teleports to the clone position, clone sprite hidden, state returns to idle

## Key Technical Details

- **Layer-shell overlays** - one `Gtk.Window` per monitor, anchored to all four edges with exclusive zone -1 (covers the whole output, including bar areas), layer `overlay` (above fullscreen windows), keyboard mode `none`, namespace `claude-pet` (visible in `hyprctl layers`). Transparent via CSS `window.claude-pet { background-color: transparent; }`. `Gdk.Surface.set_input_region` is updated whenever a sprite moves so only the sprite rectangles take clicks.
- **Leaving a monitor** - a sprite that leaves an overlay is not hidden but painted transparent in place (`SpriteArea.active = False`): with nothing left to draw GTK skips the frame and the compositor keeps showing the old buffer, i.e. a ghost.
- **Drawing cost** - only the 128x128 `SpriteArea` nodes are redrawn (`queue_draw` on the sprite, not the window), and only when position, frame or state changed; the timer itself runs at 60fps. Idle CPU ~1%.
- **Menu position** - the popover points at the click via `_gdk_rect()`: PyGObject ignores `Gdk.Rectangle(x, y, w, h)` arguments, which put the menu in the top-left corner.
- **Gestures** - `Gtk.GestureDrag` (button 1) for drag/throw with the implicit grab, so the drag keeps tracking when the pointer leaves the sprite or the monitor; `Gtk.GestureClick` (button 3) for the menu.
- **Monitor hotplug** - `Gdk.Display.get_monitors()` "items-changed" rebuilds the overlays and the wander bounds.
- **60fps frame timer** - `FRAME_INTERVAL_MS = 1000 // 60 = 16ms`. Character `_TICK_MS` matches this.
- **Sprite fallback** - if a sprite index is missing, falls back to the lowest available sprite number (end of `SpriteCharacter.__init__`). This means animations work even if a mascot is missing some sprites.
- **Multi-monitor** - WanderEngine tracks the active monitor (global coordinates), switches on drag-drop. Pet is constrained to one monitor at a time.
- **Config persistence** - mascot and hat choice saved to `~/.config/claude-pet/config.json`; an optional `"monitor": "DP-6"` there pins the spawn monitor.
- **Sprites skip tiny files** - PNGs under 500 bytes are skipped (assumed blank/transparent). Any `shime<N>.png` is loaded, there is no upper index limit.

## Running

```bash
make run          # foreground
make debug        # with debug logging (activates "active" wander mode)
make start        # background
make stop         # kill the pet
make test-states  # cycle through all states
make sprites      # regenerate shime54+ and animations.json (tools/build_sprites.py)
make test-working # set a specific state
make install      # install hooks (into ~/.claude and ~/.claude-work)
make uninstall    # remove hooks
```

No Docker needed - this uses system python3 with python3-gi (PyGObject) and python3-gi-cairo.

## Documentation Policy

When making changes that affect behavior, flags, architecture, or features, **always update both CLAUDE.md and README.md** in the same change. Keep them in sync with the code.
