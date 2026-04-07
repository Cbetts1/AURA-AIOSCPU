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

# TODO: import heapq


class Priority:
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class Event:
    """A single message travelling on the event bus."""

    def __init__(self, event_type: str, payload=None,
                 priority: int = Priority.NORMAL, source: str = ""):
        # TODO: self.event_type = event_type
        # TODO: self.payload = payload
        # TODO: self.priority = priority
        # TODO: self.source = source
        # TODO: self.timestamp = time.time()
        pass

    def __lt__(self, other):
        # Required so Event objects are orderable in a heapq.
        # TODO: return self.priority < other.priority
        pass


class EventBus:
    """In-process publish/subscribe event bus."""

    def __init__(self):
        # TODO: self._subscribers = {}   ← {event_type: [callbacks]}
        # TODO: self._queue = []         ← heapq of (priority, Event)
        pass

    def subscribe(self, event_type: str, callback) -> None:
        """Register a callback for a given event type."""
        # TODO: self._subscribers.setdefault(event_type, []).append(callback)
        pass

    def publish(self, event: Event) -> None:
        """Enqueue an event for delivery on the next drain() call."""
        # TODO: heapq.heappush(self._queue, (event.priority, event))
        pass

    def drain(self) -> None:
        """Deliver all queued events to their subscribers.

        Called once per kernel loop tick. Errors in callbacks are logged
        but do not halt delivery of remaining events.
        """
        # TODO: while self._queue:
        #     _, event = heapq.heappop(self._queue)
        #     for cb in self._subscribers.get(event.event_type, []):
        #         try:
        #             cb(event)
        #         except Exception as exc:
        #             # TODO: log error without crashing the bus
        #             pass
        pass
