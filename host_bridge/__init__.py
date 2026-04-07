"""
AURA-AIOSCPU Host Bridge
========================
Unified façade for running AURA-AIOSCPU on top of any host OS.

All host interactions MUST go through this module — never call
platform, subprocess, socket, or os.listdir directly in kernel or
service code. Route through HostBridge.syscall() or the adapter objects.

Implementation is delegated to bridge/:
  bridge/android.py — Android / Termux
  bridge/linux.py   — Linux (bare metal, VM, container, WSL)
  bridge/windows.py — Windows / WSL
  bridge/macos.py   — macOS

Three execution modes
---------------------
  Universal  — guest OS on top of host, no root assumed, bridge only
  Internal   — controlled env, manages own prefix, respects host boundaries
  Hardware   — projects onto external hardware via auditable adapters

Contract
--------
  - NEVER hardcode host-specific paths (/tmp, /proc, etc.)
  - NEVER assume root access
  - NEVER bypass the bridge for filesystem or network I/O
  - ALL host-specific behavior is behind capability checks
"""

import logging
import os

from bridge import get_bridge, detect_host_type  # noqa: F401
from bridge.base import HostBridgeBase, BridgeCapability  # noqa: F401

logger = logging.getLogger(__name__)

SUPPORTED_HOSTS = {"linux", "android", "macos", "windows"}

# Syscalls allowed in Universal mode (no root, no escalation)
_UNIVERSAL_ALLOWED = frozenset({
    "fs_read", "fs_write", "fs_list",
    "net_connect", "net_send", "net_recv",
    "proc_spawn", "proc_kill",
    "sys_info",
})

# Additional syscalls in Internal mode (user-granted elevation)
_INTERNAL_ALLOWED = _UNIVERSAL_ALLOWED | frozenset({
    "fs_chmod", "fs_mount_bind",
    "net_listen", "net_raw",
})

# Hardware mode adds projection calls
_HARDWARE_ALLOWED = _INTERNAL_ALLOWED | frozenset({
    "hal_project",
})


# ---------------------------------------------------------------------------
# Adapter classes — wrap bridge for typed, module-specific access
# ---------------------------------------------------------------------------

class HostNetworkAdapter:
    """Virtual network device backed by the host network stack."""

    def __init__(self, bridge: HostBridgeBase):
        self._bridge = bridge

    def connect(self, host: str, port: int):
        """Open a TCP connection through the host bridge."""
        return self._bridge.syscall(BridgeCapability.NET_CONNECT, host, port)

    def __repr__(self):
        return f"HostNetworkAdapter(bridge={self._bridge!r})"


class HostFilesystemAdapter:
    """Virtual filesystem device rooted at a host directory."""

    def __init__(self, root_path: str, bridge: HostBridgeBase):
        self._root   = root_path
        self._bridge = bridge

    def full_path(self, rel: str) -> str:
        return os.path.join(self._root, rel.lstrip("/"))

    def read(self, rel: str) -> bytes:
        path = self.full_path(rel)
        with open(path, "rb") as fh:
            return fh.read()

    def write(self, rel: str, data: bytes) -> None:
        path = self.full_path(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    def list(self, rel: str = "") -> list[str]:
        return self._bridge.syscall(BridgeCapability.FS_LIST,
                                    self.full_path(rel))

    def __repr__(self):
        return f"HostFilesystemAdapter(root={self._root!r})"


class HostDisplayAdapter:
    """Virtual display device — prints to stdout (headless-safe)."""

    def print_line(self, text: str) -> None:
        print(text)

    def __repr__(self):
        return "HostDisplayAdapter(backend=stdout)"


# ---------------------------------------------------------------------------
# HostBridge — public façade
# ---------------------------------------------------------------------------

class HostBridge:
    """
    Unified host-OS bridge façade.

    Wraps the underlying bridge implementation with mode-aware permission
    enforcement and typed virtual device adapters.

    Usage::

        bridge = HostBridge()
        bridge.set_mode("universal")
        bridge.syscall("fs_list", "/home/user")
        net = bridge.get_network_adapter()
    """

    def __init__(self, host_type: str | None = None):
        if host_type is not None and host_type not in SUPPORTED_HOSTS:
            raise ValueError(
                f"Unknown host type {host_type!r}. "
                f"Supported: {sorted(SUPPORTED_HOSTS)}"
            )
        self._bridge    = get_bridge()
        self._host_type = detect_host_type() if host_type is None else host_type
        self._mode      = "universal"
        self._granted_permissions: set[str] = set()
        self._adapters: dict[str, object] = {}
        logger.info("HostBridge: initialised for host=%r mode=%r",
                    self._host_type, self._mode)

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    def set_mode(self, mode: str,
                 granted_permissions: set | None = None) -> None:
        """Called by the kernel mode-activation to configure the bridge."""
        self._mode = mode
        self._granted_permissions = granted_permissions or set()
        self._bridge.set_mode(mode, self._granted_permissions)
        logger.info("HostBridge: mode=%r", mode)

    # ------------------------------------------------------------------
    # Virtual device adapters
    # ------------------------------------------------------------------

    def get_network_adapter(self) -> HostNetworkAdapter:
        if "net" not in self._adapters:
            self._adapters["net"] = HostNetworkAdapter(self._bridge)
        return self._adapters["net"]  # type: ignore[return-value]

    def get_filesystem_adapter(self, root_path: str) -> HostFilesystemAdapter:
        key = f"fs:{root_path}"
        if key not in self._adapters:
            self._adapters[key] = HostFilesystemAdapter(root_path, self._bridge)
        return self._adapters[key]  # type: ignore[return-value]

    def get_display_adapter(self) -> HostDisplayAdapter:
        if "display" not in self._adapters:
            self._adapters["display"] = HostDisplayAdapter()
        return self._adapters["display"]  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Safe path access (routed through bridge — no hardcoded paths)
    # ------------------------------------------------------------------

    def get_temp_dir(self) -> str:
        """Return a guaranteed-writable temp dir for this host."""
        return self._bridge.get_temp_dir()

    def get_home_dir(self) -> str:
        return self._bridge.get_home_dir()

    def get_safe_path(self, *parts: str) -> str:
        return self._bridge.get_safe_path(*parts)

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        """
        Proxy a syscall through the bridge with mode-level enforcement.

        Raises PermissionError if the call exceeds the current mode's
        allowed capability set.
        """
        allowed = self._allowed_for_mode()
        if call not in allowed:
            raise PermissionError(
                f"Syscall {call!r} is not permitted in {self._mode!r} mode."
            )
        logger.debug("HostBridge.syscall: %r args=%r", call, args)
        return self._bridge.syscall(call, *args)

    # ------------------------------------------------------------------
    # Capability query
    # ------------------------------------------------------------------

    def available_capabilities(self) -> set:
        """Return the set of capabilities this host can provide."""
        return set(self._bridge.available_capabilities())

    def get_sys_info(self) -> dict:
        return self._bridge.get_sys_info()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _allowed_for_mode(self) -> frozenset:
        if self._mode == "hardware":
            return _HARDWARE_ALLOWED
        if self._mode == "internal":
            return _INTERNAL_ALLOWED
        return _UNIVERSAL_ALLOWED

