"""
AURA-AIOSCPU macOS Host Bridge
================================
Bridge for macOS (Apple Silicon and Intel).

Safe path policy
----------------
macOS sets $TMPDIR per-user to a secure, session-scoped temp directory.
This is used as the primary temp path. Falls back to $HOME/.aura-tmp.

Never assumes /tmp is the right location — while macOS does have /tmp
(as a symlink to /private/tmp), we always prefer $TMPDIR for portability.
"""

import logging
import os
import platform
import socket
import subprocess
from typing import FrozenSet

from bridge.base import HostBridgeBase, BridgeCapability

logger = logging.getLogger(__name__)


def _is_root() -> bool:
    try:
        return os.getuid() == 0
    except AttributeError:
        return False


class MacOSBridge(HostBridgeBase):
    """Host bridge for macOS (Apple Silicon / Intel)."""

    @classmethod
    def detect(cls) -> bool:
        return platform.system() == "Darwin"

    def __init__(self):
        super().__init__()
        self._is_root = _is_root()
        self._caps    = self._build_caps()
        logger.info("MacOSBridge: root=%s arch=%s",
                    self._is_root, platform.machine())

    # ------------------------------------------------------------------
    # Safe paths
    # ------------------------------------------------------------------

    def get_temp_dir(self) -> str:
        """Return a writable temp dir. Prefers $TMPDIR (macOS per-user dir)."""
        # macOS $TMPDIR is reliable and per-user
        t = os.environ.get("TMPDIR", "")
        if t and self._probe_writable(t):
            return t

        # XDG-style fallback
        home = self.get_home_dir()
        fallback = os.path.join(home, ".aura-tmp")
        if self._probe_writable(fallback):
            return fallback

        # Last resort: working directory
        cwd_fallback = os.path.join(os.getcwd(), ".aura-tmp")
        os.makedirs(cwd_fallback, exist_ok=True)
        return cwd_fallback

    def get_home_dir(self) -> str:
        home = os.environ.get("HOME", "")
        if home and os.path.isdir(home):
            return home
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
            BridgeCapability.FS_CHMOD,
            BridgeCapability.NET_LISTEN,
            BridgeCapability.PROC_KILL,
        }
        if self._is_root:
            caps |= {
                BridgeCapability.FS_MOUNT_BIND,
                BridgeCapability.NET_RAW,
            }
        return frozenset(caps)

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def get_sys_info(self) -> dict:
        mac_ver = platform.mac_ver()[0] or platform.release()
        return {
            "host":    "macos",
            "version": mac_ver,
            "arch":    platform.machine(),
            "python":  platform.python_version(),
            "root":    self._is_root,
            "home":    self.get_home_dir(),
            "tmpdir":  self.get_temp_dir(),
        }

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        if call == "sys_info":
            return self.get_sys_info()
        if call not in self.available_capabilities():
            raise PermissionError(
                f"MacOSBridge: syscall {call!r} not available "
                f"(root={self._is_root})"
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
            path = args[0]
            mode = int(args[1], 8) if len(args) > 1 else 0o644
            os.chmod(path, mode)
            return True
        logger.debug("MacOSBridge: unhandled syscall %r", call)
        return None
