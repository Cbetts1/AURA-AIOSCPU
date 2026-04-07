"""
AURA-AIOSCPU Event Bus
======================
The sole communication channel between: kernel ↔ services ↔ shell ↔ AURA.

Rules
-----
- Any component may publish an event.
- Components subscribe by event type (string).
- Events are delivered in priority order: CRITICAL > HIGH > NORMAL > LOW.
- The kernel loop drains the bus once per tick via drain().
- A subscriber error must never crash the bus.

Standard event types (add more as subsystems are defined)
----------------------------------------------------------
  MODE_ACTIVATED        kernel mode came online
  SERVICE_REGISTERED    a service was registered with the scheduler
  SERVICE_STARTED       a service transitioned to RUNNING
  SERVICE_STOPPED       a service transitioned to STOPPED
  PERMISSION_REQUEST    a component is asking the user for a capability
  PERMISSION_RESPONSE   the user's answer to a PERMISSION_REQUEST
  PRIORITY_HINT         AURA is suggesting a scheduler priority change
  SHUTDOWN              the OS is shutting down
"""

import heapq
import logging
import time

logger = logging.getLogger(__name__)


class Priority:
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class Event:
    """A single message travelling on the event bus."""

    _counter = 0  # tie-breaker so heapq never compares Event objects directly

    def __init__(self, event_type: str, payload=None,
                 priority: int = Priority.NORMAL, source: str = ""):
        self.event_type = event_type
        self.payload = payload
        self.priority = priority
        self.source = source
        self.timestamp = time.time()
        Event._counter += 1
        self._seq = Event._counter

    def __lt__(self, other):
        # heapq is a min-heap: lower priority number = higher urgency
        if self.priority != other.priority:
            return self.priority < other.priority
        return self._seq < other._seq

    def __repr__(self):
        return (f"Event(type={self.event_type!r}, priority={self.priority}, "
                f"source={self.source!r})")


class EventBus:
    """In-process publish/subscribe event bus."""

    def __init__(self):
        self._subscribers: dict[str, list] = {}
        self._queue: list = []  # heapq of Event objects

    def subscribe(self, event_type: str, callback) -> None:
        """Register a callback for a given event type."""
        self._subscribers.setdefault(event_type, []).append(callback)

    def publish(self, event: Event) -> None:
        """Enqueue an event for delivery on the next drain() call."""
        heapq.heappush(self._queue, event)

    def drain(self) -> int:
        """Deliver all queued events to their subscribers.

        Called once per kernel loop tick. Errors in callbacks are logged
        but do not halt delivery of remaining events.

        Returns the number of events dispatched.
        """
        count = 0
        while self._queue:
            event = heapq.heappop(self._queue)
            count += 1
            for cb in list(self._subscribers.get(event.event_type, [])):
                try:
                    cb(event)
                except Exception:
                    logger.exception(
                        "EventBus: subscriber error on event %r", event
                    )
        return count

