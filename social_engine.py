"""Inter-process social behaviors between pet instances.

Pets share position via files in /tmp and use that data to avoid
sitting near each other, face nearby peers, and occasionally fight.
"""

from __future__ import annotations

import glob
import logging
import os
import random
import tempfile
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Position and state of a remote pet instance."""
    hash: str
    x: float
    y: float
    width: int
    height: int
    facing: int
    state: str
    move_state: str
    monitor_idx: int
    fight_target: str
    timestamp: float


@dataclass
class SocialDirective:
    """Instructions from the social engine to the pet window."""
    block_sit: bool = False
    face_toward: int | None = None  # -1 or 1 to override facing, None = no override
    fight_role: str | None = None   # "attacker" or "defender" or None
    fight_peer_x: float = 0.0      # peer x for computing throw direction
    nearest_peer_dist: float = float("inf")  # distance to nearest peer on same monitor


class SocialEngine:
    """Coordinates social behaviors between pet instances via position files."""

    WRITE_INTERVAL = 10       # write every N frames (~166ms at 60fps)
    READ_INTERVAL_MS = 300    # read peers every 300ms
    STALE_THRESHOLD = 3.0     # discard peers older than 3 seconds
    FIGHT_CHANCE = 0.03       # ~3% per second
    FIGHT_COOLDOWN = 10.0     # seconds between fights
    FIGHT_PROPOSAL_TTL = 3.0  # seconds before a proposal expires
    PROXIMITY_SIT = 1.5       # block sit within this * pet_size
    PROXIMITY_FACE = 3.0      # face peer within this * pet_size
    PROXIMITY_FIGHT = 1.0     # fight within this * pet_size (about one sprite width apart)

    def __init__(self, my_hash: str, pet_size: int, pet_height: int) -> None:
        self._my_hash = my_hash
        self._pet_size = pet_size
        self._pet_height = pet_height
        self._pos_file = f"/tmp/claude-pet-{my_hash}-pos"
        self._peers: list[PeerInfo] = []
        self._frame_count = 0
        self._last_read = 0.0
        self._last_fight = 0.0
        self._fight_target: str = ""  # hash of peer we want to fight (proposal)
        self._fight_role: str = ""    # "attacker" or "defender" (set on confirmation)
        self._fight_active = False    # True once both sides confirmed
        self._fight_delivered = False  # True after directive was consumed by pet_window
        self._fight_proposed_at: float = 0.0  # when we wrote our proposal

    def write_position(self, x: float, y: float, facing: int,
                       state: str, move_state: str,
                       monitor_idx: int) -> None:
        """Write current position to the shared file (atomic via rename)."""
        self._frame_count += 1
        if self._frame_count % self.WRITE_INTERVAL != 0:
            return

        line = (f"{x},{y},{self._pet_size},{self._pet_height},"
                f"{facing},{state},{move_state},{monitor_idx},"
                f"{self._fight_target},{time.time():.3f}\n")
        try:
            fd, tmp = tempfile.mkstemp(dir="/tmp", prefix="claude-pet-pos-")
            os.write(fd, line.encode())
            os.close(fd)
            os.rename(tmp, self._pos_file)
        except OSError:
            pass

    def _read_peers(self) -> None:
        """Glob position files and parse peer positions, skipping self and stale."""
        now = time.time()
        if now - self._last_read < self.READ_INTERVAL_MS / 1000.0:
            return
        self._last_read = now

        peers = []
        for path in glob.glob("/tmp/claude-pet-*-pos"):
            # Extract hash from filename: /tmp/claude-pet-{hash}-pos
            basename = os.path.basename(path)
            if not basename.startswith("claude-pet-") or not basename.endswith("-pos"):
                continue
            peer_hash = basename[len("claude-pet-"):-len("-pos")]
            if peer_hash == self._my_hash:
                continue

            try:
                with open(path) as f:
                    line = f.readline().strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 10:
                    continue
                peer = PeerInfo(
                    hash=peer_hash,
                    x=float(parts[0]),
                    y=float(parts[1]),
                    width=int(parts[2]),
                    height=int(parts[3]),
                    facing=int(parts[4]),
                    state=parts[5],
                    move_state=parts[6],
                    monitor_idx=int(parts[7]),
                    fight_target=parts[8],
                    timestamp=float(parts[9]),
                )
                if now - peer.timestamp <= self.STALE_THRESHOLD:
                    peers.append(peer)
            except (OSError, ValueError, IndexError):
                continue

        self._peers = peers

    def tick(self, x: float, y: float, facing: int,
             state: str, monitor_idx: int,
             move_state: str) -> SocialDirective:
        """Run social logic and return a directive for the pet window.

        Should be called every frame, but peer reading is throttled internally.
        """
        self._read_peers()
        directive = SocialDirective()

        if not self._peers:
            return directive

        # Find nearest peer on the same monitor
        nearest: PeerInfo | None = None
        nearest_dist = float("inf")
        for peer in self._peers:
            if peer.monitor_idx != monitor_idx:
                continue
            dist = abs(peer.x - x)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = peer

        if nearest is None:
            return directive

        directive.nearest_peer_dist = nearest_dist
        now = time.time()

        # Expire stale fight proposals
        if (self._fight_target and not self._fight_active
                and now - self._fight_proposed_at > self.FIGHT_PROPOSAL_TTL):
            self._fight_target = ""
            self._fight_proposed_at = 0.0

        # --- Active fight: deliver directive once, then block ---
        if self._fight_active:
            if not self._fight_delivered:
                self._fight_delivered = True
                directive.fight_role = self._fight_role
                for peer in self._peers:
                    if peer.hash == self._fight_target:
                        directive.fight_peer_x = peer.x
                logger.debug("Fight: %s against %s", self._fight_role, self._fight_target)
            return directive

        # --- Check for mutual targeting (handshake complete) ---
        if self._fight_target and not self._fight_active:
            for peer in self._peers:
                if (peer.hash == self._fight_target
                        and peer.fight_target == self._my_hash
                        and peer.monitor_idx == monitor_idx):
                    # Both sides proposed — fight is on!
                    # Re-check proximity at confirmation time
                    dist = abs(peer.x - x)
                    if dist > self.PROXIMITY_FIGHT * self._pet_size:
                        # Too far now, cancel
                        self._fight_target = ""
                        break
                    self._fight_active = True
                    self._last_fight = now
                    if self._my_hash < peer.hash:
                        self._fight_role = "attacker"
                    else:
                        self._fight_role = "defender"
                    self._fight_delivered = True
                    directive.fight_role = self._fight_role
                    directive.fight_peer_x = peer.x
                    logger.debug("Fight confirmed: %s against %s",
                                 self._fight_role, self._fight_target)
                    return directive

        # --- Check if a peer is proposing to us (respond with counter-proposal) ---
        if not self._fight_target and now - self._last_fight > self.FIGHT_COOLDOWN:
            for peer in self._peers:
                if (peer.fight_target == self._my_hash
                        and peer.monitor_idx == monitor_idx
                        and state == "idle" and move_state == "walk"):
                    dist = abs(peer.x - x)
                    if dist <= self.PROXIMITY_FIGHT * self._pet_size:
                        self._fight_target = peer.hash
                        self._fight_proposed_at = now
                        logger.debug("Fight: accepted proposal from %s", peer.hash)
                        break

        # --- No active fight: check proximity behaviors ---

        # Block sitting near peers
        if nearest_dist < self.PROXIMITY_SIT * self._pet_size:
            directive.block_sit = True

        # Face toward nearest peer when sitting
        if move_state == "sit" and nearest_dist < self.PROXIMITY_FACE * self._pet_size:
            if nearest.x > x:
                directive.face_toward = 1   # peer is to the right
            else:
                directive.face_toward = -1  # peer is to the left

        # --- Fight proposal: random chance when close and both walking ---
        if (not self._fight_target
                and nearest_dist < self.PROXIMITY_FIGHT * self._pet_size
                and state == "idle"
                and move_state == "walk"
                and nearest.state == "idle"
                and nearest.move_state == "walk"
                and now - self._last_fight > self.FIGHT_COOLDOWN):
            if random.random() < self.FIGHT_CHANCE * (self.READ_INTERVAL_MS / 1000.0):
                self._fight_target = nearest.hash
                self._fight_proposed_at = now
                logger.debug("Fight: proposed to %s", nearest.hash)

        return directive

    def clear_fight(self) -> None:
        """Called when a fight animation completes."""
        self._fight_active = False
        self._fight_target = ""
        self._fight_role = ""
        self._fight_delivered = False
        self._fight_proposed_at = 0.0
        logger.debug("Fight cleared")

    def cleanup(self) -> None:
        """Remove position file on shutdown."""
        try:
            os.unlink(self._pos_file)
        except OSError:
            pass
