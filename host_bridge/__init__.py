"""
AURA-AIOSCPU Host Bridge
========================
Unified API for running AURA-AIOSCPU on top of a host OS.

This is what makes the OS "mirrored" — it can run on top of Android,
Linux, macOS, or Windows by routing all I/O through this bridge rather
than touching hardware directly.

Supported host types (planned)
-------------------------------
  android  — uses Android APIs (JNI / ADB / Termux bridge)
  linux    — uses POSIX + Linux-specific APIs
  macos    — uses POSIX + macOS-specific APIs
  windows  — uses Win32 / WSL bridge

Responsibilities
----------------
- Provide a virtual network adapter backed by the host network stack.
- Provide a virtual filesystem adapter rooted at a host directory.
- Provide a virtual display adapter backed by the host display system.
- Proxy syscalls to the host with permission enforcement.
- Enforce Universal / Internal mode capability boundaries.
"""


class HostBridge:
    """Unified host-OS bridge — one API regardless of underlying OS."""

    def __init__(self, host_type: str = "linux"):
        # TODO: self._host_type = host_type
        # TODO: self._adapters = {}   ← lazily initialised adapters
        pass

    # ------------------------------------------------------------------
    # Virtual device adapters
    # ------------------------------------------------------------------

    def get_network_adapter(self):
        """Return a virtual network device backed by the host network stack."""
        # TODO: return HostNetworkAdapter(self._host_type)
        pass

    def get_filesystem_adapter(self, root_path: str):
        """Return a virtual filesystem device rooted at root_path on the host."""
        # TODO: return HostFilesystemAdapter(root_path, self._host_type)
        pass

    def get_display_adapter(self):
        """Return a virtual display device backed by the host display system."""
        # TODO: return HostDisplayAdapter(self._host_type)
        pass

    # ------------------------------------------------------------------
    # Syscall proxy
    # ------------------------------------------------------------------

    def syscall(self, call: str, *args):
        """Proxy a syscall to the host OS with permission enforcement.

        Raises PermissionError if the call is not permitted in the current
        kernel mode.
        """
        # TODO: check active kernel mode + granted permissions
        # TODO: delegate to self._backend(call, *args)
        # TODO: raise PermissionError for disallowed calls
        pass

    # ------------------------------------------------------------------
    # Capability query
    # ------------------------------------------------------------------

    def available_capabilities(self) -> set:
        """Return the set of capabilities the host can provide."""
        # TODO: introspect host environment
        # TODO: return set of capability strings
        return set()
