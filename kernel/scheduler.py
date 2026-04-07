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

# TODO: import heapq (for priority queue)
# TODO: from kernel.event_bus import EventBus


class Scheduler:
    """Priority-based task/service/job scheduler."""

    def __init__(self, event_bus):
        # TODO: self._event_bus = event_bus
        # TODO: self._task_queue = []          ← heapq (priority, task)
        # TODO: self._service_registry = {}    ← {name: service}
        # TODO: self._job_queue = []           ← [(next_run_ts, interval, job)]
        # TODO: subscribe to PRIORITY_HINT events
        pass

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def submit_task(self, task, priority: int = 5) -> None:
        """Submit a short-lived task for immediate scheduling.

        Lower priority number = higher urgency (like Unix nice values).
        """
        # TODO: validate task is callable
        # TODO: heapq.heappush(self._task_queue, (priority, task))
        pass

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    def register_service(self, name: str, service) -> None:
        """Register a long-lived service object."""
        # TODO: add to self._service_registry
        # TODO: publish SERVICE_REGISTERED event
        pass

    # ------------------------------------------------------------------
    # Background jobs
    # ------------------------------------------------------------------

    def schedule_job(self, job, interval_ms: int) -> None:
        """Schedule a periodic background job."""
        # TODO: compute next_run_ts = now() + interval_ms
        # TODO: heapq.heappush(self._job_queue, (next_run_ts, interval_ms, job))
        pass

    # ------------------------------------------------------------------
    # Tick (called by KernelLoop each iteration)
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Advance the scheduler by one unit of work."""
        # TODO: run the highest-priority task from _task_queue (if any)
        # TODO: check _job_queue for jobs whose next_run_ts <= now(); run them
        # TODO: health-check each registered service
        pass
