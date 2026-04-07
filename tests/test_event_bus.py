"""
Tests — Event Bus
=================
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock
from kernel.event_bus import EventBus, Event, Priority


class TestEventBus:

    def test_subscribe_and_receive(self):
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("TEST_EVENT", handler)
        bus.publish(Event("TEST_EVENT", payload="hello"))
        bus.drain()
        handler.assert_called_once()
        assert handler.call_args[0][0].payload == "hello"

    def test_unsubscribed_type_not_delivered(self):
        bus = EventBus()
        bus.publish(Event("UNKNOWN_TYPE"))
        bus.drain()  # should not raise

    def test_priority_ordering(self):
        bus = EventBus()
        order = []
        bus.subscribe("EVT", lambda e: order.append(e.priority))
        bus.publish(Event("EVT", priority=Priority.LOW))
        bus.publish(Event("EVT", priority=Priority.CRITICAL))
        bus.drain()
        assert order == [Priority.CRITICAL, Priority.LOW]

    def test_subscriber_error_does_not_halt_delivery(self):
        bus = EventBus()
        bad_handler  = MagicMock(side_effect=RuntimeError("boom"))
        good_handler = MagicMock()
        bus.subscribe("EVT", bad_handler)
        bus.subscribe("EVT", good_handler)
        bus.publish(Event("EVT"))
        bus.drain()  # must not raise
        good_handler.assert_called_once()

    def test_drain_clears_queue(self):
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("EVT", handler)
        bus.publish(Event("EVT"))
        bus.drain()
        bus.drain()  # second drain — nothing new published
        assert handler.call_count == 1

    def test_event_attributes(self):
        e = Event("MY_TYPE", payload={"key": "val"},
                  priority=Priority.HIGH, source="test")
        assert e.event_type == "MY_TYPE"
        assert e.payload == {"key": "val"}
        assert e.priority == Priority.HIGH
        assert e.source == "test"
        assert e.timestamp > 0

    def test_event_ordering_by_sequence_when_same_priority(self):
        """Events with the same priority are delivered in publish order."""
        bus = EventBus()
        order = []
        bus.subscribe("E", lambda e: order.append(e.payload))
        bus.publish(Event("E", payload=1, priority=Priority.NORMAL))
        bus.publish(Event("E", payload=2, priority=Priority.NORMAL))
        bus.drain()
        assert order == [1, 2]

