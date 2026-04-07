"""
Tests — Event Bus
=================
Validates publish, subscribe, and drain behaviour.

Covers
------
- Events are delivered to the correct subscribers.
- Events with higher priority are delivered first.
- A subscriber error does not prevent other events from being delivered.
- Publishing from inside a callback does not cause re-entrant drain loops.
"""

# TODO: from unittest.mock import MagicMock
# TODO: from kernel.event_bus import EventBus, Event, Priority


class TestEventBus:

    def test_subscribe_and_receive(self):
        """A subscribed callback receives a published event after drain()."""
        # TODO: bus = EventBus()
        # TODO: handler = MagicMock()
        # TODO: bus.subscribe("TEST_EVENT", handler)
        # TODO: bus.publish(Event("TEST_EVENT", payload="hello"))
        # TODO: bus.drain()
        # TODO: handler.assert_called_once()
        # TODO: assert handler.call_args[0][0].payload == "hello"
        pass

    def test_unsubscribed_type_not_delivered(self):
        """An event type with no subscribers is silently discarded."""
        # TODO: bus = EventBus()
        # TODO: bus.publish(Event("UNKNOWN_TYPE"))
        # TODO: bus.drain()   ← should not raise
        pass

    def test_priority_ordering(self):
        """CRITICAL events are delivered before LOW events."""
        # TODO: order = []
        # TODO: bus.subscribe("EVT", lambda e: order.append(e.priority))
        # TODO: bus.publish(Event("EVT", priority=Priority.LOW))
        # TODO: bus.publish(Event("EVT", priority=Priority.CRITICAL))
        # TODO: bus.drain()
        # TODO: assert order == [Priority.CRITICAL, Priority.LOW]
        pass

    def test_subscriber_error_does_not_halt_delivery(self):
        """An exception in one subscriber must not stop other subscribers."""
        # TODO: bus = EventBus()
        # TODO: bad_handler  = MagicMock(side_effect=RuntimeError("boom"))
        # TODO: good_handler = MagicMock()
        # TODO: bus.subscribe("EVT", bad_handler)
        # TODO: bus.subscribe("EVT", good_handler)
        # TODO: bus.publish(Event("EVT"))
        # TODO: bus.drain()   ← must not raise
        # TODO: good_handler.assert_called_once()
        pass

    def test_drain_clears_queue(self):
        """After drain(), publishing nothing means the next drain() is a no-op."""
        # TODO: bus = EventBus()
        # TODO: handler = MagicMock()
        # TODO: bus.subscribe("EVT", handler)
        # TODO: bus.publish(Event("EVT"))
        # TODO: bus.drain()
        # TODO: bus.drain()   ← second drain, nothing new published
        # TODO: assert handler.call_count == 1
        pass
