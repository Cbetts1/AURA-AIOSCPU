"""
Tests — Service Manager
========================
"""

import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from kernel.event_bus import EventBus
from services import ServiceManager, ServiceState


def _make_sm(tmpdir=None):
    return ServiceManager(EventBus(), services_dir=tmpdir or "/nonexistent")


def _unit(name="svc-a", entrypoint="/services/a.py"):
    return {"name": name, "entrypoint": entrypoint}


class TestServiceManager:

    def test_instantiation(self):
        sm = _make_sm()
        assert sm is not None

    def test_register_publishes_event(self):
        bus = EventBus()
        sm = ServiceManager(bus)
        received = []
        bus.subscribe("SERVICE_REGISTERED", received.append)
        sm.register("svc-a", _unit())
        bus.drain()
        assert len(received) == 1

    def test_status_after_register_is_registered(self):
        sm = _make_sm()
        sm.register("svc-a", _unit())
        assert sm.status("svc-a") == ServiceState.REGISTERED

    def test_status_unknown_service(self):
        sm = _make_sm()
        assert sm.status("no-such-service") == "unknown"

    def test_register_missing_key_raises(self):
        sm = _make_sm()
        with pytest.raises(ValueError):
            sm.register("bad", {"name": "bad"})  # missing "entrypoint"

    def test_discover_missing_dir_does_not_raise(self):
        sm = _make_sm("/definitely/does/not/exist")
        sm.discover()  # should log a warning, not raise

    def test_discover_loads_unit_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            unit_path = os.path.join(tmpdir, "myservice.service")
            with open(unit_path, "w") as f:
                f.write("name = myservice\n")
                f.write("entrypoint = /services/myservice.py\n")
            sm = ServiceManager(EventBus(), services_dir=tmpdir)
            sm.discover()
            assert sm.status("myservice") == ServiceState.REGISTERED

    def test_start_transitions_to_running(self):
        sm = _make_sm()
        sm.register("svc-a", _unit(entrypoint="/nonexistent_stub.py"))
        sm.start("svc-a")
        import time; time.sleep(0.05)
        assert sm.status("svc-a") in (ServiceState.RUNNING, ServiceState.STOPPED)

    def test_start_unknown_service_raises(self):
        sm = _make_sm()
        with pytest.raises(KeyError):
            sm.start("ghost-service")

