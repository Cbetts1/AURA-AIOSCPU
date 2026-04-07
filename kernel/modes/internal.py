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

# TODO: from kernel.event_bus import Event, Priority


class InternalMode:
    """Kernel surface: Internal — elevated host permissions, user-granted."""

    NAME = "internal"

    def activate(self, kernel, granted_permissions: set) -> None:
        """Configure the kernel using permissions the user has granted.

        Args:
            kernel: The Kernel instance.
            granted_permissions: Set of capability strings approved by user.
        """
        # TODO: validate granted_permissions against the known capability list
        # TODO: configure HAL with the subset of elevated capabilities
        # TODO: publish MODE_ACTIVATED event with name=self.NAME
        pass

    def request_permission(self, capability: str) -> None:
        """Ask the user to grant a specific capability at runtime.

        Publishes a PERMISSION_REQUEST event; the shell will surface it to
        the user and publish a PERMISSION_RESPONSE when answered.
        """
        # TODO: publish PERMISSION_REQUEST event with capability payload
        # TODO: (response is handled asynchronously via event bus)
        pass
