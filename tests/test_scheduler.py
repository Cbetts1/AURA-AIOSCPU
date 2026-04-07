"""
Tests — Scheduler
=================
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock
from kernel.event_bus import EventBus, Event
from kernel.scheduler import Scheduler


class TestScheduler:

    def _make(self):
        return Scheduler(EventBus())

    def test_instantiation(self):
        sched = self._make()
        assert sched is not None

    def test_submit_task_runs_on_tick(self):
        sched = self._make()
        task = MagicMock()
        sched.submit_task(task)
        sched.tick()
        task.assert_called_once()

    def test_higher_priority_task_runs_first(self):
        sched = self._make()
        order = []
        sched.submit_task(lambda: order.append("low"),  priority=9)
        sched.submit_task(lambda: order.append("high"), priority=1)
        sched.tick()  # runs "high" (priority=1 < priority=9)
        sched.tick()  # runs "low"
        assert order == ["high", "low"]

    def test_register_service_publishes_event(self):
        bus = EventBus()
        sched = Scheduler(bus)
        received = []
        bus.subscribe("SERVICE_REGISTERED", received.append)
        sched.register_service("test-svc", MagicMock())
        bus.drain()
        assert len(received) == 1
        assert received[0].payload == {"name": "test-svc"}

    def test_periodic_job_called_at_interval(self):
        sched = self._make()
        job = MagicMock()
        sched.schedule_job(job, interval_ms=1)  # 1ms → fire very quickly
        time.sleep(0.01)   # wait for interval to pass
        sched.tick()
        assert job.call_count >= 1

    def test_schedule_job_zero_interval_raises(self):
        sched = self._make()
        with pytest.raises(ValueError):
            sched.schedule_job(lambda: None, interval_ms=0)

    def test_submit_non_callable_raises(self):
        sched = self._make()
        with pytest.raises(TypeError):
            sched.submit_task("not_callable")

    def test_empty_tick_does_not_raise(self):
        sched = self._make()
        sched.tick()  # nothing queued — should not raise

