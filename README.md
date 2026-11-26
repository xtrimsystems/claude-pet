# Claude Pet

An animated desktop companion for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). A transparent, always-on-top pixel art character that reflects the current state of your Claude Code session — thinking, working, waiting for input, celebrating, or erroring out.

Uses the [Shimeji-ee](https://kilkakon.com/shimeji/) / [Shijima-Qt](https://getshijima.app) sprite format. Standard Shimeji mascot packs will partially work out of the box — basic movement animations (walking, climbing, sitting, falling, dragging) use standard sprite indices. However, Claude-specific state animations (working, celebrating, thinking, error, doubling) use higher sprite indices (38-50) that don't exist in most packs. Missing sprites fall back to the first available frame, so the pet still functions — it just won't have distinct animations for those states. To get the full experience, you can add custom sprites to the pack at those indices (see the sprite mapping in [CLAUDE.md](CLAUDE.md)).

## Features

- Reacts to Claude Code state in real-time (idle, thinking, working, attention, celebrating, error)
- Shimeji-style wandering: walks, climbs screen edges, sits, jumps, falls
- Drag and throw with physics simulation
- Multi-monitor support
- Right-click context menu for manual state control, scaling, and special actions
- Auto-starts with your first Claude Code session and leaves with the last one (via hooks)
- One pet for the whole desktop — every session (and subagent) drives the same pet
- Native Wayland: a click-through layer-shell overlay on every monitor

## Requirements

- A Wayland compositor with `wlr-layer-shell` (Hyprland, sway, river, …)
- Python 3.10+
- GTK 4 (PyGObject), pycairo and gtk4-layer-shell

```bash
sudo pacman -S python-gobject python-cairo gtk4 gtk4-layer-shell
```

## Quick Start

1. Clone the repo
2. Add a mascot pack to `sprites/` (see [sprites/README.md](sprites/README.md))
3. Install hooks: `make install` (into `~/.claude` and `~/.claude-work`; set `CLAUDE_CONFIG_DIRS` for other config dirs)
4. Start a Claude Code session — or run it by hand: `make run`

Or with a specific mascot:

```bash
python3 main.py --mascot /path/to/your/mascot
```

## Options

```
--size SIZE              Sprite size in pixels (default: 128)
--mascot PATH            Path to mascot directory with shime*.png sprites
--state-file PATH        Path to state file (default: /tmp/claude-pet-state)
--pid-file PATH          Path to PID file (default: /tmp/claude-pet.pid)
--monitor NAME           Monitor to appear on, e.g. DP-6 (default: "monitor" in config.json, else the first)
--debug                  Enable debug logging (and the more active wander mode)
```

## How It Works

Claude Pet installs hooks into Claude Code that write state changes to a file. The pet monitors this file and updates its animation accordingly:

| Claude Code Event | Pet State |
|---|---|
| User sends prompt | Thinking |
| Tool use starts | Working |
| Permission needed | Attention |
| Claude finishes a turn | Celebrating (then idle) |
| Context compaction | Doubling (clone-kill animation) |
| Idle for 60s | Idle (wandering around) |
| Last session ends | Pet exits |

When idle, the pet wanders the screen Shimeji-style — walking along edges, climbing walls, sitting, kicking, jumping, and now and then riding a scooter or a unicorn across the screen, floating up on a balloon until it pops, sneaking around in a cardboard box, teleporting, or pulling a trick (finger gun, a fly that won't leave him alone, vibing to his walkman, popping his own head off, kicking the screen, zen floating, disco). When you send a prompt he may hold up a "MAXIMUM EFFORT!" sign, and sometimes a "NAILED IT!" one when Claude finishes. After 5 minutes without Claude activity he takes a nap of a minute or two (Claude starting, or grabbing him, wakes him up early), and during long work sessions he may doze off at his laptop. Everything in the menu works at any moment, even mid-nap or mid-trick. Drag it around, throw it, or right-click it for the menu (scale, mascot, poses, rides, teleport, tricks, quit).

The hook script registers every live session in `/tmp/claude-pet-sessions/`; the pet is started by the first one and stopped by the last one, so several sessions, terminals and subagents share a single pet.

```bash
make test-states   # cycle the pet through all states
make sprites       # regenerate the Deadpool extras (sprites 54+ and sprites/deadpool/animations.json)
make stop          # kill it
```

## Acknowledgments

- Inspired by [Shimeji-ee](https://kilkakon.com/shimeji/) by Kilkakon and the original [Shimeji](https://www.group-finity.com/shimeji/) by Yuki Yamada / Group Finity
- Compatible with [Shijima-Qt](https://getshijima.app) mascot packs by pixelomer
- Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) by Anthropic

## License

[MIT](LICENSE)
