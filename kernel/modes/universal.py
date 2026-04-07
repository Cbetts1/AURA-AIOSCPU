"""
AURA-AIOSCPU — Universal Mode
==============================
The kernel runs on top of any host OS via a host-bridge.

Constraints
-----------
- No root / admin privileges required.
- All I/O goes through HostBridge adapters (network, display, storage).
- Cannot directly project into physical hardware.
- Cannot access host kernel internals.

This is the default mode when no elevated permissions are available.
"""

# TODO: from host_bridge import HostBridge
# TODO: from kernel.event_bus import Event, Priority


class UniversalMode:
    """Kernel surface: Universal — host-bridge only, no root."""

    NAME = "universal"

    def activate(self, kernel) -> None:
        """Configure the kernel for host-bridge, zero-privilege operation."""
        # TODO: attach HostBridge as the sole HAL backend
        # TODO: configure scheduler for user-space thread constraints
        # TODO: publish MODE_ACTIVATED event with name=self.NAME
        pass

    def check_capabilities(self) -> dict:
        """Return the capability set available in Universal mode.

        Granted : host-bridge IPC, user-space scheduling, virtual devices
        Denied  : raw hardware access, root syscalls, hardware projection
        """
        # TODO: query HostBridge for available host resources
        # TODO: return dict of {capability: bool}
        return {}
