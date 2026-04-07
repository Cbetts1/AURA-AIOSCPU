"""
Tests — Kernel Loop
===================
"""

import sys, os, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
from kernel.event_bus import EventBus, Event, Priority
from kernel.scheduler import Scheduler
from kernel.loop import KernelLoop
from aura import AURA


def _make_loop():
    bus = EventBus()
    sched = Scheduler(bus)
    aura = AURA(bus)
    return KernelLoop(sched, bus, aura), bus, sched, aura


class TestKernelLoop:

    def test_instantiation(self):
        loop, *_ = _make_loop()
        assert loop is not None

    def test_stop_before_start_is_safe(self):
        loop, *_ = _make_loop()
        loop.stop()  # should not raise

    def test_run_then_stop(self):
        loop, bus, *_ = _make_loop()
        t = threading.Thread(target=loop.run, daemon=True)
        t.start()
        time.sleep(0.05)
        loop.stop()
        t.join(timeout=1.0)
        assert not t.is_alive()

    def test_shutdown_event_stops_loop(self):
        loop, bus, *_ = _make_loop()
        t = threading.Thread(target=loop.run, daemon=True)
        t.start()
        time.sleep(0.03)
        bus.publish(Event("SHUTDOWN", priority=Priority.CRITICAL))
        t.join(timeout=1.0)
        assert not t.is_alive()

    def test_tick_once_calls_scheduler(self):
        bus = EventBus()
        sched = MagicMock()
        aura = MagicMock()
        loop = KernelLoop(sched, bus, aura)
        loop.tick_once()
        sched.tick.assert_called_once()

    def test_tick_once_pulses_aura_with_dict(self):
        bus = EventBus()
        sched = Scheduler(bus)
        aura = MagicMock()
        loop = KernelLoop(sched, bus, aura)
        loop.tick_once()
        aura.pulse.assert_called_once()
        args = aura.pulse.call_args[0]
        assert isinstance(args[0], dict)

    def test_tick_increments_count(self):
        loop, *_ = _make_loop()
        assert loop.tick_count() == 0
        loop.tick_once()
        loop.tick_once()
        assert loop.tick_count() == 2

