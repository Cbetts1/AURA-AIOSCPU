"""
Tests — Service Manager
========================
Validates service discovery, lifecycle transitions, and event publishing.

Covers
------
- ServiceManager initialises cleanly.
- register() publishes SERVICE_REGISTERED event.
- start() transitions state to RUNNING and publishes SERVICE_STARTED.
- stop() transitions state to STOPPED and publishes SERVICE_STOPPED.
- status() returns the correct state string.
- Discovering from a directory populates the registry.
"""

# TODO: import os, tempfile
# TODO: from unittest.mock import MagicMock
# TODO: from services import ServiceManager, ServiceState


class TestServiceManager:

    def test_instantiation(self):
        """ServiceManager initialises with an event_bus mock."""
        # TODO: sm = ServiceManager(MagicMock())
        # TODO: assert sm is not None
        pass

    def test_register_publishes_event(self):
        """register() must publish a SERVICE_REGISTERED event."""
        # TODO: event_bus = MagicMock()
        # TODO: sm = ServiceManager(event_bus)
        # TODO: sm.register("svc-a", {"name": "svc-a", "entrypoint": "/services/a.py"})
        # TODO: event_bus.publish.assert_called_once()
        # TODO: assert "SERVICE_REGISTERED" in str(event_bus.publish.call_args)
        pass

    def test_status_after_register_is_registered(self):
        """A freshly registered service has state REGISTERED."""
        # TODO: sm = ServiceManager(MagicMock())
        # TODO: sm.register("svc-a", {"name": "svc-a", "entrypoint": "/services/a.py"})
        # TODO: assert sm.status("svc-a") == ServiceState.REGISTERED
        pass

    def test_start_transitions_to_running(self):
        """start() must transition a service from REGISTERED to RUNNING."""
        # TODO: sm = ServiceManager(MagicMock())
        # TODO: sm.register("svc-a", {"name": "svc-a", "entrypoint": "/services/a.py"})
        # TODO: sm.start("svc-a")
        # TODO: assert sm.status("svc-a") == ServiceState.RUNNING
        pass

    def test_stop_transitions_to_stopped(self):
        """stop() must transition a service from RUNNING to STOPPED."""
        # TODO: sm = ServiceManager(MagicMock())
        # TODO: sm.register("svc-a", {"name": "svc-a", "entrypoint": "/services/a.py"})
        # TODO: sm.start("svc-a")
        # TODO: sm.stop("svc-a")
        # TODO: assert sm.status("svc-a") == ServiceState.STOPPED
        pass

    def test_status_unknown_service(self):
        """status() for an unregistered name must return 'unknown'."""
        # TODO: sm = ServiceManager(MagicMock())
        # TODO: assert sm.status("no-such-service") == "unknown"
        pass
