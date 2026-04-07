"""
AURA-AIOSCPU Hardware Abstraction Layer (HAL)
=============================================
Sits between the kernel and all real or virtual hardware.

Abstracts
---------
- vCPU    : virtual processor backed by host thread pool or real CPU cores.
- vMemory : virtual memory regions backed by host memory or mapped files.
- vDevice : virtual devices — network, display, storage (extensible).
- vBus    : virtual bus connecting all registered virtual devices.

All hardware projection (Hardware Mode) is driven through this layer.
The kernel never touches hardware directly — it always goes through HAL.
"""

import logging

logger = logging.getLogger(__name__)


class VBus:
    """Virtual bus — routes messages between registered virtual devices."""

    def __init__(self):
        self._devices: list = []

    def attach(self, device) -> None:
        """Attach a virtual device to the bus."""
        self._devices.append(device)
        logger.debug("VBus: attached device %r", device)

    def detach_all(self) -> None:
        """Remove all attached devices."""
        self._devices.clear()

    def device_count(self) -> int:
        return len(self._devices)


class VMemory:
    """Virtual memory manager — simple expandable region table."""

    def __init__(self):
        self._regions: dict[str, bytearray] = {}

    def allocate(self, name: str, size_bytes: int) -> bytearray:
        """Allocate a named memory region and return it."""
        region = bytearray(size_bytes)
        self._regions[name] = region
        logger.debug("VMemory: allocated %d bytes as %r", size_bytes, name)
        return region

    def free(self, name: str) -> None:
        """Release a named memory region."""
        self._regions.pop(name, None)

    def release_all(self) -> None:
        """Release all regions."""
        self._regions.clear()


class VCPU:
    """Virtual CPU — backed by the host thread pool (stub)."""

    def __init__(self):
        self.running = False

    def start(self) -> None:
        self.running = True
        logger.debug("VCPU: started")

    def stop(self) -> None:
        self.running = False
        logger.debug("VCPU: stopped")


class HAL:
    """Hardware Abstraction Layer — owns all virtual and physical devices."""

    def __init__(self):
        self._vcpu = VCPU()
        self._vmemory = VMemory()
        self._devices: dict[str, object] = {}
        self._vbus = VBus()
        self._projection_active = False

    # ------------------------------------------------------------------
    # Core virtual hardware
    # ------------------------------------------------------------------

    def get_vcpu(self) -> VCPU:
        """Return the virtual CPU interface."""
        return self._vcpu

    def get_vmemory(self) -> VMemory:
        """Return the virtual memory manager."""
        return self._vmemory

    def start(self) -> None:
        """Bring virtual hardware online."""
        self._vcpu.start()
        logger.info("HAL: started")

    def stop(self) -> None:
        """Tear down virtual hardware."""
        self._vcpu.stop()
        self._vmemory.release_all()
        self._vbus.detach_all()
        logger.info("HAL: stopped")

    # ------------------------------------------------------------------
    # Device registry
    # ------------------------------------------------------------------

    def register_device(self, name: str, device) -> None:
        """Register a virtual device and attach it to the vBus."""
        self._devices[name] = device
        self._vbus.attach(device)
        logger.debug("HAL: registered device %r", name)

    def get_device(self, name: str):
        """Look up a registered virtual device by name."""
        return self._devices.get(name)

    # ------------------------------------------------------------------
    # Hardware Projection (Hardware Mode only)
    # ------------------------------------------------------------------

    def enable_projection(self) -> None:
        """Called by Hardware Mode to allow projection."""
        self._projection_active = True

    def project(self, device_spec: dict) -> None:
        """Project a virtual device onto real hardware.

        Only valid when the kernel is in Hardware Projection mode.
        """
        if not self._projection_active:
            raise PermissionError(
                "Hardware projection requires Hardware Mode with explicit "
                "user consent. Call enable_projection() first."
            )
        name = device_spec.get("name", f"dev_{len(self._devices)}")
        logger.info("HAL: projecting device %r → spec=%r", name, device_spec)
        # Stub: register a placeholder for the projected device
        self._devices[name] = device_spec
        self._vbus.attach(device_spec)

    def teardown_all(self) -> None:
        """Remove all projected devices and release hardware resources."""
        self._vbus.detach_all()
        self._devices.clear()
        self._vmemory.release_all()
        self._vcpu.stop()
        self._projection_active = False
        logger.info("HAL: teardown complete")

