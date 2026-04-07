"""
AURA-AIOSCPU Android / Termux Host Bridge
==========================================
Implements the HostBridge API for Android devices running Termux.

Capabilities
------------
- Network via standard POSIX sockets (always available in Termux).
- termux-api extras (battery, Wi-Fi info, notifications, clipboard)
  when the ``termux-api`` package is installed.
- Graceful fallback when termux-api is absent.
"""

import json
import logging
import os
import socket
import subprocess

logger = logging.getLogger(__name__)

# Cache: None = not checked yet, True/False = result
_HAS_TERMUX_API: bool | None = None

_TERMUX_COMMANDS: dict[str, list[str]] = {
    "battery":      ["termux-battery-status"],
    "wifi":         ["termux-wifi-connectioninfo"],
    "vibrate":      ["termux-vibrate", "-d", "200"],
    "notification": ["termux-notification"],
    "clipboard_get": ["termux-clipboard-get"],
}


def _has_termux_api() -> bool:
    global _HAS_TERMUX_API
    if _HAS_TERMUX_API is None:
        _HAS_TERMUX_API = (
            subprocess.run(
                ["which", "termux-info"],
                capture_output=True,
            ).returncode == 0
        )
    return _HAS_TERMUX_API


def _run_termux(command: str, *extra_args: str) -> str | None:
    """Run a termux-api command and return stdout, or None on any error."""
    cmd = _TERMUX_COMMANDS.get(command)
    if not cmd:
        return None
    try:
        result = subprocess.run(
            cmd + list(extra_args),
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

class AndroidNetworkAdapter:
    """Virtual network adapter using the Android host TCP/IP stack."""

    def connect(self, host: str, port: int) -> socket.socket:
        sock = socket.create_connection((host, port))
        logger.debug("AndroidNetworkAdapter: connected %s:%d", host, port)
        return sock

    def wifi_info(self) -> dict:
        """Return Wi-Fi connection info (requires termux-api)."""
        if not _has_termux_api():
            return {}
        raw = _run_termux("wifi")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {}

    def __repr__(self):
        return "AndroidNetworkAdapter()"


class AndroidDisplayAdapter:
    """Virtual display adapter — text via stdout, optionally system notification."""

    def print_line(self, text: str) -> None:
        print(text)

    def notify(self, title: str, content: str) -> None:
        """Send an Android system notification if termux-api is available."""
        if _has_termux_api():
            _run_termux("notification", "--title", title, "--content", content)

    def vibrate(self) -> None:
        """Vibrate the device (requires termux-api)."""
        if _has_termux_api():
            _run_termux("vibrate")

    def __repr__(self):
        return "AndroidDisplayAdapter()"


# ---------------------------------------------------------------------------
# AndroidHostBridge
# ---------------------------------------------------------------------------

class AndroidHostBridge:
    """Full host-bridge implementation for Android / Termux."""

    def __init__(self):
        self._has_api = _has_termux_api()
        self._net     = AndroidNetworkAdapter()
        self._display = AndroidDisplayAdapter()
        logger.info("AndroidHostBridge: initialised (termux-api=%s)", self._has_api)

    # ------------------------------------------------------------------
    # Adapter access
    # ------------------------------------------------------------------

    def get_network_adapter(self) -> AndroidNetworkAdapter:
        return self._net

    def get_display_adapter(self) -> AndroidDisplayAdapter:
        return self._display

    # ------------------------------------------------------------------
    # Android-specific queries
    # ------------------------------------------------------------------

    def get_battery_status(self) -> dict:
        if not self._has_api:
            return {}
        raw = _run_termux("battery")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return {}

    def get_clipboard(self) -> str:
        if not self._has_api:
            return ""
        return _run_termux("clipboard_get") or ""

    # ------------------------------------------------------------------
    # Capability query
    # ------------------------------------------------------------------

    def available_capabilities(self) -> set:
        caps = {
            "fs_read", "fs_write", "fs_list",
            "net_connect", "net_send", "net_recv",
            "proc_spawn",
        }
        if self._has_api:
            caps |= {
                "battery_info", "wifi_info", "notification",
                "vibrate", "clipboard",
            }
        return caps

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        if call == "sys_info":
            import platform
            return {
                "os":          "Android",
                "arch":        platform.machine(),
                "termux_api":  self._has_api,
            }
        if call == "battery_info":
            return self.get_battery_status()
        if call == "wifi_info":
            return self._net.wifi_info()
        if call == "fs_list":
            path = args[0] if args else "."
            return os.listdir(path)
        logger.debug("AndroidHostBridge: stub syscall %r", call)
        return None
