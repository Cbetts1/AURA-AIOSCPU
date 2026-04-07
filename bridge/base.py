"""
AURA-AIOSCPU Bridge Base
========================
Abstract base class all host bridges must implement.

Contract
--------
Every bridge MUST:
  - implement detect() as a classmethod that returns True iff this bridge
    applies to the current host.
  - never assume /tmp exists or is writable.
  - never hard-code vendor/distro-specific paths.
  - expose get_temp_dir() and get_home_dir() that are GUARANTEED to be
    writable on the current host.
  - expose syscall() as the single point of host I/O.
  - expose available_capabilities() so callers know what they can ask for.

Bridge implementations live in:
  bridge/android.py   — Android / Termux
  bridge/linux.py     — Linux (bare metal, VM, container, WSL)
  bridge/windows.py   — Windows (native Win32 or WSL)
  bridge/macos.py     — macOS (Apple Silicon / Intel)
"""

import abc
import os
from typing import FrozenSet


class BridgeCapability:
    """Well-known capability string constants."""
    # Filesystem
    FS_READ       = "fs_read"
    FS_WRITE      = "fs_write"
    FS_LIST       = "fs_list"
    FS_CHMOD      = "fs_chmod"
    FS_MOUNT_BIND = "fs_mount_bind"
    # Network
    NET_CONNECT   = "net_connect"
    NET_SEND      = "net_send"
    NET_RECV      = "net_recv"
    NET_LISTEN    = "net_listen"
    NET_RAW       = "net_raw"
    # Process
    PROC_SPAWN    = "proc_spawn"
    PROC_KILL     = "proc_kill"
    # System
    SYS_INFO      = "sys_info"
    # Android-specific
    BATTERY_INFO  = "battery_info"
    WIFI_INFO     = "wifi_info"
    NOTIFICATION  = "notification"
    VIBRATE       = "vibrate"
    CLIPBOARD     = "clipboard"


class HostBridgeBase(abc.ABC):
    """
    Abstract base for all host bridges.

    Usage::

        bridge = LinuxBridge()
        tmp = bridge.get_temp_dir()          # guaranteed writable
        info = bridge.get_sys_info()
        bridge.syscall("fs_list", "/home")   # routed through bridge
    """

    def __init__(self):
        self._mode = "universal"
        self._granted_permissions: set[str] = set()

    # ------------------------------------------------------------------
    # Detection (classmethod — called before instantiation)
    # ------------------------------------------------------------------

    @classmethod
    @abc.abstractmethod
    def detect(cls) -> bool:
        """Return True if this bridge applies to the current host."""
        ...

    # ------------------------------------------------------------------
    # Safe path discovery — NEVER assumes /tmp or any specific host path
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def get_temp_dir(self) -> str:
        """
        Return a guaranteed-writable temporary directory.

        Implementations must probe paths in order and verify writeability
        before returning. Must NEVER return /tmp without checking first.
        """
        ...

    @abc.abstractmethod
    def get_home_dir(self) -> str:
        """Return the effective home directory for the current user."""
        ...

    def get_safe_path(self, *parts: str) -> str:
        """
        Build a path rooted under get_temp_dir().

        Creates parent directories as needed. Safe to call from any service.
        """
        path = os.path.join(self.get_temp_dir(), *parts)
        os.makedirs(os.path.dirname(path) or self.get_temp_dir(),
                    exist_ok=True)
        return path

    def get_aura_data_dir(self) -> str:
        """
        Return a persistent, writable data directory for AURA state.

        This is NOT a temp dir — data here survives reboots.
        """
        home = self.get_home_dir()
        path = os.path.join(home, ".aura")
        os.makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Capability query
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def available_capabilities(self) -> FrozenSet[str]:
        """Return the frozen set of capabilities this host provides."""
        ...

    def has_capability(self, cap: str) -> bool:
        """Return True if the named capability is available."""
        return cap in self.available_capabilities()

    # ------------------------------------------------------------------
    # Syscall proxy (ONLY point of host I/O outside the bridge)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def syscall(self, call: str, *args):
        """
        Proxy a host syscall.

        Implementations must validate ``call`` is in available_capabilities()
        before dispatching. Raise PermissionError for disallowed calls.
        """
        ...

    # ------------------------------------------------------------------
    # System information
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def get_sys_info(self) -> dict:
        """
        Return a dict describing the current host environment.

        Minimum required keys: host, arch, python, home, tmpdir
        """
        ...

    # ------------------------------------------------------------------
    # Mode management (called by kernel mode activation)
    # ------------------------------------------------------------------

    def set_mode(self, mode: str,
                 granted_permissions: set | None = None) -> None:
        """Configure the bridge for the active kernel surface mode."""
        self._mode = mode
        self._granted_permissions = granted_permissions or set()

    def get_mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_writable(path: str) -> bool:
        """Return True if path is a writable directory."""
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".aura_write_probe")
            with open(probe, "w") as fh:
                fh.write("1")
            os.unlink(probe)
            return True
        except (OSError, PermissionError):
            return False

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"mode={self._mode!r}, "
            f"caps={len(self.available_capabilities())})"
        )
