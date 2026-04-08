"""
Tests — HealthMonitor + ServiceHealth
=======================================
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import EventBus first to break the services → kernel → services circular dependency
from kernel.event_bus import EventBus  # noqa: E402 (must precede services import)

from services.health_monitor import HealthMonitor, ServiceHealth


# ---------------------------------------------------------------------------
# ServiceHealth unit tests
# ---------------------------------------------------------------------------

class TestServiceHealth:
    def test_initial_state(self):
        h = ServiceHealth("svc-a")
        assert h.name == "svc-a"
        assert h.circuit == ServiceHealth.CLOSED
        assert h.consecutive_failures == 0
        assert h.total_checks == 0
        assert h.total_failures == 0

    def test_record_healthy_resets_consecutive_failures(self):
        h = ServiceHealth("x")
        h.consecutive_failures = 5
        h.circuit = ServiceHealth.OPEN
        h.record_healthy()
        assert h.consecutive_failures == 0
        assert h.circuit == ServiceHealth.CLOSED
        assert h.total_checks == 1

    def test_record_failure_increments_counters(self):
        h = ServiceHealth("x")
        h.record_failure(max_failures=5)
        assert h.consecutive_failures == 1
        assert h.total_failures == 1
        assert h.total_checks == 1

    def test_record_failure_opens_circuit_at_threshold(self):
        h = ServiceHealth("x")
        opened = False
        for _ in range(3):
            opened = h.record_failure(max_failures=3)
        assert opened is True
        assert h.circuit == ServiceHealth.OPEN

    def test_record_failure_does_not_open_circuit_below_threshold(self):
        h = ServiceHealth("x")
        opened = h.record_failure(max_failures=5)
        assert opened is False
        assert h.circuit == ServiceHealth.CLOSED

    def test_circuit_already_open_does_not_re_open(self):
        h = ServiceHealth("x")
        h.circuit = ServiceHealth.OPEN
        opened = h.record_failure(max_failures=1)
        assert opened is False  # circuit was already open

    def test_to_dict_keys(self):
        h = ServiceHealth("svc")
        d = h.to_dict()
        for key in ("circuit", "consecutive_failures", "total_failures",
                    "total_checks", "last_state"):
            assert key in d

    def test_to_dict_values(self):
        h = ServiceHealth("svc")
        h.record_failure(max_failures=10)
        d = h.to_dict()
        assert d["consecutive_failures"] == 1
        assert d["total_failures"] == 1


# ---------------------------------------------------------------------------
# HealthMonitor lifecycle
# ---------------------------------------------------------------------------

class TestHealthMonitorLifecycle:
    def test_instantiates(self):
        hm = HealthMonitor()
        assert hm is not None

    def test_start_stop_no_error(self):
        hm = HealthMonitor(check_interval_s=60)
        hm.start()
        hm.stop()

    def test_start_idempotent(self):
        hm = HealthMonitor(check_interval_s=60)
        hm.start()
        hm.start()
        hm.stop()

    def test_last_report_empty_before_first_check(self):
        hm = HealthMonitor()
        assert hm.last_report() == {}

    def test_all_health_empty_before_checks(self):
        hm = HealthMonitor()
        assert hm.all_health() == {}

    def test_service_health_unknown_returns_none(self):
        hm = HealthMonitor()
        assert hm.service_health("unknown") is None


# ---------------------------------------------------------------------------
# HealthMonitor.run_check_now (synchronous)
# ---------------------------------------------------------------------------

class _FakeRecord:
    """Mimics a ServiceDescriptor for the health monitor."""
    def __init__(self, state="running"):
        self.state = state


class _FakeSvcMgr:
    def __init__(self, registry):
        self._registry = registry

    def stop(self, name):
        rec = self._registry.get(name)
        if rec:
            rec.state = "stopped"
        return True

    def start(self, name):
        rec = self._registry.get(name)
        if rec:
            rec.state = "running"
        return True


class TestHealthMonitorCheckNow:
    def test_run_check_with_all_running(self):
        mgr = _FakeSvcMgr({"a": _FakeRecord("running"),
                            "b": _FakeRecord("running")})
        hm = HealthMonitor(service_manager=mgr, check_interval_s=60)
        report = hm.run_check_now()
        assert report["healthy"] == 2
        assert report["failed"] == 0

    def test_run_check_with_stopped_service(self):
        mgr = _FakeSvcMgr({"a": _FakeRecord("running"),
                            "b": _FakeRecord("stopped")})
        hm = HealthMonitor(service_manager=mgr, check_interval_s=60)
        report = hm.run_check_now()
        assert report["healthy"] == 1
        assert "b" in report["degraded_list"] or "b" in report["failed_list"]

    def test_run_check_no_service_manager_returns_empty(self):
        hm = HealthMonitor(service_manager=None)
        report = hm.run_check_now()
        assert report == {}

    def test_last_report_populated_after_check(self):
        mgr = _FakeSvcMgr({"a": _FakeRecord("running")})
        hm = HealthMonitor(service_manager=mgr, check_interval_s=60)
        hm.run_check_now()
        report = hm.last_report()
        assert "healthy" in report
        assert "timestamp" in report

    def test_service_health_populated_after_check(self):
        mgr = _FakeSvcMgr({"svc-a": _FakeRecord("running")})
        hm = HealthMonitor(service_manager=mgr, check_interval_s=60)
        hm.run_check_now()
        h = hm.service_health("svc-a")
        assert h is not None
        assert h["circuit"] == ServiceHealth.CLOSED

    def test_circuit_opens_after_max_failures(self):
        mgr = _FakeSvcMgr({"bad": _FakeRecord("stopped")})
        hm = HealthMonitor(service_manager=mgr, check_interval_s=60,
                           max_consecutive_failures=3)
        for _ in range(3):
            hm.run_check_now()
        h = hm.service_health("bad")
        assert h["circuit"] == ServiceHealth.OPEN

    def test_report_structure_keys(self):
        mgr = _FakeSvcMgr({"x": _FakeRecord("running")})
        hm = HealthMonitor(service_manager=mgr)
        report = hm.run_check_now()
        for key in ("timestamp", "healthy", "degraded", "failed", "services",
                    "healthy_list", "degraded_list", "failed_list"):
            assert key in report, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# HealthMonitor — event bus integration
# ---------------------------------------------------------------------------

class TestHealthMonitorEvents:
    def test_health_report_event_published(self):
        bus = EventBus()
        events = []
        bus.subscribe("HEALTH_REPORT", events.append)
        mgr = _FakeSvcMgr({"x": _FakeRecord("running")})
        hm = HealthMonitor(event_bus=bus, service_manager=mgr)
        hm.run_check_now()
        bus.drain()
        assert len(events) == 1

    def test_integrity_alert_published_on_circuit_open(self):
        bus = EventBus()
        alerts = []
        bus.subscribe("INTEGRITY_ALERT", alerts.append)
        mgr = _FakeSvcMgr({"bad": _FakeRecord("stopped")})
        hm = HealthMonitor(event_bus=bus, service_manager=mgr,
                           max_consecutive_failures=2)
        for _ in range(2):
            hm.run_check_now()
        bus.drain()
        assert len(alerts) >= 1

    def test_no_event_bus_does_not_raise(self):
        mgr = _FakeSvcMgr({"x": _FakeRecord("running")})
        hm = HealthMonitor(event_bus=None, service_manager=mgr)
        hm.run_check_now()  # should not raise


# ---------------------------------------------------------------------------
# HealthMonitor — repair flow
# ---------------------------------------------------------------------------

class TestHealthMonitorRepair:
    def test_repair_restarts_failed_service(self):
        rec = _FakeRecord("stopped")
        mgr = _FakeSvcMgr({"bad": rec})
        hm = HealthMonitor(service_manager=mgr,
                           max_consecutive_failures=3)
        for _ in range(3):
            hm.run_check_now()
        # After circuit opens, _repair_service should be called (via job queue
        # in production; we call directly here)
        hm._repair_service("bad")
        assert rec.state == "running"

    def test_repair_sets_circuit_half_open(self):
        rec = _FakeRecord("stopped")
        mgr = _FakeSvcMgr({"bad": rec})
        hm = HealthMonitor(service_manager=mgr, max_consecutive_failures=3)
        for _ in range(3):
            hm.run_check_now()
        hm._repair_service("bad")
        h = hm.service_health("bad")
        assert h["circuit"] == ServiceHealth.HALF_OPEN

    def test_repair_no_service_manager_is_noop(self):
        hm = HealthMonitor(service_manager=None)
        hm._repair_service("anything")  # should not raise

    def test_repair_with_job_queue(self):
        """Verify that a job is submitted to the queue when the circuit opens."""
        submitted = []

        class _FakeJobQueue:
            def submit(self, name, fn, priority=5, max_retries=3):
                submitted.append(name)

        rec = _FakeRecord("stopped")
        mgr = _FakeSvcMgr({"bad": rec})
        jq = _FakeJobQueue()
        hm = HealthMonitor(service_manager=mgr, job_queue=jq,
                           max_consecutive_failures=2)
        for _ in range(2):
            hm.run_check_now()
        assert any("bad" in s for s in submitted)
