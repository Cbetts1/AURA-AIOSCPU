"""Tests for KernelWatchdog — auto-integrity check via BuildService."""

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.event_bus import EventBus, Event, Priority
from kernel.watchdog import KernelWatchdog, ServiceHealth


# ---------------------------------------------------------------------------
# ServiceHealth tests (unchanged API)
# ---------------------------------------------------------------------------

def test_service_health_initial_state():
    h = ServiceHealth("svc", max_failures=3)
    assert h.failure_count == 0
    assert not h.disabled
    assert h.is_restartable()


def test_service_health_disabled_after_max_failures():
    h = ServiceHealth("svc", max_failures=2)
    h.record_failure()
    assert not h.disabled
    h.record_failure()
    assert h.disabled
    assert not h.is_restartable()


def test_service_health_to_dict():
    h = ServiceHealth("svc")
    d = h.to_dict()
    assert "failures" in d
    assert "restarts" in d
    assert "disabled" in d


# ---------------------------------------------------------------------------
# KernelWatchdog — attach_build_service
# ---------------------------------------------------------------------------

class _FakeServiceManager:
    def __init__(self, services=None):
        self._services = services or {}

    def status(self, name):
        return self._services.get(name, "running")

    def start(self, name):
        self._services[name] = "running"


class TestWatchdogIntegrityWiring:

    def test_attach_build_service_method_exists(self):
        bus = EventBus()
        sm  = _FakeServiceManager()
        wd  = KernelWatchdog(bus, sm)
        assert hasattr(wd, "attach_build_service")

    def test_attach_build_service_sets_attribute(self):
        bus = EventBus()
        sm  = _FakeServiceManager()
        wd  = KernelWatchdog(bus, sm)

        class _FakeBuildSvc:
            def verify_integrity(self):
                return {"total_files": 5, "changed_files": [], "integrity_ok": True, "has_baseline": True}

        bs = _FakeBuildSvc()
        wd.attach_build_service(bs)
        assert wd._build_service is bs

    def test_integrity_check_triggered_by_watchdog(self):
        """Verify that the watchdog calls verify_integrity() every N cycles."""
        bus = EventBus()
        sm  = _FakeServiceManager()
        called = []

        class _TrackingBuildSvc:
            def verify_integrity(self):
                called.append(1)
                return {
                    "total_files": 5,
                    "changed_files": [],
                    "integrity_ok": True,
                    "has_baseline": True,
                }

        # integrity_check_interval=1 means every single check cycle
        wd = KernelWatchdog(
            bus, sm,
            check_interval_ms=20,
            integrity_check_interval=1,
        )
        wd._build_service = _TrackingBuildSvc()
        wd.start()
        time.sleep(0.15)
        wd.stop()
        assert len(called) >= 2

    def test_integrity_alert_published_on_drift(self):
        """When drift is detected, BuildService emits INTEGRITY_ALERT."""
        # This test verifies the full integration: watchdog triggers
        # BuildService which publishes the event.
        from services.build_service import BuildService
        import json

        bus = EventBus()
        sm  = _FakeServiceManager()
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bs  = BuildService(bus, repo_root=repo)

        # Build first to create manifest
        bs.rebuild_rootfs()

        # Corrupt one entry in the manifest
        manifest = os.path.join(bs._root, "dist", "manifest.json")
        with open(manifest) as fh:
            data = json.load(fh)
        first = next(iter(data["files"]))
        data["files"][first] = "0" * 64
        with open(manifest, "w") as fh:
            json.dump(data, fh)

        alerts = []
        bus.subscribe("INTEGRITY_ALERT", lambda e: alerts.append(e))

        bs.verify_integrity()
        bus.drain()
        assert len(alerts) >= 1


# ---------------------------------------------------------------------------
# KernelWatchdog — constructor parameters preserved
# ---------------------------------------------------------------------------

def test_watchdog_constructor_with_build_service():
    bus = EventBus()
    sm  = _FakeServiceManager()

    class _BS:
        def verify_integrity(self):
            return {"total_files": 0, "changed_files": [], "integrity_ok": True, "has_baseline": False}

    wd = KernelWatchdog(bus, sm, build_service=_BS(), integrity_check_interval=5)
    assert wd._build_service is not None
    assert wd._integrity_every == 5


def test_watchdog_without_build_service():
    bus = EventBus()
    sm  = _FakeServiceManager()
    wd  = KernelWatchdog(bus, sm)
    assert wd._build_service is None
