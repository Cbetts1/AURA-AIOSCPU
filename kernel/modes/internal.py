"""
AURA-AIOSCPU — Internal Mode
=============================
The kernel runs inside a host OS with user-granted elevated permissions.

Constraints
-----------
- Every elevated capability requires explicit user consent.
- Permissions are granted at runtime, not hardcoded.
- Cannot escalate to Hardware Projection without switching mode.

This mode is used when AURA-AIOSCPU runs as an app or daemon inside
an existing OS (e.g. Android, Linux) with elevated access.
"""

import logging

from host_bridge import HostBridge
from kernel.event_bus import Event, Priority

logger = logging.getLogger(__name__)


class InternalMode:
    """Kernel surface: Internal — elevated host permissions, user-granted."""

    NAME = "internal"

    def __init__(self):
        self._kernel = None
        self._bridge: HostBridge | None = None

    def activate(self, kernel, granted_permissions: set | None = None) -> None:
        """Configure the kernel using permissions the user has granted.

        Args:
            kernel: The Kernel instance.
            granted_permissions: Set of capability strings approved by user.
        """
        self._kernel = kernel
        granted = granted_permissions or set()
        self._bridge = HostBridge()
        self._bridge.set_mode("internal", granted)

        kernel.hal.register_device("net0",
                                   self._bridge.get_network_adapter())
        kernel.hal.register_device("display0",
                                   self._bridge.get_display_adapter())

        kernel.event_bus.publish(
            Event("MODE_ACTIVATED",
                  payload={"mode": self.NAME,
                           "permissions": list(granted)},
                  priority=Priority.HIGH, source=self.NAME)
        )
        logger.info("InternalMode: activated with permissions=%r", granted)

    def request_permission(self, capability: str) -> None:
        """Ask the user to grant a specific capability at runtime.

        Publishes a PERMISSION_REQUEST event; the shell will surface it to
        the user and publish a PERMISSION_RESPONSE when answered.
        """
        if self._kernel is None:
            return
        self._kernel.event_bus.publish(
            Event("PERMISSION_REQUEST",
                  payload={"capability": capability},
                  priority=Priority.HIGH, source=self.NAME)
        )
        logger.info("InternalMode: requested permission for %r", capability)

