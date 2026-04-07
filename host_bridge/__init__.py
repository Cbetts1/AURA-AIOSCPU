"""
AURA-AIOSCPU Host Bridge
========================
Unified API for running AURA-AIOSCPU on top of a host OS.

This is what makes the OS "mirrored" — it can run on top of Android,
Linux, macOS, or Windows by routing all I/O through this bridge rather
than touching hardware directly.

Supported host types
--------------------
  linux    — POSIX + Linux-specific APIs  (implemented)
  android  — Android/Termux bridge        (implemented)
  macos    — POSIX + macOS APIs           (stub)
  windows  — Win32 / WSL bridge           (stub)

Responsibilities
----------------
- Provide a virtual network adapter backed by the host network stack.
- Provide a virtual filesystem adapter rooted at a host directory.
- Provide a virtual display adapter backed by the host display system.
- Proxy syscalls to the host with permission enforcement.
- Enforce Universal / Internal mode capability boundaries.
- Auto-detect Android / Termux and delegate to AndroidHostBridge.
"""

import logging
import os
import platform
import socket

logger = logging.getLogger(__name__)

SUPPORTED_HOSTS = {"linux", "android", "macos", "windows"}

# Syscalls that are allowed in Universal mode (no root required)
_UNIVERSAL_ALLOWED = {
    "fs_read", "fs_write", "fs_list",
    "net_connect", "net_send", "net_recv",
    "proc_spawn", "proc_kill",
}

# Additional syscalls available in Internal mode (user-granted)
_INTERNAL_ALLOWED = _UNIVERSAL_ALLOWED | {
    "fs_chmod", "fs_mount_bind",
    "net_listen", "net_raw",
    "sys_info",
}


def detect_host_type() -> str:
    """Auto-detect the host OS type, including Android/Termux."""
    # Check for Android / Termux first
    if (
        os.environ.get("TERMUX_VERSION")
        or os.path.exists("/data/data/com.termux")
        or "com.termux" in os.environ.get("HOME", "")
    ):
        return "android"
    system = platform.system().lower()
    if system == "linux":
        return "linux"
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"  # safe default


# ---------------------------------------------------------------------------
# Adapter stubs
# ---------------------------------------------------------------------------

class HostNetworkAdapter:
    """Virtual network device backed by the host network stack."""

    def __init__(self, host_type: str):
        self._host_type = host_type

    def connect(self, host: str, port: int) -> socket.socket:
        """Open a TCP connection through the host network stack."""
        sock = socket.create_connection((host, port))
        logger.debug("HostNetworkAdapter: connected to %s:%d", host, port)
        return sock

    def __repr__(self):
        return f"HostNetworkAdapter(host={self._host_type!r})"


class HostFilesystemAdapter:
    """Virtual filesystem device rooted at a host directory."""

    def __init__(self, root_path: str, host_type: str):
        self._root = root_path
        self._host_type = host_type

    def full_path(self, rel: str) -> str:
        """Resolve a relative path inside this adapter's root."""
        return os.path.join(self._root, rel.lstrip("/"))

    def read(self, rel: str) -> bytes:
        with open(self.full_path(rel), "rb") as fh:
            return fh.read()

    def write(self, rel: str, data: bytes) -> None:
        with open(self.full_path(rel), "wb") as fh:
            fh.write(data)

    def list(self, rel: str = "") -> list[str]:
        return os.listdir(self.full_path(rel))

    def __repr__(self):
        return f"HostFilesystemAdapter(root={self._root!r})"


class HostDisplayAdapter:
    """Virtual display device — stub until a GUI backend is wired in."""

    def __init__(self, host_type: str):
        self._host_type = host_type

    def print_line(self, text: str) -> None:
        """Minimal display: print to stdout."""
        print(text)

    def __repr__(self):
        return f"HostDisplayAdapter(host={self._host_type!r})"


# ---------------------------------------------------------------------------
# HostBridge
# ---------------------------------------------------------------------------

class HostBridge:
    """Unified host-OS bridge — one API regardless of underlying OS."""

    def __init__(self, host_type: str | None = None):
        if host_type is None:
            host_type = detect_host_type()
        if host_type not in SUPPORTED_HOSTS:
            raise ValueError(
                f"Unknown host type {host_type!r}. "
                f"Supported: {SUPPORTED_HOSTS}"
            )
        self._host_type = host_type
        self._mode = "universal"          # updated by kernel mode activation
        self._granted_permissions: set[str] = set()
        self._adapters: dict[str, object] = {}

        # If Android, delegate to the dedicated implementation
        self._android_bridge = None
        if host_type == "android":
            from host_bridge.android import AndroidHostBridge
            self._android_bridge = AndroidHostBridge()

        logger.info("HostBridge: initialised for host=%r", host_type)

    # ------------------------------------------------------------------
    # Mode / permission management
    # ------------------------------------------------------------------

    def set_mode(self, mode: str,
                 granted_permissions: set | None = None) -> None:
        """Called by the kernel mode to configure the bridge."""
        self._mode = mode
        self._granted_permissions = granted_permissions or set()

    # ------------------------------------------------------------------
    # Virtual device adapters
    # ------------------------------------------------------------------

    def get_network_adapter(self) -> HostNetworkAdapter:
        """Return a virtual network device backed by the host network stack."""
        if "net" not in self._adapters:
            self._adapters["net"] = HostNetworkAdapter(self._host_type)
        return self._adapters["net"]  # type: ignore[return-value]

    def get_filesystem_adapter(self, root_path: str) -> HostFilesystemAdapter:
        """Return a virtual filesystem device rooted at root_path."""
        key = f"fs:{root_path}"
        if key not in self._adapters:
            self._adapters[key] = HostFilesystemAdapter(root_path,
                                                        self._host_type)
        return self._adapters[key]  # type: ignore[return-value]

    def get_display_adapter(self) -> HostDisplayAdapter:
        """Return a virtual display device."""
        if "display" not in self._adapters:
            self._adapters["display"] = HostDisplayAdapter(self._host_type)
        return self._adapters["display"]  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        """Proxy a syscall to the host OS with permission enforcement.

        Raises PermissionError if the call is not permitted in the current
        kernel mode.
        """
        allowed = self._allowed_syscalls()
        if call not in allowed:
            raise PermissionError(
                f"Syscall {call!r} is not permitted in "
                f"{self._mode!r} mode."
            )
        logger.debug("HostBridge syscall: %r %r", call, args)
        # Dispatch to host-specific implementations
        return self._dispatch(call, *args)

    # ------------------------------------------------------------------
    # Capability query
    # ------------------------------------------------------------------

    def available_capabilities(self) -> set:
        """Return the set of capabilities the host can provide."""
        if self._android_bridge:
            return self._android_bridge.available_capabilities()
        caps = set(_UNIVERSAL_ALLOWED)
        if self._host_type in ("linux", "macos"):
            caps.add("sys_info")
            caps.add("net_listen")
        return caps

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _allowed_syscalls(self) -> set:
        if self._mode == "hardware":
            return _INTERNAL_ALLOWED | {"hal_project"}
        if self._mode == "internal":
            return _INTERNAL_ALLOWED
        return _UNIVERSAL_ALLOWED

    def _dispatch(self, call: str, *args):
        """Dispatch syscall to Android bridge or generic POSIX handler."""
        if self._android_bridge:
            return self._android_bridge.syscall(call, *args)
        if call == "sys_info":
            return {
                "os":      platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            }
        if call == "fs_list":
            path = args[0] if args else "."
            return os.listdir(path)
        logger.debug("HostBridge: stub dispatch for %r", call)
        return None

