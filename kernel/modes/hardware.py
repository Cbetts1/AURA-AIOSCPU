"""
AURA-AIOSCPU — Hardware Projection Mode
========================================
The kernel projects a runtime into external (real or virtual) hardware.

Constraints
-----------
- Requires explicit, revocable user consent before activation.
- All hardware access is mediated by the HAL.
- Consent can be revoked at any time; teardown must be graceful.
- Cannot operate without a valid consent token.

Digital hardware targets: vCPU, vMemory, vDevices, vBus
(real hardware targets are a future extension).
"""

import logging

from host_bridge import HostBridge
from kernel.event_bus import Event, Priority

logger = logging.getLogger(__name__)

# Simple in-memory consent store; replace with secure token service later.
_VALID_TOKENS: set[str] = set()


def issue_consent_token(token: str) -> None:
    """Register a consent token (called during the user consent flow)."""
    _VALID_TOKENS.add(token)


def revoke_consent_token(token: str) -> None:
    """Revoke a previously issued consent token."""
    _VALID_TOKENS.discard(token)


class HardwareMode:
    """Kernel surface: Hardware Projection — explicit consent required."""

    NAME = "hardware"

    def __init__(self):
        self._kernel = None
        self._consent_token: str | None = None
        self._bridge: HostBridge | None = None

    def activate(self, kernel, consent_token: str) -> None:
        """Activate hardware projection after verifying user consent.

        Args:
            kernel: The Kernel instance.
            consent_token: Opaque token issued after user consent flow.
        """
        if consent_token not in _VALID_TOKENS:
            raise PermissionError(
                "Hardware Mode requires a valid consent token. "
                "Complete the user consent flow first."
            )
        self._kernel = kernel
        self._consent_token = consent_token
        self._bridge = HostBridge()
        self._bridge.set_mode("hardware")

        # Enable the HAL's projection capability
        kernel.hal.enable_projection()

        kernel.hal.register_device("net0",
                                   self._bridge.get_network_adapter())
        kernel.hal.register_device("display0",
                                   self._bridge.get_display_adapter())

        kernel.event_bus.publish(
            Event("MODE_ACTIVATED", payload={"mode": self.NAME},
                  priority=Priority.HIGH, source=self.NAME)
        )
        logger.info("HardwareMode: activated")

    def project(self, device_spec: dict) -> None:
        """Project a virtual device onto available hardware.

        Args:
            device_spec: Description of the device to project.
        """
        if self._kernel is None:
            raise RuntimeError("HardwareMode is not active")
        self._kernel.hal.project(device_spec)
        self._kernel.event_bus.publish(
            Event("DEVICE_PROJECTED", payload=device_spec,
                  priority=Priority.NORMAL, source=self.NAME)
        )

    def revoke(self) -> None:
        """Revoke hardware projection and teardown all projected devices."""
        if self._kernel is None:
            return
        self._kernel.hal.teardown_all()
        if self._consent_token:
            revoke_consent_token(self._consent_token)
            self._consent_token = None
        self._kernel.event_bus.publish(
            Event("PROJECTION_REVOKED", payload={"mode": self.NAME},
                  priority=Priority.HIGH, source=self.NAME)
        )
        logger.info("HardwareMode: projection revoked")

