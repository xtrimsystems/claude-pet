# Claude Pet

An animated desktop companion for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). A transparent, always-on-top pixel art character that reflects the current state of your Claude Code session — thinking, working, waiting for input, celebrating, or erroring out.

Uses the [Shimeji-ee](https://kilkakon.com/shimeji/) / [Shijima-Qt](https://getshijima.app) sprite format, so you can use any compatible mascot pack.

## Features

- Reacts to Claude Code state in real-time (idle, thinking, working, attention, celebrating, error)
- Shimeji-style wandering: walks, climbs screen edges, sits, jumps, falls
- Drag and throw with physics simulation
- Multi-monitor support
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
--size SIZE        Window size in pixels (default: 128)
--mascot PATH      Path to mascot directory with shime*.png sprites
--position POS     Starting position: top-left, top-right, bottom-left, bottom-right, center
--state-file PATH  Path to state file (default: /tmp/claude-pet-state)
--debug            Enable debug logging
```

## How It Works

Claude Pet installs hooks into Claude Code that write state changes to a file. The pet monitors this file and updates its animation accordingly:

| Claude Code Event | Pet State |
|---|---|
| Tool use starts | Working (active animation) |
| Tool use completes | Thinking (contemplative) |
| Session stops / needs input | Attention (alert) |
| Idle for 30s | Idle (wandering around) |

When idle, the pet wanders the screen Shimeji-style — walking along edges, climbing walls, sitting, jumping.

## Acknowledgments

- Inspired by [Shimeji-ee](https://kilkakon.com/shimeji/) by Kilkakon and the original [Shimeji](https://www.group-finity.com/shimeji/) by Yuki Yamada / Group Finity
- Compatible with [Shijima-Qt](https://getshijima.app) mascot packs by pixelomer
- Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) by Anthropic

## License

[MIT](LICENSE)
