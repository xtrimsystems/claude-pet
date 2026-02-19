# Claude Pet

An animated desktop companion for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). A transparent, always-on-top pixel art character that reflects the current state of your Claude Code session — thinking, working, waiting for input, celebrating, or erroring out.

Uses the [Shimeji-ee](https://kilkakon.com/shimeji/) / [Shijima-Qt](https://getshijima.app) sprite format. Standard Shimeji mascot packs will partially work out of the box — basic movement animations (walking, climbing, sitting, falling, dragging) use standard sprite indices. However, Claude-specific state animations (working, celebrating, thinking, error, doubling) use higher sprite indices (38-50) that don't exist in most packs. Missing sprites fall back to the first available frame, so the pet still functions — it just won't have distinct animations for those states. To get the full experience, you can add custom sprites to the pack at those indices (see the sprite mapping in [CLAUDE.md](CLAUDE.md)).

## Features

- Reacts to Claude Code state in real-time (idle, thinking, working, attention, celebrating, error)
- Shimeji-style wandering: walks, climbs screen edges, sits, jumps, falls
- Drag and throw with physics simulation
- Multi-monitor support
- **Social behaviors**: multiple pets interact — they face each other when sitting nearby, avoid sitting next to each other, and occasionally fight (attacker plays attack animation, defender gets shoved back)
- Right-click context menu for manual state control, scaling, and special actions
- Auto-starts when Claude Code runs (via hooks)
- Works on X11 with a compositor (picom, compton, etc.)

## Requirements

- Linux with X11 and a compositor
- Python 3.10+
- GTK 3 (PyGObject)

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 xprop
```

## Quick Start

1. Clone the repo
2. Add a mascot pack to `sprites/` (see [sprites/README.md](sprites/README.md))
3. Install hooks: `make install`
4. Run: `make run`

Or with a specific mascot:

```bash
python3 main.py --mascot /path/to/your/mascot
```

## i3 / Regolith Users

Add to your i3 config:

```
for_window [class="Claude-pet"] floating enable, border none, sticky enable
for_window [title="Claude Pet"] floating enable, border none, sticky enable
```

## Options

```
--size SIZE              Window size in pixels (default: 128)
--mascot PATH            Path to mascot directory with shime*.png sprites
--state-file PATH        Path to state file (default: /tmp/claude-pet-state)
--pid-file PATH          Path to PID file (default: /tmp/claude-pet.pid)
--project-name NAME      Project name to display near the sprite
--debug                  Enable debug logging
```

## How It Works

Claude Pet installs hooks into Claude Code that write state changes to a file. The pet monitors this file and updates its animation accordingly:

| Claude Code Event | Pet State |
|---|---|
| User sends prompt | Thinking |
| Tool use starts | Working |
| Permission needed | Attention |
| Session stops | Celebrating (then idle) |
| Context compaction | Doubling (clone-kill animation) |
| Idle for 60s | Idle (wandering around) |

When idle, the pet wanders the screen Shimeji-style — walking along edges, climbing walls, sitting, kicking, jumping. When multiple Claude Code sessions are active, their pets interact: they face each other when sitting nearby, avoid crowding, and occasionally pick fights.

You can spawn test pets to see social behaviors in action:

```bash
make test-pet   # run multiple times to spawn several pets
make stop       # kill them all
```

## Acknowledgments

- Inspired by [Shimeji-ee](https://kilkakon.com/shimeji/) by Kilkakon and the original [Shimeji](https://www.group-finity.com/shimeji/) by Yuki Yamada / Group Finity
- Compatible with [Shijima-Qt](https://getshijima.app) mascot packs by pixelomer
- Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) by Anthropic

## License

[MIT](LICENSE)
