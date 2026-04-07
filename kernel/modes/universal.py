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

import logging

from host_bridge import HostBridge
from kernel.event_bus import Event, Priority

logger = logging.getLogger(__name__)


class UniversalMode:
    """Kernel surface: Universal — host-bridge only, no root."""

    NAME = "universal"

    def __init__(self):
        self._kernel = None
        self._bridge: HostBridge | None = None

    def activate(self, kernel) -> None:
        """Configure the kernel for host-bridge, zero-privilege operation."""
        self._kernel = kernel
        self._bridge = HostBridge()
        self._bridge.set_mode("universal")

        # Register the host-bridge adapters as virtual devices in the HAL
        kernel.hal.register_device("net0",
                                   self._bridge.get_network_adapter())
        kernel.hal.register_device("display0",
                                   self._bridge.get_display_adapter())

        kernel.event_bus.publish(
            Event("MODE_ACTIVATED", payload={"mode": self.NAME},
                  priority=Priority.HIGH, source=self.NAME)
        )
        logger.info("UniversalMode: activated")

    def check_capabilities(self) -> dict:
        """Return the capability set available in Universal mode."""
        if self._bridge is None:
            return {}
        caps = self._bridge.available_capabilities()
        return {c: True for c in caps}

