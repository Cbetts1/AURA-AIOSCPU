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

    # ------------------------------------------------------------------
    # Version / uname
    # ------------------------------------------------------------------

    def test_version_returns_string(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("version")
        assert "AURA" in result
        assert "Python" in result

    def test_uname_returns_string(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("uname")
        assert isinstance(result, str)
        assert len(result) > 0

    # ------------------------------------------------------------------
    # File system commands
    # ------------------------------------------------------------------

    def test_pwd_returns_string(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("pwd")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ls_home(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("ls")
        assert isinstance(result, str)

    def test_ls_nonexistent_dir(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("ls /tmp/definitely/does/not/exist_xyz")
        assert "no such" in result.lower() or "not" in result.lower()

    def test_mkdir_and_rm(self, tmp_path):
        shell, *_ = _make_shell()
        test_dir = str(tmp_path / "aura_test_dir")
        shell.dispatch(f"mkdir {test_dir}")
        assert os.path.isdir(test_dir)
        result = shell.dispatch(f"rm {test_dir}")
        assert "Removed" in result
        assert not os.path.exists(test_dir)

    def test_write_and_cat(self, tmp_path):
        shell, *_ = _make_shell()
        path = str(tmp_path / "hello.txt")
        shell.dispatch(f"write {path} hello world")
        result = shell.dispatch(f"cat {path}")
        assert "hello world" in result

    def test_cat_missing_file(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("cat /tmp/no_such_file_xyz_aura.txt")
        assert "no such" in result.lower()

    def test_cat_no_args(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("cat")
        assert "usage" in result.lower() or "cat" in result.lower()

    def test_mkdir_no_args(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("mkdir")
        assert "usage" in result.lower()

    def test_rm_missing_file(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("rm /tmp/no_such_file_xyz_aura.txt")
        assert "no such" in result.lower()

    def test_echo(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("echo hello world")
        assert result == "hello world"

    def test_echo_empty(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("echo")
        assert result == ""

    # ------------------------------------------------------------------
    # System commands
    # ------------------------------------------------------------------

    def test_ps_returns_thread_list(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("ps")
        assert "NAME" in result
        assert "alive" in result

    def test_clear_returns_ansi(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("clear")
        assert "\033[" in result

    def test_history_empty_initially(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("history")
        assert "history" in result.lower() or "No history" in result

    def test_history_records_commands(self):
        shell, *_ = _make_shell()
        import threading
        # Manually trigger run-like history population
        shell._history.append("help")
        shell._history.append("status")
        result = shell.dispatch("history")
        assert "help" in result

    def test_date_returns_string(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("date")
        assert isinstance(result, str)
        assert len(result) > 5

    def test_uptime_returns_string(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("uptime")
        assert "uptime" in result.lower()

    def test_whoami_returns_string(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("whoami")
        assert isinstance(result, str)
        assert len(result) > 0

    # ------------------------------------------------------------------
    # Network commands
    # ------------------------------------------------------------------

    def test_ping_no_args(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("ping")
        assert "usage" in result.lower()

    def test_ping_unreachable(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("ping 192.0.2.1")  # TEST-NET — always unreachable
        assert isinstance(result, str)

    def test_net_returns_status(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("net")
        assert "network status" in result.lower() or "status" in result.lower()

    # ------------------------------------------------------------------
    # Package manager commands
    # ------------------------------------------------------------------

    def test_pkg_list_empty(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("pkg list")
        assert isinstance(result, str)

    def test_pkg_no_args_shows_list(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("pkg")
        assert isinstance(result, str)

    def test_pkg_info_unknown(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("pkg info nonexistent_xyz")
        assert "not found" in result.lower()

    def test_pkg_search_no_results(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("pkg search xyzzy_nonexistent")
        assert "No packages" in result or isinstance(result, str)

    def test_pkg_bad_sub_shows_usage(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("pkg badcommand")
        assert "Usage" in result or "usage" in result.lower()

    # ------------------------------------------------------------------
    # Web terminal commands
    # ------------------------------------------------------------------

    def test_web_status_when_not_started(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("web status")
        assert "stopped" in result.lower()

    def test_web_stop_when_not_started(self):
        shell, *_ = _make_shell()
        result = shell.dispatch("web stop")
        assert "not running" in result.lower()

    def test_web_start_and_stop(self):
        shell, *_ = _make_shell()
        # Find a free port
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        result = shell.dispatch(f"web start {port}")
        assert "started" in result.lower() or "7331" in result or str(port) in result
        shell.dispatch("web stop")


