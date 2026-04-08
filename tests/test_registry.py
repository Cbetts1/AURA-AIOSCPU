"""
Tests — Service Registry (SSR)
================================
"""

import configparser
import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import EventBus first to break the services → kernel → services circular dependency
from kernel.event_bus import EventBus  # noqa: E402 (must precede services import)

from services.registry import (
    ServiceDescriptor,
    ServiceRegistry,
    ServiceState,
    RestartPolicy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_service_file(directory, filename, content):
    path = os.path.join(directory, filename)
    with open(path, "w") as fh:
        fh.write(content)
    return path


def _minimal_service_file(name="mysvc", module="", auto_start="true",
                           restart_policy="on-failure",
                           depends_on="", description="A service"):
    lines = [
        "[Service]",
        f"Name={name}",
        f"Description={description}",
        f"AutoStart={auto_start}",
        f"RestartPolicy={restart_policy}",
    ]
    if module:
        lines.append(f"Module={module}")
    if depends_on:
        lines.append(f"DependsOn={depends_on}")
    lines += [
        "[Health]",
        "CheckInterval=10",
        "MaxFailures=2",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ServiceDescriptor
# ---------------------------------------------------------------------------

class TestServiceDescriptor:
    def test_defaults(self):
        d = ServiceDescriptor(name="svc")
        assert d.auto_start is True
        assert d.restart_policy == RestartPolicy.ON_FAILURE
        assert d.state == ServiceState.STOPPED
        assert d.failure_count == 0
        assert d.depends_on == []
        assert d.instance is None

    def test_custom_values(self):
        d = ServiceDescriptor(
            name="x",
            description="desc",
            module="services.foo:Foo",
            auto_start=False,
            restart_policy=RestartPolicy.NEVER,
            restart_delay=10.0,
            depends_on=["a", "b"],
        )
        assert d.name == "x"
        assert d.auto_start is False
        assert d.restart_policy == RestartPolicy.NEVER
        assert d.depends_on == ["a", "b"]


# ---------------------------------------------------------------------------
# ServiceRegistry — basics
# ---------------------------------------------------------------------------

class TestServiceRegistryBasics:
    def test_instantiates_without_error(self):
        sr = ServiceRegistry(services_dir="/nonexistent")
        assert sr is not None

    def test_discover_missing_dir_returns_zero(self):
        sr = ServiceRegistry(services_dir="/definitely/does/not/exist")
        count = sr.discover()
        assert count == 0

    def test_list_services_empty_when_no_services(self):
        sr = ServiceRegistry(services_dir="/nonexistent")
        assert sr.list_services() == []

    def test_health_report_empty_dict_when_no_services(self):
        sr = ServiceRegistry(services_dir="/nonexistent")
        assert sr.health_report() == {}

    def test_get_state_unknown_service(self):
        sr = ServiceRegistry(services_dir="/nonexistent")
        assert sr.get_state("ghost") is None


# ---------------------------------------------------------------------------
# ServiceRegistry — discovery
# ---------------------------------------------------------------------------

class TestServiceRegistryDiscovery:
    def test_discovers_valid_service_file(self, tmp_path):
        _write_service_file(tmp_path, "alpha.service",
                            _minimal_service_file("alpha"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        count = sr.discover()
        assert count == 1

    def test_discovers_multiple_service_files(self, tmp_path):
        for name in ("alpha", "beta", "gamma"):
            _write_service_file(tmp_path, f"{name}.service",
                                _minimal_service_file(name))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        count = sr.discover()
        assert count == 3

    def test_ignores_non_service_files(self, tmp_path):
        _write_service_file(tmp_path, "notes.txt", "nothing")
        _write_service_file(tmp_path, "alpha.service",
                            _minimal_service_file("alpha"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        assert sr.discover() == 1

    def test_service_file_without_name_uses_filename(self, tmp_path):
        content = "[Service]\nDescription=desc\n[Health]\nCheckInterval=5\n"
        _write_service_file(tmp_path, "myservice.service", content)
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        services = sr.list_services()
        assert any(s["name"] == "myservice" for s in services)

    def test_list_services_after_discover(self, tmp_path):
        _write_service_file(tmp_path, "svc.service",
                            _minimal_service_file("svc"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        services = sr.list_services()
        assert len(services) == 1
        svc = services[0]
        assert svc["name"] == "svc"
        assert "state" in svc
        assert "auto_start" in svc
        assert "depends_on" in svc

    def test_auto_start_false_parsed(self, tmp_path):
        _write_service_file(tmp_path, "disabled.service",
                            _minimal_service_file("disabled", auto_start="false"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        services = sr.list_services()
        disabled = next(s for s in services if s["name"] == "disabled")
        assert disabled["auto_start"] is False

    def test_restart_policy_never_parsed(self, tmp_path):
        _write_service_file(tmp_path, "never.service",
                            _minimal_service_file("never", restart_policy="never"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        assert sr._registry["never"].restart_policy == RestartPolicy.NEVER

    def test_restart_policy_always_parsed(self, tmp_path):
        _write_service_file(tmp_path, "always.service",
                            _minimal_service_file("always", restart_policy="always"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        assert sr._registry["always"].restart_policy == RestartPolicy.ALWAYS

    def test_depends_on_parsed(self, tmp_path):
        _write_service_file(tmp_path, "child.service",
                            _minimal_service_file("child", depends_on="parent, base"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        assert sr._registry["child"].depends_on == ["parent", "base"]

    def test_malformed_service_file_is_skipped(self, tmp_path):
        # Write a service file that will parse to have an invalid section
        _write_service_file(tmp_path, "bad.service", "THIS IS NOT VALID INI @@##")
        _write_service_file(tmp_path, "good.service",
                            _minimal_service_file("good"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        # Should not raise; good.service should still be loaded
        count = sr.discover()
        assert count >= 1


# ---------------------------------------------------------------------------
# ServiceRegistry — dependency ordering
# ---------------------------------------------------------------------------

class TestServiceRegistryOrdering:
    def test_dependencies_appear_before_dependents(self, tmp_path):
        _write_service_file(tmp_path, "base.service",
                            _minimal_service_file("base"))
        _write_service_file(tmp_path, "mid.service",
                            _minimal_service_file("mid", depends_on="base"))
        _write_service_file(tmp_path, "top.service",
                            _minimal_service_file("top", depends_on="mid"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        order = sr._load_order
        assert order.index("base") < order.index("mid")
        assert order.index("mid") < order.index("top")

    def test_circular_dependency_does_not_raise(self, tmp_path):
        _write_service_file(tmp_path, "a.service",
                            _minimal_service_file("a", depends_on="b"))
        _write_service_file(tmp_path, "b.service",
                            _minimal_service_file("b", depends_on="a"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()  # must not hang or raise

    def test_external_dependency_not_in_registry_is_skipped(self, tmp_path):
        _write_service_file(tmp_path, "child.service",
                            _minimal_service_file("child", depends_on="ghost"))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        assert "child" in sr._load_order


# ---------------------------------------------------------------------------
# ServiceRegistry — lifecycle (no-module services)
# ---------------------------------------------------------------------------

class TestServiceRegistryLifecycle:
    def _make_no_module_sr(self, tmp_path):
        """Create a registry with a single service that has no module (stub)."""
        _write_service_file(tmp_path, "stub.service",
                            _minimal_service_file("stub", module=""))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=EventBus())
        sr.discover()
        return sr

    def test_start_no_module_sets_running(self, tmp_path):
        sr = self._make_no_module_sr(tmp_path)
        ok = sr.start("stub")
        assert ok is True
        assert sr.get_state("stub") == ServiceState.RUNNING

    def test_start_unknown_service_returns_false(self, tmp_path):
        sr = self._make_no_module_sr(tmp_path)
        assert sr.start("ghost") is False

    def test_stop_running_service(self, tmp_path):
        sr = self._make_no_module_sr(tmp_path)
        sr.start("stub")
        # No-module services have no instance, so stop() returns False
        # (there is nothing to call .stop() on).
        ok = sr.stop("stub")
        assert ok is False  # expected: no instance to stop

    def test_stop_already_stopped_returns_false(self, tmp_path):
        sr = self._make_no_module_sr(tmp_path)
        # stub never started — instance is None
        assert sr.stop("stub") is False

    def test_stop_unknown_service_returns_false(self, tmp_path):
        sr = self._make_no_module_sr(tmp_path)
        assert sr.stop("ghost") is False

    def test_restart_service(self, tmp_path):
        sr = self._make_no_module_sr(tmp_path)
        sr.start("stub")
        ok = sr.restart("stub")
        assert ok is True
        assert sr.get_state("stub") == ServiceState.RUNNING

    def test_start_publishes_no_event_for_no_module(self, tmp_path):
        bus = EventBus()
        events = []
        bus.subscribe("SERVICE_STARTED", events.append)
        _write_service_file(tmp_path, "stub.service",
                            _minimal_service_file("stub", module=""))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=bus)
        sr.discover()
        sr.start("stub")
        bus.drain()
        # no-module services do not publish SERVICE_STARTED
        assert len(events) == 0

    def test_start_invalid_module_sets_failed(self, tmp_path):
        _write_service_file(tmp_path, "broken.service",
                            _minimal_service_file("broken",
                                                  module="no.such.module:FakeClass"))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=EventBus())
        sr.discover()
        ok = sr.start("broken")
        assert ok is False
        assert sr.get_state("broken") == ServiceState.FAILED

    def test_failed_service_increments_failure_count(self, tmp_path):
        _write_service_file(tmp_path, "broken.service",
                            _minimal_service_file("broken",
                                                  module="no.such.module:FakeClass"))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=EventBus())
        sr.discover()
        sr.start("broken")
        assert sr._registry["broken"].failure_count == 1

    def test_start_all_autostart(self, tmp_path):
        _write_service_file(tmp_path, "a.service",
                            _minimal_service_file("a", module=""))
        _write_service_file(tmp_path, "b.service",
                            _minimal_service_file("b", module="",
                                                  auto_start="false"))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=EventBus())
        sr.discover()
        started = sr.start_all_autostart()
        assert "a" in started
        assert "b" not in started


# ---------------------------------------------------------------------------
# ServiceRegistry — health report
# ---------------------------------------------------------------------------

class TestServiceRegistryHealth:
    def test_health_report_shows_all_services(self, tmp_path):
        for name in ("x", "y"):
            _write_service_file(tmp_path, f"{name}.service",
                                _minimal_service_file(name, module=""))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        report = sr.health_report()
        assert "x" in report
        assert "y" in report

    def test_health_report_keys(self, tmp_path):
        _write_service_file(tmp_path, "svc.service",
                            _minimal_service_file("svc", module=""))
        sr = ServiceRegistry(services_dir=str(tmp_path))
        sr.discover()
        report = sr.health_report()
        entry = report["svc"]
        assert "state" in entry
        assert "failure_count" in entry
        assert "started_at" in entry

    def test_started_at_recorded_after_start(self, tmp_path):
        _write_service_file(tmp_path, "svc.service",
                            _minimal_service_file("svc", module=""))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=EventBus())
        sr.discover()
        sr.start("svc")
        assert sr.health_report()["svc"]["started_at"] > 0


# ---------------------------------------------------------------------------
# ServiceRegistry — event bus integration
# ---------------------------------------------------------------------------

class TestServiceRegistryEvents:
    def test_service_started_event_published(self, tmp_path):
        bus = EventBus()
        events = []
        bus.subscribe("SERVICE_STARTED", events.append)

        # Use a real module that can be imported and has a start() method
        _write_service_file(tmp_path, "svc.service",
                            _minimal_service_file(
                                "svc",
                                module="services.logging_service:LoggingService"))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=bus)
        sr.discover()
        sr.start("svc")
        bus.drain()
        assert len(events) == 1

    def test_service_failed_event_published(self, tmp_path):
        bus = EventBus()
        events = []
        bus.subscribe("SERVICE_FAILED", events.append)
        _write_service_file(tmp_path, "bad.service",
                            _minimal_service_file("bad",
                                                  module="no.such:Class"))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=bus)
        sr.discover()
        sr.start("bad")
        bus.drain()
        assert len(events) == 1

    def test_service_stopped_event_published(self, tmp_path):
        bus = EventBus()
        stopped_events = []
        bus.subscribe("SERVICE_STOPPED", stopped_events.append)
        _write_service_file(tmp_path, "svc.service",
                            _minimal_service_file(
                                "svc",
                                module="services.logging_service:LoggingService"))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=bus)
        sr.discover()
        sr.start("svc")
        sr.stop("svc")
        bus.drain()
        assert len(stopped_events) == 1

    def test_publish_without_event_bus_does_not_raise(self, tmp_path):
        _write_service_file(tmp_path, "svc.service",
                            _minimal_service_file("svc", module=""))
        sr = ServiceRegistry(services_dir=str(tmp_path), event_bus=None)
        sr.discover()
        sr.start("svc")   # should not raise even with no event bus
