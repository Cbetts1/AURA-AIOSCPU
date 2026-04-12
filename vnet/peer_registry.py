"""
AURA-AIOSCPU Peer Registry
============================
Tracks sibling AURA nodes that are known to this instance.

Peers can be discovered via:
  1. Command Center registration response (``peers`` list)
  2. Direct announcement over the local command channel
  3. Manual addition via the CLI or shell

Each peer entry records:
  - node_id / alias
  - last_seen timestamp
  - reported capabilities
  - reported status
  - HTTP address (host:port) if the peer exposes a command channel

The registry serialises to ``config/peers.json`` so discoveries survive
restarts.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import List

logger = logging.getLogger(__name__)

_PEERS_FILE = "peers.json"
_PEER_STALE_S = 300  # mark a peer as stale after 5 minutes without a ping


@dataclass
class PeerRecord:
    """A single peer node entry."""
    node_id:      str
    alias:        str     = "unknown"
    host:         str     = ""         # IP or hostname
    port:         int     = 0          # command channel port (0 = unknown)
    capabilities: list    = field(default_factory=list)
    status:       str     = "unknown"
    first_seen:   float   = field(default_factory=time.time)
    last_seen:    float   = field(default_factory=time.time)
    version:      str     = ""

    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > _PEER_STALE_S

    def touch(self) -> None:
        self.last_seen = time.time()

    def to_dict(self) -> dict:
        return asdict(self)


class PeerRegistry:
    """
    In-memory peer registry with optional file-backed persistence.

    Parameters
    ----------
    config_dir : str | None
        Directory where ``peers.json`` is stored.
        Defaults to ``<repo_root>/config/``.
    """

    def __init__(self, config_dir: str | None = None):
        self._config_dir = config_dir or _default_config_dir()
        os.makedirs(self._config_dir, exist_ok=True)
        self._path  = os.path.join(self._config_dir, _PEERS_FILE)
        self._peers: dict[str, PeerRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add_or_update(
        self,
        node_id: str,
        *,
        alias: str = "unknown",
        host: str = "",
        port: int = 0,
        capabilities: list | None = None,
        status: str = "unknown",
        version: str = "",
    ) -> PeerRecord:
        """Add a new peer or refresh an existing one."""
        if node_id in self._peers:
            peer = self._peers[node_id]
            peer.alias        = alias or peer.alias
            peer.host         = host  or peer.host
            peer.port         = port  or peer.port
            peer.capabilities = capabilities if capabilities is not None else peer.capabilities
            peer.status       = status
            peer.version      = version or peer.version
            peer.touch()
        else:
            peer = PeerRecord(
                node_id      = node_id,
                alias        = alias,
                host         = host,
                port         = port,
                capabilities = capabilities or [],
                status       = status,
                version      = version,
            )
            self._peers[node_id] = peer
            logger.info("PeerRegistry: +peer %s (%s)", node_id, alias)
        self._save()
        return peer

    def remove(self, node_id: str) -> bool:
        """Remove a peer. Returns True if it existed."""
        if node_id in self._peers:
            del self._peers[node_id]
            self._save()
            logger.info("PeerRegistry: -peer %s", node_id)
            return True
        return False

    def touch(self, node_id: str) -> bool:
        """Update last_seen for a peer. Returns True if peer exists."""
        if node_id in self._peers:
            self._peers[node_id].touch()
            return True
        return False

    def merge_from_cc(self, peer_list: List[dict]) -> int:
        """
        Merge a list of peer dicts returned by the CC registration response.
        Returns the number of new/updated peers.
        """
        count = 0
        for p in peer_list:
            if not isinstance(p, dict):
                continue
            node_id = p.get("node_id")
            if not node_id:
                continue
            self.add_or_update(
                node_id,
                alias=p.get("alias", "unknown"),
                host=p.get("host", ""),
                port=int(p.get("port", 0)),
                capabilities=p.get("capabilities", []),
                status=p.get("status", "unknown"),
                version=p.get("version", ""),
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, node_id: str) -> PeerRecord | None:
        return self._peers.get(node_id)

    def all(self) -> list[PeerRecord]:
        return list(self._peers.values())

    def active(self) -> list[PeerRecord]:
        """Return peers that have been seen recently."""
        return [p for p in self._peers.values() if not p.is_stale()]

    def stale(self) -> list[PeerRecord]:
        return [p for p in self._peers.values() if p.is_stale()]

    def count(self) -> int:
        return len(self._peers)

    def to_list(self) -> list[dict]:
        return [p.to_dict() for p in self._peers.values()]

    def __len__(self) -> int:
        return len(self._peers)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        try:
            with open(self._path, "w") as fh:
                json.dump(self.to_list(), fh, indent=2)
        except OSError as exc:
            logger.warning("PeerRegistry: save error: %s", exc)

    def _load(self) -> None:
        if not os.path.isfile(self._path):
            return
        try:
            with open(self._path) as fh:
                records = json.load(fh)
            for r in records:
                if not isinstance(r, dict) or "node_id" not in r:
                    continue
                pr = PeerRecord(**{
                    k: v for k, v in r.items()
                    if k in PeerRecord.__dataclass_fields__
                })
                self._peers[pr.node_id] = pr
            logger.debug("PeerRegistry: loaded %d peers", len(self._peers))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("PeerRegistry: load error: %s", exc)


def _default_config_dir() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "config")
