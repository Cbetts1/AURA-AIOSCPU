"""
Tests — Scheduler
=================
Validates task submission, service registration, and job scheduling.

Covers
------
- Tasks can be submitted and are executed on tick().
- Services can be registered; SERVICE_REGISTERED event is published.
- Jobs are scheduled and called at the right interval.
- PRIORITY_HINT events from AURA alter task ordering.
"""

# TODO: from unittest.mock import MagicMock
# TODO: from kernel.scheduler import Scheduler
# TODO: from kernel.event_bus import EventBus, Event


class TestScheduler:

    def test_instantiation(self):
        """Scheduler accepts an event_bus and initialises cleanly."""
        # TODO: event_bus = MagicMock()
        # TODO: sched = Scheduler(event_bus)
        # TODO: assert sched is not None
        pass

    def test_submit_task_runs_on_tick(self):
        """A submitted task must be called during the next tick()."""
        # TODO: sched = Scheduler(MagicMock())
        # TODO: task = MagicMock()
        # TODO: sched.submit_task(task)
        # TODO: sched.tick()
        # TODO: task.assert_called_once()
        pass

    def test_higher_priority_task_runs_first(self):
        """A task with a lower priority number runs before a higher one."""
        # TODO: order = []
        # TODO: sched.submit_task(lambda: order.append("low"),  priority=9)
        # TODO: sched.submit_task(lambda: order.append("high"), priority=1)
        # TODO: sched.tick(); sched.tick()
        # TODO: assert order == ["high", "low"]
        pass

    def test_register_service_publishes_event(self):
        """register_service() must publish a SERVICE_REGISTERED event."""
        # TODO: event_bus = MagicMock()
        # TODO: sched = Scheduler(event_bus)
        # TODO: sched.register_service("test-svc", MagicMock())
        # TODO: event_bus.publish.assert_called_once()
        # TODO: assert event_bus.publish.call_args[0][0].event_type == "SERVICE_REGISTERED"
        pass

    def test_periodic_job_called_at_interval(self):
        """A scheduled job must be called after its interval has elapsed."""
        # TODO: sched = Scheduler(MagicMock())
        # TODO: job = MagicMock()
        # TODO: sched.schedule_job(job, interval_ms=0)  ← 0ms = run next tick
        # TODO: sched.tick()
        # TODO: job.assert_called_once()
        pass
