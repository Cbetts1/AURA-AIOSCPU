"""
AURA-AIOSCPU Windows Host Bridge
==================================
Bridge for native Windows and WSL (Windows Subsystem for Linux).

Safe path policy
----------------
Never assumes C:\\Temp, /tmp, or any specific Windows path.
Path discovery order:
  1. %TMPDIR% / %TEMP% / %TMP%
  2. %LOCALAPPDATA%\\aura-tmp
  3. %USERPROFILE%\\.aura-tmp
  4. $HOME/.aura-tmp  (WSL fallback)
  5. $PWD/.aura-tmp   (last resort)

WSL vs native
-------------
When running under WSL, some POSIX paths work but Windows-style env
vars may also be set. We probe both.
"""

import logging
import os
import platform
import socket
import subprocess
from typing import FrozenSet

from bridge.base import HostBridgeBase, BridgeCapability

logger = logging.getLogger(__name__)


def _is_wsl() -> bool:
    try:
        with open("/proc/version") as fh:
            return "microsoft" in fh.read().lower()
    except (OSError, AttributeError):
        return False


class WindowsBridge(HostBridgeBase):
    """Host bridge for native Windows or WSL environments."""

    @classmethod
    def detect(cls) -> bool:
        return platform.system() == "Windows" or _is_wsl()

    def __init__(self):
        super().__init__()
        self._is_wsl  = _is_wsl()
        self._is_native_windows = platform.system() == "Windows"
        self._caps    = self._build_caps()
        logger.info(
            "WindowsBridge: native_win=%s wsl=%s",
            self._is_native_windows, self._is_wsl,
        )

    # ------------------------------------------------------------------
    # Safe paths
    # ------------------------------------------------------------------

    def get_temp_dir(self) -> str:
        """Return a writable temp dir — no hardcoded Windows paths."""
        candidates: list[str] = []

        # Standard env vars (Windows + WSL)
        for var in ("TMPDIR", "TEMP", "TMP"):
            v = os.environ.get(var, "")
            if v:
                candidates.append(v)

        # Windows-specific app data
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidates.append(os.path.join(local_app, "aura-tmp"))

        home = self.get_home_dir()
        candidates.append(os.path.join(home, ".aura-tmp"))

        for path in candidates:
            if self._probe_writable(path):
                return path

        fallback = os.path.join(os.getcwd(), ".aura-tmp")
        os.makedirs(fallback, exist_ok=True)
        return fallback

    def get_home_dir(self) -> str:
        # Windows
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile and os.path.isdir(userprofile):
            return userprofile
        # POSIX / WSL
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
        return frozenset({
            BridgeCapability.FS_READ,
            BridgeCapability.FS_WRITE,
            BridgeCapability.FS_LIST,
            BridgeCapability.NET_CONNECT,
            BridgeCapability.NET_SEND,
            BridgeCapability.NET_RECV,
            BridgeCapability.PROC_SPAWN,
            BridgeCapability.SYS_INFO,
        })

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def get_sys_info(self) -> dict:
        return {
            "host":           "windows",
            "wsl":            self._is_wsl,
            "native_windows": self._is_native_windows,
            "arch":           platform.machine(),
            "release":        platform.release(),
            "python":         platform.python_version(),
            "home":           self.get_home_dir(),
            "tmpdir":         self.get_temp_dir(),
        }

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        if call == "sys_info":
            return self.get_sys_info()
        if call not in self.available_capabilities():
            raise PermissionError(
                f"WindowsBridge: syscall {call!r} not available"
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
        logger.debug("WindowsBridge: unhandled syscall %r", call)
        return None
