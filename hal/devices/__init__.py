"""
AURA-AIOSCPU Virtual Device base classes.
"""


class VDevice:
    """Abstract base for all virtual devices registered with the HAL."""

    DEVICE_TYPE: str = "generic"

    def start(self) -> None:
        """Bring the device online."""

    def stop(self) -> None:
        """Take the device offline."""

    def status(self) -> str:
        return "online"
