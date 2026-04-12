"""
AURA-AIOSCPU Node Identity
============================
Generates and persists a stable virtual identity for this AURA node.

Each node has:
  - A UUID (generated once, stored in config/node_identity.json)
  - A human-readable alias (defaults to hostname + "-aura")
  - A declared capability set
  - Build metadata (version, repo, branch)
  - A serialisation method for CC registration payloads

The identity is stable across restarts and is used by:
  - CommandCenterClient  (registration payload)
  - CommandChannel       (X-Node-ID header)
  - VirtualMesh          (peer table key)
"""

import json
import logging
import os
import platform
import socket
import time
import uuid

logger = logging.getLogger(__name__)

_IDENTITY_FILE_NAME = "node_identity.json"

# ---------------------------------------------------------------------------
# Canonical capability names
# ---------------------------------------------------------------------------

CAPABILITIES = {
    "kernel.event_bus":      "Publish/subscribe event bus",
    "kernel.scheduler":      "Task and job scheduling",
    "kernel.watchdog":       "Service watchdog and self-repair",
    "kernel.modes":          "Multi-mode kernel surface (universal/internal/hardware)",
    "services.registry":     "System service registry with dependency ordering",
    "services.health":       "Service health monitoring and circuit breaker",
    "services.logging":      "Structured log aggregation",
    "services.network":      "Network connectivity monitoring",
    "services.storage":      "Virtual key-value storage",
    "services.job_queue":    "Asynchronous job queue",
    "services.build":        "In-process rootfs builder and integrity verifier",
    "services.web_terminal": "Browser-accessible HTML5 terminal (port 7331)",
    "services.cmd_channel":  "Remote REST command channel (port 7332)",
    "aura.ai_layer":         "AURA AI personality and context engine",
    "aura.memory":           "Persistent memory and recall",
    "aura.introspection":    "Runtime self-introspection",
    "hal.storage":           "Hardware abstraction — storage device",
    "shell.plugins":         "Extensible POSIX-compatible shell with plugins",
    "vnet.node":             "Virtual-network node (this capability)",
    "vnet.mesh":             "Virtual mesh peer synchronisation",
    "vnet.cmd_channel":      "Accepts remote commands from Command Center",
    "builder.module":        "Can scaffold new modules at runtime",
}


class NodeIdentity:
    """
    Stable virtual identity for this AURA node.

    Parameters
    ----------
    config_dir : str
        Directory where node_identity.json is stored.
        Defaults to ``<repo_root>/config/``.
    alias : str | None
        Human-readable node alias.  Defaults to ``<hostname>-aura``.
    version : str
        Node software version string.
    """

    def __init__(
        self,
        config_dir: str | None = None,
        alias: str | None = None,
        version: str = "0.1.0",
    ):
        self._config_dir = config_dir or _default_config_dir()
        os.makedirs(self._config_dir, exist_ok=True)
        self._path = os.path.join(self._config_dir, _IDENTITY_FILE_NAME)

        stored = self._load()
        self.node_id: str   = stored.get("node_id")   or str(uuid.uuid4())
        self.alias: str     = alias or stored.get("alias") or _default_alias()
        self.version: str   = version
        self.created_at: float = stored.get("created_at") or time.time()
        self.capabilities: dict[str, str] = dict(CAPABILITIES)

        self._save()
        logger.info(
            "NodeIdentity: id=%s alias=%r version=%s",
            self.node_id, self.alias, self.version,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise identity for CC registration or status endpoint."""
        return {
            "node_id":      self.node_id,
            "alias":        self.alias,
            "version":      self.version,
            "created_at":   self.created_at,
            "hostname":     _safe_hostname(),
            "platform":     platform.system(),
            "arch":         platform.machine(),
            "python":       platform.python_version(),
            "capabilities": list(self.capabilities.keys()),
        }

    def add_capability(self, name: str, description: str = "") -> None:
        """Register an additional capability at runtime."""
        self.capabilities[name] = description
        logger.debug("NodeIdentity: +capability %r", name)

    def remove_capability(self, name: str) -> None:
        """Remove a capability (e.g. when a service fails to start)."""
        self.capabilities.pop(name, None)

    def capability_summary(self) -> dict[str, str]:
        return dict(self.capabilities)

    def __repr__(self) -> str:
        return f"NodeIdentity(id={self.node_id!r}, alias={self.alias!r})"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        data = {
            "node_id":    self.node_id,
            "alias":      self.alias,
            "created_at": self.created_at,
        }
        try:
            with open(self._path, "w") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            logger.warning("NodeIdentity: could not save identity: %s", exc)

    def _load(self) -> dict:
        if not os.path.isfile(self._path):
            return {}
        try:
            with open(self._path) as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("NodeIdentity: could not load identity: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_config_dir() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "config")


def _default_alias() -> str:
    return f"{_safe_hostname()}-aura"


def _safe_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"
