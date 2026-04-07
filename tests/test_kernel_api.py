"""Unit tests: Kernel API"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock
from kernel.api import KernelAPI
from kernel.permissions import PermissionModel


class TestKernelAPI:
    def _make_api(self, mode="universal"):
        kernel = MagicMock()
        kernel.mode = MagicMock()
        kernel.mode.NAME = mode
        kernel.services = MagicMock()
        kernel.services._registry = {}
        kernel.aura = MagicMock()
        kernel.aura.query = MagicMock(return_value="AURA response")
        kernel.event_bus = MagicMock()
        kernel.scheduler = MagicMock()
        kernel.model_manager = MagicMock()
        kernel.hal = MagicMock()
        pm = PermissionModel(mode=mode)
        return KernelAPI(kernel, pm)

    def test_instantiable(self):
        api = self._make_api()
        assert api is not None

    def test_get_mode(self):
        api = self._make_api("universal")
        assert api.get_mode() == "universal"

    def test_get_status_returns_dict(self):
        api = self._make_api()
        api._kernel.aura.get_state_snapshot.return_value = {"mode": "universal"}
        status = api.sysinfo()
        assert isinstance(status, dict)

    def test_query_aura(self):
        api = self._make_api()
        result = api.aura_query("hello")
        assert isinstance(result, str)

    def test_grant_capability(self):
        api = self._make_api()
        api.grant_capability("net.listen")
        # No exception = success

    def test_list_services(self):
        api = self._make_api()
        services = api.list_services()
        assert isinstance(services, dict)
