"""
Tests — HAL
===========
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock
from hal import HAL


class TestHAL:

    def test_instantiation(self):
        hal = HAL()
        assert hal is not None

    def test_register_and_get_device(self):
        hal = HAL()
        device = MagicMock()
        hal.register_device("net0", device)
        assert hal.get_device("net0") is device

    def test_get_unknown_device_returns_none(self):
        hal = HAL()
        assert hal.get_device("does-not-exist") is None

    def test_project_without_hardware_mode_raises(self):
        hal = HAL()
        with pytest.raises(PermissionError):
            hal.project({"type": "network", "name": "net1"})

    def test_project_with_projection_enabled(self):
        hal = HAL()
        hal.enable_projection()
        hal.project({"type": "network", "name": "vnet0"})
        assert hal.get_device("vnet0") is not None

    def test_teardown_all_clears_devices(self):
        hal = HAL()
        hal.register_device("net0", MagicMock())
        hal.register_device("disp0", MagicMock())
        hal.teardown_all()
        assert hal.get_device("net0") is None
        assert hal.get_device("disp0") is None

    def test_start_and_stop(self):
        hal = HAL()
        hal.start()
        assert hal.get_vcpu().running is True
        hal.stop()
        assert hal.get_vcpu().running is False

    def test_vmemory_allocate_and_free(self):
        hal = HAL()
        mem = hal.get_vmemory()
        region = mem.allocate("test_region", 1024)
        assert len(region) == 1024
        mem.free("test_region")
        assert "test_region" not in mem._regions

