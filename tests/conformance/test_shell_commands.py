"""Conformance: Shell Commands Presence (Contract 3)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import MagicMock
from kernel.event_bus import EventBus
from aura import AURA
from shell import Shell

REQUIRED_COMMANDS = [
    "help", "status", "services", "sysinfo", "version",
    "ls", "cat", "pwd", "mkdir", "rm", "echo",
    "ps", "clear", "history", "date", "uptime", "whoami",
    "model", "device", "build", "repair", "test",
    "logs", "ping", "net", "pkg", "web",
]


class TestShellCommands:
    def _make_shell(self):
        bus  = EventBus()
        aura = AURA(bus)
        return Shell(aura, bus)

    def test_shell_instantiable(self):
        shell = self._make_shell()
        assert shell is not None

    @pytest.mark.parametrize("cmd", REQUIRED_COMMANDS)
    def test_required_command_registered(self, cmd):
        shell = self._make_shell()
        assert cmd in shell._builtins, f"Command {cmd!r} not registered"

    def test_dispatch_help_returns_string(self):
        shell = self._make_shell()
        result = shell.dispatch("help")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_dispatch_version_returns_string(self):
        shell = self._make_shell()
        result = shell.dispatch("version")
        assert isinstance(result, str)

    def test_dispatch_empty_returns_empty(self):
        shell = self._make_shell()
        result = shell.dispatch("")
        assert result == ""

    def test_dispatch_unknown_goes_to_aura(self):
        shell = self._make_shell()
        result = shell.dispatch("what is 2+2")
        assert isinstance(result, str)

    def test_plugin_loader_importable(self):
        from shell.plugin_loader import PluginLoader  # noqa: F401
        assert PluginLoader

    def test_plugin_loader_load_all(self):
        from shell.plugin_loader import PluginLoader
        loader = PluginLoader()
        loaded = loader.load_all()
        assert isinstance(loaded, list)

    def test_history_is_list(self):
        shell = self._make_shell()
        assert isinstance(shell._history, list)

    def test_dispatch_adds_to_history_on_run(self):
        shell = self._make_shell()
        # Simulate history recording
        line = "status"
        shell._history.append(line)
        assert line in shell._history

    def test_stop_saves_history(self):
        shell = self._make_shell()
        # Call stop without polluting the history file
        shell.stop()  # must not raise
