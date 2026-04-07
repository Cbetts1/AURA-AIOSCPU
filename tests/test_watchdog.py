"""Tests for kernel.watchdog — KernelWatchdog self-repair."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.event_bus import EventBus, Event, Priority
from kernel.watchdog import KernelWatchdog, ServiceHealth


# ---------------------------------------------------------------------------
# ServiceHealth unit tests
# ---------------------------------------------------------------------------

def test_service_health_initially_restartable():
    h = ServiceHealth("svc", max_failures=3, backoff_ms=100)
    assert h.is_restartable() is True
    assert h.disabled is False


def test_service_health_disabled_after_max_failures():
    h = ServiceHealth("svc", max_failures=3)
    h.record_failure()
    h.record_failure()
    assert h.disabled is False
    h.record_failure()
    assert h.disabled is True
    assert h.is_restartable() is False


def test_service_health_backoff():
    h = ServiceHealth("svc", max_failures=10, backoff_ms=500)
    h.record_failure()
    # Immediately after failure, backoff not yet elapsed
    assert h.is_restartable() is False


def test_service_health_backoff_elapsed():
    h = ServiceHealth("svc", max_failures=10, backoff_ms=1)
    h.record_failure()
    time.sleep(0.01)  # 10ms > 1ms backoff
    assert h.is_restartable() is True


def test_service_health_to_dict():
    h = ServiceHealth("svc", max_failures=3)
    d = h.to_dict()
    assert "failures"  in d
    assert "restarts"  in d
    assert "disabled"  in d


# ---------------------------------------------------------------------------
# Stub service manager for testing
# ---------------------------------------------------------------------------

class _StubServiceManager:
    def __init__(self):
        self._states: dict[str, str] = {}
        self.restart_calls: list[str] = []

    def status(self, name: str) -> str:
        return self._states.get(name, "unknown")

    def start(self, name: str) -> None:
        self.restart_calls.append(name)
        self._states[name] = "running"

    def set_state(self, name: str, state: str) -> None:
        self._states[name] = state


# ---------------------------------------------------------------------------
# KernelWatchdog tests
# ---------------------------------------------------------------------------

@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def services():
    return _StubServiceManager()


@pytest.fixture
def watchdog(bus, services):
    wd = KernelWatchdog(
        bus, services,
        check_interval_ms=50_000,  # effectively disabled; we call manually
        max_failures=3,
        auto_restart=True,
    )
    return wd


def _register_service(bus: EventBus, watchdog: KernelWatchdog, name: str):
    """Simulate a SERVICE_REGISTERED event so watchdog starts tracking."""
    bus.publish(Event("SERVICE_REGISTERED", payload={"name": name},
                      priority=Priority.NORMAL))
    bus.drain()  # deliver to watchdog subscribers


def test_watchdog_tracks_registered_services(bus, services, watchdog):
    _register_service(bus, watchdog, "my-svc")
    assert "my-svc" in watchdog._health


def test_watchdog_reports_degraded_services(bus, services, watchdog):
    _register_service(bus, watchdog, "svc-a")
    services.set_state("svc-a", "stopped")

    # Manually trigger a check cycle
    watchdog._check_cycle()

    # Health report should reflect the failure
    report = watchdog.get_health_report()
    assert "svc-a" in report


def test_watchdog_auto_restarts_stopped_service(bus, services, watchdog):
    _register_service(bus, watchdog, "svc-b")
    services.set_state("svc-b", "stopped")

    watchdog._check_cycle()

    # Watchdog should have called start() on the service manager
    assert "svc-b" in services.restart_calls


def test_watchdog_no_restart_when_observe_only(bus, services):
    wd = KernelWatchdog(bus, services, check_interval_ms=50_000,
                        auto_restart=False)
    _register_service(bus, wd, "svc-c")
    services.set_state("svc-c", "stopped")
    wd._check_cycle()
    # Should NOT have called start
    assert "svc-c" not in services.restart_calls


def test_watchdog_disables_after_max_failures(bus, services, watchdog):
    _register_service(bus, watchdog, "fragile-svc")
    health = watchdog._health["fragile-svc"]
    for _ in range(3):
        health.record_failure()
    assert health.disabled is True
    # Even if stopped, should not attempt restart
    services.set_state("fragile-svc", "stopped")
    watchdog._check_cycle()
    assert services.restart_calls.count("fragile-svc") == 0


def test_watchdog_get_health_report_empty(bus, services, watchdog):
    report = watchdog.get_health_report()
    assert isinstance(report, dict)


def test_watchdog_health_report_structure(bus, services, watchdog):
    _register_service(bus, watchdog, "reported-svc")
    report = watchdog.get_health_report()
    assert "reported-svc" in report
    svc_report = report["reported-svc"]
    assert "failures"  in svc_report
    assert "restarts"  in svc_report
    assert "disabled"  in svc_report


def test_watchdog_publishes_health_check_event(bus, services, watchdog):
    received = []
    bus.subscribe("HEALTH_CHECK", lambda e: received.append(e))

    _register_service(bus, watchdog, "alive-svc")
    services.set_state("alive-svc", "running")
    watchdog._check_cycle()
    bus.drain()

    assert len(received) >= 1
    assert received[0].event_type == "HEALTH_CHECK"


def test_watchdog_publishes_restarting_event(bus, services, watchdog):
    received = []
    bus.subscribe("SERVICE_RESTARTING", lambda e: received.append(e))

    _register_service(bus, watchdog, "crasher")
    services.set_state("crasher", "stopped")
    watchdog._check_cycle()
    bus.drain()

    assert len(received) >= 1
    assert received[0].payload["name"] == "crasher"


def test_watchdog_start_and_stop():
    bus = EventBus()
    svc = _StubServiceManager()
    wd  = KernelWatchdog(bus, svc, check_interval_ms=10_000)
    wd.start()
    assert wd._running is True
    wd.stop()
    assert wd._running is False
