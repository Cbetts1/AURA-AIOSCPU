"""
AURA-AIOSCPU Scheduler
=======================
Manages all runnable work in the system.

Responsibilities
----------------
- Tasks   : short-lived, high-priority units of work.
- Services : long-lived background processes loaded from /services.
- Jobs     : deferred / periodic background work.

AURA may influence task priority by publishing a PRIORITY_HINT event on
the event bus; the scheduler subscribes to that event type.
"""

import heapq
import logging
import time

from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)


class _TaskEntry:
    """Wraps a callable so it is orderable in a heapq by priority."""

    _counter = 0

    def __init__(self, priority: int, task):
        _TaskEntry._counter += 1
        self.priority = priority
        self.seq = _TaskEntry._counter
        self.task = task

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.seq < other.seq


class Scheduler:
    """Priority-based task/service/job scheduler."""

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._task_queue: list[_TaskEntry] = []
        self._service_registry: dict[str, object] = {}
        # job entries: [next_run_ts, interval_ms, job_callable]
        self._job_queue: list[list] = []
        self._event_bus.subscribe("PRIORITY_HINT", self._handle_priority_hint)

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def submit_task(self, task, priority: int = 5) -> None:
        """Submit a short-lived task for immediate scheduling.

        Lower priority number = higher urgency (like Unix nice values).
        """
        if not callable(task):
            raise TypeError(f"task must be callable, got {type(task)!r}")
        heapq.heappush(self._task_queue, _TaskEntry(priority, task))

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def register_service(self, name: str, service) -> None:
        """Register a long-lived service object."""
        self._service_registry[name] = service
        self._event_bus.publish(
            Event("SERVICE_REGISTERED", payload={"name": name},
                  priority=Priority.NORMAL, source="scheduler")
        )

    # ------------------------------------------------------------------
    # Background jobs
    # ------------------------------------------------------------------

    def schedule_job(self, job, interval_ms: int) -> None:
        """Schedule a periodic background job.

        interval_ms must be >= 1 to prevent a tight busy-loop.
        """
        if not callable(job):
            raise TypeError(f"job must be callable, got {type(job)!r}")
        if interval_ms < 1:
            raise ValueError("interval_ms must be >= 1")
        next_run = time.monotonic() + interval_ms / 1000.0
        # stored as list so we can mutate next_run in-place
        heapq.heappush(self._job_queue, [next_run, interval_ms, job])

    # ------------------------------------------------------------------
    # Tick (called by KernelLoop each iteration)
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Advance the scheduler by one unit of work."""
        # Run the single highest-priority pending task (if any)
        if self._task_queue:
            entry = heapq.heappop(self._task_queue)
            try:
                entry.task()
            except Exception:
                logger.exception("Scheduler: task raised an exception")

        # Run any periodic jobs whose time has come
        now = time.monotonic()
        while self._job_queue and self._job_queue[0][0] <= now:
            entry = heapq.heappop(self._job_queue)
            next_run, interval_ms, job = entry
            try:
                job()
            except Exception:
                logger.exception("Scheduler: job raised an exception")
            # Re-schedule the job
            entry[0] = now + interval_ms / 1000.0
            heapq.heappush(self._job_queue, entry)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_priority_hint(self, event: Event) -> None:
        """Respond to AURA priority hints (future: re-prioritise tasks)."""
        logger.debug("Scheduler: received PRIORITY_HINT %r", event.payload)

