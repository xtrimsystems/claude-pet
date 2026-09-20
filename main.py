#!/usr/bin/env python3
"""Claude Pet - Animated desktop companion for Claude Code.

A transparent, always-on-top desktop pet that reflects the current
state of a Claude Code session through pixel art animations.
Native Wayland: GTK4 + wlr-layer-shell (gtk4-layer-shell).
"""

import argparse
import ctypes.util
import json
import logging
import os
import signal
import sys

logger = logging.getLogger("claude-pet")

DEFAULT_SPRITES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "claude-pet")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LAYER_SHELL_LIB = "gtk4-layer-shell"


def ensure_layer_shell_preloaded() -> None:
    """Re-exec with libgtk4-layer-shell in LD_PRELOAD.

    The library has to be loaded before libwayland-client, which language
    bindings cannot guarantee — preloading is the way its documentation
    prescribes for that case.
    """
    lib = ctypes.util.find_library(LAYER_SHELL_LIB)
    if lib is None:
        print("Error: libgtk4-layer-shell not found. Install it with: sudo pacman -S gtk4-layer-shell")
        sys.exit(1)
    preload = os.environ.get("LD_PRELOAD", "")
    if lib in preload.split(":"):
        return
    os.environ["LD_PRELOAD"] = f"{lib}:{preload}" if preload else lib
    os.execv(sys.executable, [sys.executable] + sys.argv)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="claude-pet",
        description="Animated desktop companion for Claude Code",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=128,
        help="Sprite size in pixels (default: 128 = 1x sprite scale)",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default="/tmp/claude-pet-state",
        help="Path to the state file (default: /tmp/claude-pet-state)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to stderr",
    )
    parser.add_argument(
        "--mascot",
        type=str,
        default=None,
        help="Path to mascot directory with shime*.png sprites (Shimeji-ee / Shijima-Qt format)",
    )
    parser.add_argument(
        "--pid-file",
        type=str,
        default="/tmp/claude-pet.pid",
        help="Path to the PID file (default: /tmp/claude-pet.pid)",
    )
    return parser.parse_args(argv)


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


def check_single_instance(pid_file: str) -> None:
    """Exit if another instance is already running."""
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # raises if process doesn't exist
            logger.info("Already running (PID %d), exiting", pid)
            sys.exit(0)
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass  # stale PID file, continue


def write_pid(pid_file: str) -> None:
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def remove_pid(pid_file: str) -> None:
    """Delete the PID file only if it still refers to this process."""
    try:
        with open(pid_file) as f:
            if int(f.read().strip()) == os.getpid():
                os.unlink(pid_file)
    except (OSError, ValueError):
        pass


def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def resolve_mascot(explicit: str | None, config: dict) -> str | None:
    """Explicit --mascot > saved config > first directory in sprites/."""
    if explicit:
        return explicit
    if config.get("mascot"):
        candidate = os.path.join(DEFAULT_SPRITES_DIR, config["mascot"])
        if os.path.isdir(candidate):
            return candidate
    for entry in sorted(os.listdir(DEFAULT_SPRITES_DIR)):
        candidate = os.path.join(DEFAULT_SPRITES_DIR, entry)
        if os.path.isdir(candidate):
            return candidate
    return None


def main() -> None:
    ensure_layer_shell_preloaded()
    args = parse_args()
    setup_logging(args.debug)
    check_single_instance(args.pid_file)
    write_pid(args.pid_file)

    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import GLib, Gtk, Gtk4LayerShell

    Gtk.init()
    if not Gtk4LayerShell.is_supported():
        print("Error: the compositor does not support wlr-layer-shell (are you on Wayland?)")
        remove_pid(args.pid_file)
        sys.exit(1)

    from claude_bridge import ClaudeBridge
    from pet_window import Pet
    from sprite_character import SpriteCharacter

    logger.info("Starting Claude Pet: size=%d, state_file=%s, pid_file=%s",
                args.size, args.state_file, args.pid_file)

    mascot_path = resolve_mascot(args.mascot, load_config())
    if mascot_path is None or not os.path.isdir(mascot_path):
        print("Error: No mascot found. Place a mascot in sprites/ or use --mascot <path>")
        print("See sprites/README.md for details.")
        remove_pid(args.pid_file)
        sys.exit(1)

    character = SpriteCharacter(mascot_path)
    if not character._sprites:
        print(f"Error: No shime*.png sprites found in {mascot_path}")
        remove_pid(args.pid_file)
        sys.exit(1)
    logger.info("Loaded mascot from %s (%d sprites)", mascot_path, len(character._sprites))

    loop = GLib.MainLoop()
    pet = Pet(
        character=character,
        bridge=ClaudeBridge(state_file=args.state_file),
        size=args.size,
        debug=args.debug,
        sprites_dir=DEFAULT_SPRITES_DIR,
        mascot_path=mascot_path,
        on_quit=loop.quit,
    )

    def handle_signal(signum: int) -> bool:
        logger.info("Received signal %d, shutting down", signum)
        pet.shutdown()
        loop.quit()
        return False

    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
        signal_add = GLibUnix.signal_add
    except (ValueError, ImportError):
        signal_add = GLib.unix_signal_add
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal_add(GLib.PRIORITY_DEFAULT, sig, handle_signal, sig)

    loop.run()
    remove_pid(args.pid_file)
    logger.info("Claude Pet shut down")


if __name__ == "__main__":
    main()
