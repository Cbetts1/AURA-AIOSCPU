"""
Tests — HAL (Hardware Abstraction Layer)
=========================================
Validates virtual device registration and the hardware projection contract.

Covers
------
- HAL initialises without error.
- Virtual devices can be registered and retrieved by name.
- project() raises when not in Hardware Mode.
- teardown_all() releases all registered devices.
"""

# TODO: from unittest.mock import MagicMock
# TODO: from hal import HAL


class TestHAL:

    def test_instantiation(self):
        """HAL initialises cleanly with no devices registered."""
        # TODO: hal = HAL()
        # TODO: assert hal is not None
        pass

    def test_register_and_get_device(self):
        """A registered device can be retrieved by name."""
        # TODO: hal = HAL()
        # TODO: device = MagicMock()
        # TODO: hal.register_device("net0", device)
        # TODO: assert hal.get_device("net0") is device
        pass

    def test_get_unknown_device_returns_none(self):
        """Looking up an unregistered device name returns None."""
        # TODO: hal = HAL()
        # TODO: assert hal.get_device("does-not-exist") is None
        pass

    def test_project_without_hardware_mode_raises(self):
        """project() must raise when the kernel is not in Hardware Mode."""
        # TODO: hal = HAL()
        # TODO: with pytest.raises(PermissionError):
        #     hal.project({"type": "network"})
        pass

    def test_teardown_all_clears_devices(self):
        """teardown_all() must remove all registered devices."""
        # TODO: hal = HAL()
        # TODO: hal.register_device("net0", MagicMock())
        # TODO: hal.register_device("disp0", MagicMock())
        # TODO: hal.teardown_all()
        # TODO: assert hal.get_device("net0") is None
        # TODO: assert hal.get_device("disp0") is None
        pass
