"""
AURA-AIOSCPU Android / Termux Host Bridge
==========================================
Full bridge for Android devices running under Termux.

Safe path policy
----------------
Android has NO /tmp. Never use it. Safe paths in order:
  1. $TMPDIR        — set by Termux to a valid writable location
  2. $HOME/tmp      — user home tmp fallback
  3. /data/data/com.termux/files/home/tmp  — known Termux home

Capabilities
------------
  Base (always):   fs_read, fs_write, fs_list, net_connect, net_send,
                   net_recv, proc_spawn, sys_info
  With termux-api: battery_info, wifi_info, notification, vibrate, clipboard
"""

import json
import logging
import os
import platform
import socket
import subprocess
from typing import FrozenSet

from bridge.base import HostBridgeBase, BridgeCapability

logger = logging.getLogger(__name__)

_TERMUX_API_COMMANDS: dict[str, list[str]] = {
    "battery":       ["termux-battery-status"],
    "wifi":          ["termux-wifi-connectioninfo"],
    "vibrate":       ["termux-vibrate", "-d", "200"],
    "notification":  ["termux-notification"],
    "clipboard_get": ["termux-clipboard-get"],
}

_TERMUX_API_CHECKED: bool | None = None


def _has_termux_api() -> bool:
    global _TERMUX_API_CHECKED
    if _TERMUX_API_CHECKED is None:
        _TERMUX_API_CHECKED = (
            subprocess.run(
                ["which", "termux-info"],
                capture_output=True,
            ).returncode == 0
        )
    return _TERMUX_API_CHECKED


def _run_termux_cmd(command: str, *extra_args: str) -> str | None:
    """Run a termux-api command and return stdout, or None on any error."""
    cmd = _TERMUX_API_COMMANDS.get(command)
    if cmd is None:
        return None
    try:
        result = subprocess.run(
            cmd + list(extra_args),
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


class AndroidBridge(HostBridgeBase):
    """Host bridge for Android / Termux environments."""

    @classmethod
    def detect(cls) -> bool:
        return (
            bool(os.environ.get("TERMUX_VERSION"))
            or os.path.isdir("/data/data/com.termux")
            or "com.termux" in os.environ.get("HOME", "")
        )

    def __init__(self):
        super().__init__()
        self._has_api = _has_termux_api()
        self._caps    = self._build_caps()
        logger.info("AndroidBridge: initialised (termux-api=%s)", self._has_api)

    # ------------------------------------------------------------------
    # Safe paths — /tmp does NOT exist on Android
    # ------------------------------------------------------------------

    def get_temp_dir(self) -> str:
        """Return a writable temp dir without ever assuming /tmp exists."""
        # $TMPDIR is reliably set by Termux to a valid writable path
        tmpdir = os.environ.get("TMPDIR", "")
        if tmpdir and self._probe_writable(tmpdir):
            return tmpdir

        # HOME/tmp fallback
        home = self.get_home_dir()
        fallback = os.path.join(home, "tmp")
        if self._probe_writable(fallback):
            return fallback

        # Last resort: known Termux path
        known = "/data/data/com.termux/files/home/tmp"
        if self._probe_writable(known):
            return known

        raise RuntimeError("AndroidBridge: no writable temp directory found")

    def get_home_dir(self) -> str:
        home = os.environ.get("HOME", "")
        if home and os.path.isdir(home):
            return home
        # Known Termux home
        known = "/data/data/com.termux/files/home"
        if os.path.isdir(known):
            return known
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
        if self._has_api:
            caps |= {
                BridgeCapability.BATTERY_INFO,
                BridgeCapability.WIFI_INFO,
                BridgeCapability.NOTIFICATION,
                BridgeCapability.VIBRATE,
                BridgeCapability.CLIPBOARD,
            }
        return frozenset(caps)

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def get_sys_info(self) -> dict:
        return {
            "host":       "android",
            "arch":       platform.machine(),
            "python":     platform.python_version(),
            "termux_api": self._has_api,
            "home":       self.get_home_dir(),
            "tmpdir":     self.get_temp_dir(),
        }

    # ------------------------------------------------------------------
    # Android-specific queries
    # ------------------------------------------------------------------

    def get_battery_status(self) -> dict:
        if not self._has_api:
            return {}
        raw = _run_termux_cmd("battery")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {}

    def get_wifi_info(self) -> dict:
        if not self._has_api:
            return {}
        raw = _run_termux_cmd("wifi")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {}

    def get_clipboard(self) -> str:
        if not self._has_api:
            return ""
        return _run_termux_cmd("clipboard_get") or ""

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        if call not in self.available_capabilities() and call != "sys_info":
            raise PermissionError(
                f"AndroidBridge: syscall {call!r} not available on this host"
            )
        if call == "sys_info":
            return self.get_sys_info()
        if call == BridgeCapability.BATTERY_INFO:
            return self.get_battery_status()
        if call == BridgeCapability.WIFI_INFO:
            return self.get_wifi_info()
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
        logger.debug("AndroidBridge: unhandled syscall %r", call)
        return None
