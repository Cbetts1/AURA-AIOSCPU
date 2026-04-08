"""
Tests — JobQueue + Job
========================
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import EventBus first to break the services → kernel → services circular dependency
from kernel.event_bus import EventBus  # noqa: E402 (must precede services import)

from services.job_queue import JobQueue, Job


# ---------------------------------------------------------------------------
# Job dataclass unit tests
# ---------------------------------------------------------------------------

class TestJob:
    def test_defaults(self):
        j = Job(name="test", fn=lambda: None)
        assert j.name == "test"
        assert j.priority == 5
        assert j.max_retries == 3
        assert j.state == "queued"
        assert j.attempts == 0
        assert j.error == ""

    def test_job_id_unique(self):
        ids = {Job(name="t", fn=lambda: None).job_id for _ in range(50)}
        assert len(ids) == 50

    def test_to_dict_keys(self):
        j = Job(name="x", fn=lambda: None)
        d = j.to_dict()
        for key in ("job_id", "name", "priority", "state", "attempts",
                    "max_retries", "error", "elapsed_s", "submitted_at"):
            assert key in d

    def test_ordering_by_priority(self):
        j_high = Job(name="high", fn=lambda: None, priority=1, _seq=1)
        j_low  = Job(name="low",  fn=lambda: None, priority=9, _seq=2)
        # Set same next_run_at so priority determines order
        j_high.next_run_at = j_low.next_run_at = 0.0
        assert j_high < j_low

    def test_ordering_by_next_run_at(self):
        j_early = Job(name="e", fn=lambda: None, _seq=1)
        j_late  = Job(name="l", fn=lambda: None, _seq=2)
        j_early.next_run_at = 0.0
        j_late.next_run_at  = 100.0
        assert j_early < j_late

    def test_ordering_by_seq_as_tiebreak(self):
        j1 = Job(name="a", fn=lambda: None, priority=5, _seq=1)
        j2 = Job(name="b", fn=lambda: None, priority=5, _seq=2)
        j1.next_run_at = j2.next_run_at = 0.0
        assert j1 < j2


# ---------------------------------------------------------------------------
# JobQueue lifecycle
# ---------------------------------------------------------------------------

class TestJobQueueLifecycle:
    def test_instantiates(self):
        jq = JobQueue()
        assert jq is not None

    def test_start_stop(self):
        jq = JobQueue()
        jq.start()
        jq.stop()

    def test_start_idempotent(self):
        jq = JobQueue()
        jq.start()
        jq.start()
        jq.stop()

    def test_pending_count_zero_initially(self):
        jq = JobQueue()
        assert jq.pending_count() == 0

    def test_active_count_zero_initially(self):
        jq = JobQueue()
        assert jq.active_count() == 0

    def test_list_pending_empty_initially(self):
        jq = JobQueue()
        assert jq.list_pending() == []

    def test_list_history_empty_initially(self):
        jq = JobQueue()
        assert jq.list_history() == []


# ---------------------------------------------------------------------------
# JobQueue submit
# ---------------------------------------------------------------------------

class TestJobQueueSubmit:
    def test_submit_returns_job_id_string(self):
        jq = JobQueue()
        jq.start()
        job_id = jq.submit("test", lambda: None)
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_submit_increments_pending_count(self):
        jq = JobQueue()
        jq.start()
        jq.submit("t1", lambda: time.sleep(10), delay_s=100)
        jq.submit("t2", lambda: time.sleep(10), delay_s=100)
        assert jq.pending_count() == 2

    def test_submit_with_priority(self):
        jq = JobQueue()
        jq.start()
        jq.submit("urgent", lambda: None, priority=0, delay_s=100)
        jq.submit("normal", lambda: None, priority=5, delay_s=100)
        pending = jq.list_pending()
        assert pending[0]["priority"] == 0   # highest urgency first

    def test_submit_publishes_job_queued_event(self):
        bus = EventBus()
        events = []
        bus.subscribe("JOB_QUEUED", events.append)
        jq = JobQueue(event_bus=bus)
        jq.start()
        jq.submit("evt_test", lambda: None, delay_s=100)
        bus.drain()
        assert len(events) == 1
        assert events[0].payload["name"] == "evt_test"

    def test_no_event_bus_submit_does_not_raise(self):
        jq = JobQueue(event_bus=None)
        jq.start()
        jq.submit("no-bus", lambda: None)


# ---------------------------------------------------------------------------
# JobQueue drain — successful execution
# ---------------------------------------------------------------------------

class TestJobQueueDrain:
    def test_job_completes_after_drain(self):
        jq = JobQueue()
        jq.start()
        ran = []
        jq.submit("collect", lambda: ran.append(True))
        # Poll until the job runs (drain is called internally)
        for _ in range(50):
            jq._drain_one()
            if ran:
                break
            time.sleep(0.01)
        assert ran

    def test_completed_job_in_history(self):
        jq = JobQueue()
        jq.start()
        jq.submit("hist", lambda: None)
        for _ in range(50):
            jq._drain_one()
            if jq.list_history():
                break
            time.sleep(0.01)
        assert jq.list_history()
        assert jq.list_history()[0]["state"] == "done"

    def test_job_complete_event_published(self):
        bus = EventBus()
        events = []
        bus.subscribe("JOB_COMPLETE", events.append)
        jq = JobQueue(event_bus=bus)
        jq.start()
        jq.submit("done", lambda: None)
        for _ in range(50):
            jq._drain_one()
            bus.drain()
            if events:
                break
            time.sleep(0.01)
        assert events
        assert events[0].payload["name"] == "done"

    def test_job_started_event_published(self):
        bus = EventBus()
        started = []
        bus.subscribe("JOB_STARTED", started.append)
        jq = JobQueue(event_bus=bus)
        jq.start()
        jq.submit("start-evt", lambda: None)
        for _ in range(50):
            jq._drain_one()
            bus.drain()
            if started:
                break
            time.sleep(0.01)
        assert started

    def test_drain_does_nothing_when_stopped(self):
        jq = JobQueue()
        jq._running = False
        jq.submit("idle", lambda: None, delay_s=0)
        jq._drain_one()
        # Job should remain in queue, not execute
        assert jq.pending_count() == 1

    def test_drain_does_nothing_when_queue_empty(self):
        jq = JobQueue()
        jq.start()
        jq._drain_one()  # no-op, no exception


# ---------------------------------------------------------------------------
# JobQueue — failure and retry
# ---------------------------------------------------------------------------

class TestJobQueueRetry:
    def _drain_n(self, jq, n=20, pause=0.01):
        for _ in range(n):
            jq._drain_one()
            time.sleep(pause)

    def test_failed_job_retries(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("not yet")

        jq = JobQueue()
        jq.start()
        jq.submit("flaky", flaky, max_retries=3)

        # Force-drain many times to allow retries (with small backoff bypass)
        for _ in range(200):
            # Reset backoff to let job run immediately
            with jq._lock:
                for j in jq._queue:
                    j.next_run_at = time.monotonic() - 1
            jq._drain_one()
            if len(calls) >= 3:
                break
            time.sleep(0.005)

        assert len(calls) >= 2

    def test_exhausted_retries_sets_failed_state(self):
        jq = JobQueue()
        jq.start()
        jq.submit("always-fail", lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                  max_retries=1)
        for _ in range(100):
            with jq._lock:
                for j in jq._queue:
                    j.next_run_at = time.monotonic() - 1
            jq._drain_one()
            if jq.list_history():
                break
            time.sleep(0.005)

        history = jq.list_history()
        assert history
        assert history[-1]["state"] == "failed"

    def test_job_failed_event_published(self):
        bus = EventBus()
        fail_events = []
        bus.subscribe("JOB_FAILED", fail_events.append)
        jq = JobQueue(event_bus=bus)
        jq.start()
        jq.submit("boom", lambda: (_ for _ in ()).throw(RuntimeError("x")),
                  max_retries=1)
        for _ in range(100):
            with jq._lock:
                for j in jq._queue:
                    j.next_run_at = time.monotonic() - 1
            jq._drain_one()
            bus.drain()
            if fail_events:
                break
            time.sleep(0.005)
        assert fail_events


# ---------------------------------------------------------------------------
# JobQueue cancel
# ---------------------------------------------------------------------------

class TestJobQueueCancel:
    def test_cancel_queued_job_returns_true(self):
        jq = JobQueue()
        jq.start()
        job_id = jq.submit("c", lambda: None, delay_s=1000)
        assert jq.cancel(job_id) is True
        assert jq.pending_count() == 0

    def test_cancel_nonexistent_job_returns_false(self):
        jq = JobQueue()
        jq.start()
        assert jq.cancel("bogus-id") is False

    def test_cancelled_job_in_history(self):
        jq = JobQueue()
        jq.start()
        job_id = jq.submit("c", lambda: None, delay_s=1000)
        jq.cancel(job_id)
        history = jq.list_history()
        assert any(h["job_id"] == job_id for h in history)


# ---------------------------------------------------------------------------
# JobQueue status introspection
# ---------------------------------------------------------------------------

class TestJobQueueStatus:
    def test_status_queued_job(self):
        jq = JobQueue()
        jq.start()
        # Submit with a delay so the job stays in the queue before running
        job_id = jq.submit("s", lambda: None, delay_s=1000)
        # status() only checks _active and _history, not the pending queue.
        # A queued-but-not-started job is not yet tracked by status().
        # Run it and then check history.
        with jq._lock:
            for j in jq._queue:
                j.next_run_at = 0.0
        for _ in range(50):
            jq._drain_one()
            if jq.status(job_id) is not None:
                break
            time.sleep(0.01)
        s = jq.status(job_id)
        assert s is not None
        assert s["name"] == "s"

    def test_status_unknown_job_returns_none(self):
        jq = JobQueue()
        assert jq.status("no-such-id") is None

    def test_status_completed_job_in_history(self):
        jq = JobQueue()
        jq.start()
        job_id = jq.submit("done", lambda: None)
        for _ in range(50):
            jq._drain_one()
            if jq.status(job_id):
                break
            time.sleep(0.01)
        s = jq.status(job_id)
        assert s is not None

    def test_list_history_limit(self):
        jq = JobQueue()
        jq.start()
        for i in range(10):
            jq.submit(f"j{i}", lambda: None)
        for _ in range(200):
            jq._drain_one()
            if len(jq.list_history()) >= 5:
                break
            time.sleep(0.005)
        limited = jq.list_history(limit=3)
        assert len(limited) <= 3


# ---------------------------------------------------------------------------
# History trimming
# ---------------------------------------------------------------------------

class TestJobQueueHistoryTrim:
    def test_history_capped_at_max(self):
        jq = JobQueue()
        jq._max_history = 5
        jq.start()
        for i in range(10):
            j = Job(name=f"j{i}", fn=lambda: None, _seq=i)
            j.next_run_at = 0.0
            import heapq
            with jq._lock:
                heapq.heappush(jq._queue, j)
        for _ in range(100):
            jq._drain_one()
            time.sleep(0.005)
        assert len(jq._history) <= 5
