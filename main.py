#!/usr/bin/env python3
"""Claude Pet - Animated desktop companion for Claude Code.

A transparent, always-on-top desktop pet that reflects the current
state of a Claude Code session through pixel art animations.
"""

import argparse
import json
import logging
import os
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from claude_bridge import ClaudeBridge  # noqa: E402
from pet_window import PetWindow  # noqa: E402

logger = logging.getLogger("claude-pet")

VALID_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right", "center")
DEFAULT_SPRITES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "claude-pet")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="claude-pet",
        description="Animated desktop companion for Claude Code",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=128,
        help="Window size in pixels (default: 128 = 1x sprite scale)",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default="/tmp/claude-pet-state",
        help="Path to the state file (default: /tmp/claude-pet-state)",
    )
    parser.add_argument(
        "--position",
        type=str,
        default="bottom-right",
        choices=VALID_POSITIONS,
        help="Starting screen position (default: bottom-right)",
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
    return parser.parse_args(argv)


def setup_logging(debug: bool) -> None:
    """Configure logging to stderr."""
    level = logging.DEBUG if debug else logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


def setup_signal_handlers() -> None:
    """Register SIGINT and SIGTERM to gracefully quit GTK."""
    def handle_signal(signum: int, frame: object) -> None:
        logger.info("Received signal %d, shutting down", signum)
        Gtk.main_quit()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


PID_FILE = "/tmp/claude-pet.pid"


def check_single_instance() -> None:
    """Exit if another instance is already running."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # raises if process doesn't exist
            logger.info("Already running (PID %d), exiting", pid)
            sys.exit(0)
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass  # stale PID file, continue


def write_pid() -> None:
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid() -> None:
    try:
        os.unlink(PID_FILE)
    except OSError:
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


def main() -> None:
    args = parse_args()
    setup_logging(args.debug)
    check_single_instance()
    setup_signal_handlers()
    write_pid()

    logger.info(
        "Starting Claude Pet: size=%d, position=%s, state_file=%s",
        args.size,
        args.position,
        args.state_file,
    )

    bridge = ClaudeBridge(state_file=args.state_file)
    config = load_config()

    # Resolve mascot path: explicit --mascot > saved config > first in sprites/
    mascot_path = args.mascot
    if mascot_path is None and config.get("mascot"):
        candidate = os.path.join(DEFAULT_SPRITES_DIR, config["mascot"])
        if os.path.isdir(candidate):
            mascot_path = candidate
    if mascot_path is None:
        for entry in sorted(os.listdir(DEFAULT_SPRITES_DIR)):
            candidate = os.path.join(DEFAULT_SPRITES_DIR, entry)
            if os.path.isdir(candidate):
                mascot_path = candidate
                break
    if mascot_path is None or not os.path.isdir(mascot_path):
        print("Error: No mascot found. Place a mascot in sprites/ or use --mascot <path>")
        print("See sprites/README.md for details.")
        sys.exit(1)

    from sprite_character import SpriteCharacter
    character = SpriteCharacter(mascot_path)
    if not character._sprites:
        print(f"Error: No shime*.png sprites found in {mascot_path}")
        sys.exit(1)
    logger.info("Loaded mascot from %s (%d sprites)",
                 mascot_path, len(character._sprites))

    window = PetWindow(
        character=character,
        bridge=bridge,
        size=args.size,
        position=args.position,
        debug=args.debug,
        sprites_dir=DEFAULT_SPRITES_DIR,
        mascot_path=mascot_path,
    )
    window.show_all()

    Gtk.main()
    remove_pid()
    logger.info("Claude Pet shut down")


if __name__ == "__main__":
    main()
