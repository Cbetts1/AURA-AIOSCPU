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


class HAL:
    """Hardware Abstraction Layer — owns all virtual and physical devices."""

    def __init__(self):
        # TODO: self._vcpu = None          ← vCPU provider instance
        # TODO: self._vmemory = None       ← vMemory manager instance
        # TODO: self._devices = {}         ← {name: device_instance}
        # TODO: self._vbus = None          ← vBus instance
        pass

    # ------------------------------------------------------------------
    # Core virtual hardware
    # ------------------------------------------------------------------

    def get_vcpu(self):
        """Return the virtual CPU interface."""
        # TODO: return self._vcpu
        pass

    def get_vmemory(self):
        """Return the virtual memory manager."""
        # TODO: return self._vmemory
        pass

    # ------------------------------------------------------------------
    # Device registry
    # ------------------------------------------------------------------

    def register_device(self, name: str, device) -> None:
        """Register a virtual device and attach it to the vBus."""
        # TODO: self._devices[name] = device
        # TODO: self._vbus.attach(device)
        pass

    def get_device(self, name: str):
        """Look up a registered virtual device by name."""
        # TODO: return self._devices.get(name)
        pass

    # ------------------------------------------------------------------
    # Hardware Projection (Hardware Mode only)
    # ------------------------------------------------------------------

    def project(self, device_spec: dict) -> None:
        """Project a virtual device onto real hardware.

        Only valid when the kernel is in Hardware Projection mode.
        """
        # TODO: assert Hardware Mode is active
        # TODO: map virtual device spec to a physical device handle
        # TODO: update device registry with projected device
        pass

    def teardown_all(self) -> None:
        """Remove all projected devices and release hardware resources."""
        # TODO: detach all devices from vBus
        # TODO: release all vMemory regions
        # TODO: reset vCPU to idle state
        pass
