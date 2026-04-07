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

# TODO: from kernel.event_bus import Event, Priority
# TODO: from hal import HAL


class HardwareMode:
    """Kernel surface: Hardware Projection — explicit consent required."""

    NAME = "hardware"

    def activate(self, kernel, consent_token: str) -> None:
        """Activate hardware projection after verifying user consent.

        Args:
            kernel: The Kernel instance.
            consent_token: Opaque token issued after user consent flow.
        """
        # TODO: verify consent_token is valid and unexpired
        # TODO: initialise HAL hardware projection layer
        # TODO: publish MODE_ACTIVATED event with name=self.NAME
        pass

    def project(self, device_spec: dict) -> None:
        """Project a virtual device onto available hardware.

        Args:
            device_spec: Description of the device to project
                         (type, resources, constraints).
        """
        # TODO: validate device_spec against HAL capabilities
        # TODO: call kernel.hal.project(device_spec)
        # TODO: publish DEVICE_PROJECTED event
        pass

    def revoke(self) -> None:
        """Revoke hardware projection and teardown all projected devices."""
        # TODO: call kernel.hal.teardown_all()
        # TODO: publish PROJECTION_REVOKED event
        # TODO: transition kernel back to Internal or Universal mode
        pass
