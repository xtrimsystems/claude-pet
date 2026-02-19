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
from pet_window import LABEL_HEIGHT, PetWindow  # noqa: E402

logger = logging.getLogger("claude-pet")

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
    parser.add_argument(
        "--project-name",
        type=str,
        default=None,
        help="Project name to display below the pet sprite",
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
    try:
        os.unlink(pid_file)
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
    check_single_instance(args.pid_file)
    setup_signal_handlers()
    write_pid(args.pid_file)

    logger.info(
        "Starting Claude Pet: size=%d, state_file=%s, pid_file=%s, project=%s",
        args.size,
        args.state_file,
        args.pid_file,
        args.project_name or "(default)",
    )

    bridge = ClaudeBridge(state_file=args.state_file)

    # Extract project hash from state file path for social engine
    # State file format: /tmp/claude-pet-{hash}-state
    social_engine = None
    state_base = os.path.basename(args.state_file)
    if state_base.startswith("claude-pet-") and state_base.endswith("-state"):
        project_hash = state_base[len("claude-pet-"):-len("-state")]
        if project_hash:
            from social_engine import SocialEngine
            social_engine = SocialEngine(
                my_hash=project_hash,
                pet_size=args.size,
                pet_height=args.size + (LABEL_HEIGHT if args.project_name else 0),
            )
            logger.info("Social engine enabled (hash=%s)", project_hash)

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
        debug=args.debug,
        sprites_dir=DEFAULT_SPRITES_DIR,
        mascot_path=mascot_path,
        project_name=args.project_name,
        social_engine=social_engine,
    )
    window.show_all()

    Gtk.main()
    if social_engine:
        social_engine.cleanup()
    remove_pid(args.pid_file)
    logger.info("Claude Pet shut down")


if __name__ == "__main__":
    main()
