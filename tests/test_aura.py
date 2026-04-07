"""
Tests — AURA
============
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock
from kernel.event_bus import EventBus, Event
from aura import AURA


class TestAURA:

    def _make(self):
        return AURA(EventBus())

    def test_instantiation(self):
        aura = self._make()
        assert aura is not None

    def test_pulse_updates_snapshot(self):
        aura = self._make()
        aura.pulse({"scheduler_depth": 3, "mode": "universal"})
        snapshot = aura.get_state_snapshot()
        assert snapshot.get("scheduler_depth") == 3
        assert snapshot.get("mode") == "universal"

    def test_query_returns_string(self):
        aura = self._make()
        result = aura.query("what is the system status?")
        assert isinstance(result, str)

    def test_snapshot_is_a_copy(self):
        aura = self._make()
        aura.pulse({"key": "original"})
        snap = aura.get_state_snapshot()
        snap["key"] = "mutated"
        assert aura.get_state_snapshot()["key"] == "original"

    def test_system_event_recorded_in_snapshot(self):
        bus = EventBus()
        aura = AURA(bus)
        bus.publish(Event("SERVICE_STARTED", payload={"name": "svc-a"}))
        bus.drain()
        snap = aura.get_state_snapshot()
        assert "last_service_started" in snap
        assert snap["last_service_started"] == {"name": "svc-a"}

    def test_pulse_increments_tick(self):
        aura = self._make()
        aura.pulse({"tick": 1})
        aura.pulse({"tick": 2})
        assert aura.get_state_snapshot()["last_pulse"] == 2

