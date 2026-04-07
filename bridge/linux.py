"""
AURA-AIOSCPU Linux Host Bridge
================================
Bridge for Linux environments: bare metal, VM, container, WSL.

Safe path policy
----------------
Never returns /tmp without probing it first.
Path discovery order:
  1. $TMPDIR
  2. $XDG_RUNTIME_DIR/aura-tmp
  3. $HOME/.cache/aura-tmp
  4. /tmp  (last resort — verified writable)
  5. $PWD/.aura-tmp  (absolute fallback)

Container detection
-------------------
Checks /.dockerenv, /run/.containerenv, /proc/1/cgroup for docker/containerd
signatures. Container mode reduces assumed capabilities (no mount, no raw).
"""

import logging
import os
import platform
import socket
import subprocess
from typing import FrozenSet

from bridge.base import HostBridgeBase, BridgeCapability

logger = logging.getLogger(__name__)


def _is_container() -> bool:
    """Best-effort container detection — never raises."""
    try:
        if os.path.exists("/.dockerenv"):
            return True
        if os.path.exists("/run/.containerenv"):
            return True
        with open("/proc/1/cgroup") as fh:
            content = fh.read()
            if "docker" in content or "containerd" in content:
                return True
    except (OSError, PermissionError):
        pass
    return False


def _is_wsl() -> bool:
    """Detect Windows Subsystem for Linux."""
    try:
        with open("/proc/version") as fh:
            return "microsoft" in fh.read().lower()
    except (OSError, AttributeError):
        return False


def _is_root() -> bool:
    try:
        return os.getuid() == 0
    except AttributeError:
        return False


def _detect_distro() -> str:
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except (OSError, PermissionError):
        pass
    return platform.system()


class LinuxBridge(HostBridgeBase):
    """Host bridge for Linux (bare metal, VM, container, WSL)."""

    @classmethod
    def detect(cls) -> bool:
        # Android/Termux uses its own bridge — check first
        if (
            os.environ.get("TERMUX_VERSION")
            or os.path.isdir("/data/data/com.termux")
            or "com.termux" in os.environ.get("HOME", "")
        ):
            return False
        return platform.system() == "Linux"

    def __init__(self):
        super().__init__()
        self._is_root      = _is_root()
        self._is_container = _is_container()
        self._is_wsl       = _is_wsl()
        self._distro       = _detect_distro()
        self._caps         = self._build_caps()
        logger.info(
            "LinuxBridge: distro=%r root=%s container=%s wsl=%s",
            self._distro, self._is_root, self._is_container, self._is_wsl,
        )

    # ------------------------------------------------------------------
    # Safe paths
    # ------------------------------------------------------------------

    def get_temp_dir(self) -> str:
        """Find a writable temp dir — probes multiple candidates."""
        candidates: list[str] = []

        t = os.environ.get("TMPDIR", "")
        if t:
            candidates.append(t)

        xdg = os.environ.get("XDG_RUNTIME_DIR", "")
        if xdg:
            candidates.append(os.path.join(xdg, "aura-tmp"))

        home = os.environ.get("HOME", "")
        if home:
            candidates.append(os.path.join(home, ".cache", "aura-tmp"))

        # /tmp last — verify it's actually writable
        candidates.append("/tmp")

        for path in candidates:
            if self._probe_writable(path):
                return path

        # Absolute fallback: use working directory
        fallback = os.path.join(os.getcwd(), ".aura-tmp")
        os.makedirs(fallback, exist_ok=True)
        return fallback

    def get_home_dir(self) -> str:
        home = os.environ.get("HOME", "")
        if home and os.path.isdir(home):
            return home
        try:
            import pwd
            return pwd.getpwuid(os.getuid()).pw_dir
        except Exception:
            return os.getcwd()

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def available_capabilities(self) -> FrozenSet[str]:
        return self._caps

    def _build_caps(self) -> FrozenSet[str]:
        caps = {
            BridgeCapability.FS_READ,
            BridgeCapability.FS_WRITE,
            BridgeCapability.FS_LIST,
            BridgeCapability.NET_CONNECT,
            BridgeCapability.NET_SEND,
            BridgeCapability.NET_RECV,
            BridgeCapability.PROC_SPAWN,
            BridgeCapability.SYS_INFO,
        }
        if self._is_root:
            caps |= {
                BridgeCapability.FS_CHMOD,
                BridgeCapability.FS_MOUNT_BIND,
                BridgeCapability.NET_LISTEN,
                BridgeCapability.NET_RAW,
                BridgeCapability.PROC_KILL,
            }
        elif not self._is_container:
            caps |= {
                BridgeCapability.FS_CHMOD,
                BridgeCapability.NET_LISTEN,
                BridgeCapability.PROC_KILL,
            }
        return frozenset(caps)

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def get_sys_info(self) -> dict:
        return {
            "host":      "linux",
            "distro":    self._distro,
            "arch":      platform.machine(),
            "release":   platform.release(),
            "python":    platform.python_version(),
            "root":      self._is_root,
            "container": self._is_container,
            "wsl":       self._is_wsl,
            "home":      self.get_home_dir(),
            "tmpdir":    self.get_temp_dir(),
        }

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        if call == "sys_info":
            return self.get_sys_info()
        if call not in self.available_capabilities():
            raise PermissionError(
                f"LinuxBridge: syscall {call!r} not available "
                f"(root={self._is_root}, container={self._is_container})"
            )
        if call == BridgeCapability.FS_LIST:
            path = args[0] if args else self.get_home_dir()
            return os.listdir(path)
        if call == BridgeCapability.NET_CONNECT:
            host, port = args[0], int(args[1])
            return socket.create_connection((host, port))
        if call == BridgeCapability.PROC_SPAWN:
            cmd = args[0] if args else []
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
        if call == BridgeCapability.FS_CHMOD:
            path, mode = args[0], int(args[1], 8) if len(args) > 1 else 0o644
            os.chmod(path, mode)
            return True
        logger.debug("LinuxBridge: unhandled syscall %r", call)
        return None
