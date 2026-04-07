"""
Tests — Shell
=============
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
from kernel.event_bus import EventBus, Event
from aura import AURA
from shell import Shell


def _make_shell():
    bus = EventBus()
    aura = AURA(bus)
    return Shell(aura, bus), aura, bus


class TestShell:

    def test_instantiation(self):
        shell, *_ = _make_shell()
        assert shell is not None

    def test_builtin_help_does_not_call_aura(self):
        shell, aura, _ = _make_shell()
        with patch.object(aura, "query") as mock_query:
            result = shell.dispatch("help")
            mock_query.assert_not_called()
        assert "commands" in result.lower() or "help" in result.lower()

    def test_unknown_input_forwarded_to_aura(self):
        shell, aura, _ = _make_shell()
        with patch.object(aura, "query", return_value="I can help.") as mock_q:
            result = shell.dispatch("what services are running?")
            mock_q.assert_called_once_with("what services are running?")
        assert result == "I can help."

    def test_dispatch_returns_string(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("sysinfo")
        assert isinstance(result, str)

    def test_empty_input_returns_empty_string(self):
        shell, *_ = _make_shell()
        assert shell.dispatch("") == ""
        assert shell.dispatch("   ") == ""

    def test_exit_publishes_shutdown_event(self):
        shell, _, bus = _make_shell()
        received = []
        bus.subscribe("SHUTDOWN", received.append)
        shell.dispatch("exit")
        bus.drain()
        assert len(received) == 1

    def test_status_builtin(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("status")
        assert isinstance(result, str)

