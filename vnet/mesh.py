"""
AURA-AIOSCPU Virtual Mesh
==========================
Manages the virtual mesh that connects all AURA nodes in a cluster.

Responsibilities
----------------
- Maintain a PeerRegistry of all known siblings.
- Periodically broadcast this node's state to reachable peers.
- Accept incoming state sync messages from peers.
- Elect a coordinator (peer with lexicographically lowest node_id).
- Expose a high-level API for the CommandChannel and CLI.

Coordinator Election
--------------------
Simple "lowest ID wins" leader election — no quorum needed.
Each node evaluates who should be coordinator based on the set of active
peers (including itself).  The coordinator label is informational: any
node can still receive and execute commands directly.

State Sync (pull model)
-----------------------
When ``sync_state`` is called the mesh iterates over reachable peers and
GETs their ``/api/node/status`` endpoint, then updates the peer registry.
This is a lightweight pull — no push/subscribe needed.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from vnet.peer_registry import PeerRegistry, PeerRecord

logger = logging.getLogger(__name__)

_SYNC_INTERVAL_S  = 60      # how often to sync state from peers
_REQUEST_TIMEOUT  = 5       # per-peer HTTP timeout


class VirtualMesh:
    """
    Virtual mesh coordinator for a cluster of AURA nodes.

    Parameters
    ----------
    identity : NodeIdentity
        The local node's identity.
    peer_registry : PeerRegistry
        Shared peer registry.
    sync_interval_s : float
        How often to run peer state sync.
    """

    def __init__(
        self,
        identity,
        peer_registry: PeerRegistry,
        sync_interval_s: float = _SYNC_INTERVAL_S,
    ):
        self._identity      = identity
        self._peers         = peer_registry
        self._sync_interval = sync_interval_s

        self._running  = False
        self._thread: threading.Thread | None = None
        self._lock     = threading.Lock()

        self._sync_count   = 0
        self._last_sync_ts = 0.0
        self._coordinator: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background sync daemon."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="vnet-mesh-sync"
        )
        self._thread.start()
        logger.info("VirtualMesh: sync thread started (interval=%.0fs)", self._sync_interval)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync_state(self) -> dict[str, Any]:
        """
        Pull status from all reachable peers, update the registry, and
        recompute coordinator.  Returns a summary dict.
        """
        reachable = 0
        unreachable = 0
        updated: list[str] = []

        for peer in self._peers.active():
            if not peer.host or not peer.port:
                continue
            try:
                info = self._fetch_peer_status(peer)
                if info:
                    self._peers.add_or_update(
                        peer.node_id,
                        alias=info.get("alias", peer.alias),
                        host=peer.host,
                        port=peer.port,
                        capabilities=info.get("capabilities", peer.capabilities),
                        status=info.get("status", "unknown"),
                        version=info.get("version", peer.version),
                    )
                    updated.append(peer.node_id)
                    reachable += 1
            except Exception as exc:
                logger.debug("VirtualMesh: peer %s unreachable: %s", peer.node_id, exc)
                unreachable += 1

        self._compute_coordinator()
        self._sync_count += 1
        self._last_sync_ts = time.time()

        result = {
            "reachable":   reachable,
            "unreachable": unreachable,
            "updated":     updated,
            "coordinator": self._coordinator,
            "peer_count":  self._peers.count(),
        }
        logger.debug("VirtualMesh: sync complete: %s", result)
        return result

    def announce_to_peer(self, peer: PeerRecord) -> bool:
        """
        POST this node's identity to a peer's /api/node/announce endpoint.
        Returns True on success.
        """
        if not peer.host or not peer.port:
            return False
        url = f"http://{peer.host}:{peer.port}/api/node/announce"
        payload = self._identity.to_dict()
        payload["host"] = self._identity.to_dict().get("hostname", "")
        payload["port"] = 7332  # default command channel port
        try:
            body = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT):
                pass
            return True
        except Exception as exc:
            logger.debug("VirtualMesh: announce to %s failed: %s", peer.node_id, exc)
            return False

    # ------------------------------------------------------------------
    # Coordinator
    # ------------------------------------------------------------------

    @property
    def coordinator(self) -> str | None:
        """node_id of the current coordinator, or None if no peers."""
        return self._coordinator

    def am_coordinator(self) -> bool:
        """True if this node is the current coordinator."""
        return self._coordinator == self._identity.node_id

    def _compute_coordinator(self) -> None:
        candidates = [self._identity.node_id]
        for peer in self._peers.active():
            candidates.append(peer.node_id)
        self._coordinator = sorted(candidates)[0]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        return {
            "running":        self._running,
            "sync_count":     self._sync_count,
            "last_sync_ts":   self._last_sync_ts or None,
            "peer_count":     self._peers.count(),
            "active_peers":   len(self._peers.active()),
            "coordinator":    self._coordinator,
            "am_coordinator": self.am_coordinator(),
        }

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while self._running:
            time.sleep(self._sync_interval)
            if not self._running:
                break
            try:
                self.sync_state()
            except Exception as exc:
                logger.error("VirtualMesh: sync error: %s", exc)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _fetch_peer_status(self, peer: PeerRecord) -> dict:
        url = f"http://{peer.host}:{peer.port}/api/node/status"
        req = urllib.request.Request(
            url,
            headers={
                "X-Node-ID":    self._identity.node_id,
                "X-Node-Alias": self._identity.alias,
            },
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
