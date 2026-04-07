"""
AURA-AIOSCPU Job Queue
========================
Persistent, prioritised job queue with retry logic and lifecycle tracking.

Design
------
- Jobs are submitted with a name, callable, priority, and optional retries.
- The queue is drained by the kernel scheduler on each tick.
- Failed jobs are retried with exponential back-off up to max_retries.
- Completed and failed jobs are kept in a history ring for introspection.
- All state is in-memory; persistence via event bus events.

Priority levels (lower = higher urgency, Unix-style)
-----------------------------------------------------
  0 — CRITICAL   kernel self-repair
  1 — HIGH        system operations
  5 — NORMAL      default
  9 — LOW         background housekeeping

Events published
----------------
  JOB_QUEUED    { name, job_id, priority }
  JOB_STARTED   { name, job_id }
  JOB_COMPLETE  { name, job_id, elapsed_s }
  JOB_FAILED    { name, job_id, attempt, error }
  JOB_RETRYING  { name, job_id, attempt, retry_in_s }
"""

import heapq
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_MAX_HISTORY = 200


@dataclass(order=False)
class Job:
    """One unit of queued work."""
    name:        str
    fn:          Callable
    priority:    int   = 5
    max_retries: int   = 3
    job_id:      str   = field(default_factory=lambda: uuid.uuid4().hex[:8])
    attempts:    int   = 0
    next_run_at: float = field(default_factory=time.monotonic)
    state:       str   = "queued"       # queued | running | done | failed
    error:       str   = ""
    submitted_at: float = field(default_factory=time.time)
    elapsed_s:   float = 0.0

    # heapq ordering: (next_run_at, priority, seq)
    _seq: int = field(default=0)

    def __lt__(self, other: "Job") -> bool:
        if self.next_run_at != other.next_run_at:
            return self.next_run_at < other.next_run_at
        if self.priority != other.priority:
            return self.priority < other.priority
        return self._seq < other._seq

    def to_dict(self) -> dict:
        return {
            "job_id":      self.job_id,
            "name":        self.name,
            "priority":    self.priority,
            "state":       self.state,
            "attempts":    self.attempts,
            "max_retries": self.max_retries,
            "error":       self.error,
            "elapsed_s":   round(self.elapsed_s, 3),
            "submitted_at": self.submitted_at,
        }


class JobQueue:
    """
    Prioritised job queue integrated with the kernel scheduler.

    Usage::

        jq = JobQueue(event_bus, scheduler)
        jq.start()
        job_id = jq.submit("rebuild", lambda: build_system(), priority=1)
        print(jq.status(job_id))
    """

    def __init__(self, event_bus=None, scheduler=None):
        self._event_bus  = event_bus
        self._scheduler  = scheduler
        self._queue: list[Job] = []    # min-heap
        self._active: dict[str, Job] = {}
        self._history: list[Job] = []
        self._max_history = _DEFAULT_MAX_HISTORY
        self._lock  = threading.Lock()
        self._running = False
        self._seq   = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        # Register the drain job with the kernel scheduler (runs every tick)
        if self._scheduler is not None:
            self._scheduler.schedule_job(self._drain_one, interval_ms=100)
        logger.info("JobQueue: started")

    def stop(self) -> None:
        self._running = False
        logger.info("JobQueue: stopped (queued=%d, history=%d)",
                    len(self._queue), len(self._history))

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit(self, name: str, fn: Callable,
               priority: int = 5,
               max_retries: int = 3,
               delay_s: float = 0.0) -> str:
        """
        Submit a job. Returns the job_id string.

        Args:
            name:        Human-readable job name.
            fn:          Callable to run (must not block indefinitely).
            priority:    0–9, lower = higher urgency.
            max_retries: How many times to retry on failure.
            delay_s:     Seconds to wait before first execution.
        """
        self._seq += 1
        job = Job(
            name=name, fn=fn,
            priority=priority,
            max_retries=max_retries,
            next_run_at=time.monotonic() + delay_s,
            _seq=self._seq,
        )
        with self._lock:
            heapq.heappush(self._queue, job)
        self._publish("JOB_QUEUED", {
            "name": name, "job_id": job.job_id, "priority": priority,
        })
        logger.debug("JobQueue: submitted %r id=%s", name, job.job_id)
        return job.job_id

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    def active_count(self) -> int:
        return len(self._active)

    def status(self, job_id: str) -> dict | None:
        """Return status dict for a job by ID (active or history)."""
        if job_id in self._active:
            return self._active[job_id].to_dict()
        for j in self._history:
            if j.job_id == job_id:
                return j.to_dict()
        return None

    def list_pending(self) -> list[dict]:
        with self._lock:
            return [j.to_dict() for j in sorted(self._queue)]

    def list_history(self, limit: int = 50) -> list[dict]:
        return [j.to_dict() for j in self._history[-limit:]]

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel(self, job_id: str) -> bool:
        """Remove a queued job by ID. Returns True if found and cancelled."""
        with self._lock:
            for i, job in enumerate(self._queue):
                if job.job_id == job_id:
                    self._queue.pop(i)
                    heapq.heapify(self._queue)
                    job.state = "cancelled"
                    self._history.append(job)
                    self._trim_history()
                    return True
        return False

    # ------------------------------------------------------------------
    # Internal — drain (called by scheduler every 100ms)
    # ------------------------------------------------------------------

    def _drain_one(self) -> None:
        """Run the next ready job (if any). Called by the scheduler."""
        if not self._running:
            return
        now = time.monotonic()
        with self._lock:
            if not self._queue or self._queue[0].next_run_at > now:
                return
            job = heapq.heappop(self._queue)

        job.state    = "running"
        job.attempts += 1
        self._active[job.job_id] = job
        self._publish("JOB_STARTED", {"name": job.name, "job_id": job.job_id})

        t0 = time.monotonic()
        try:
            job.fn()
            job.elapsed_s = time.monotonic() - t0
            job.state     = "done"
            self._publish("JOB_COMPLETE", {
                "name": job.name, "job_id": job.job_id,
                "elapsed_s": round(job.elapsed_s, 3),
            })
        except Exception as exc:
            job.elapsed_s = time.monotonic() - t0
            job.error     = str(exc)
            logger.warning("JobQueue: job %r failed (attempt %d): %s",
                           job.name, job.attempts, exc)
            if job.attempts < job.max_retries:
                backoff = 2 ** job.attempts
                job.next_run_at = time.monotonic() + backoff
                job.state = "retrying"
                self._publish("JOB_RETRYING", {
                    "name": job.name, "job_id": job.job_id,
                    "attempt": job.attempts, "retry_in_s": backoff,
                })
                with self._lock:
                    heapq.heappush(self._queue, job)
                del self._active[job.job_id]
                return
            else:
                job.state = "failed"
                self._publish("JOB_FAILED", {
                    "name": job.name, "job_id": job.job_id,
                    "attempt": job.attempts, "error": job.error,
                })

        del self._active[job.job_id]
        self._history.append(job)
        self._trim_history()

    def _trim_history(self) -> None:
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def _publish(self, event_type: str, payload: dict) -> None:
        if self._event_bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._event_bus.publish(
                Event(event_type, payload=payload,
                      priority=Priority.NORMAL, source="job_queue")
            )
        except Exception:
            pass
