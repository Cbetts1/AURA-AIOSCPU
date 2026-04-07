"""
Tests — Shell
=============
Validates command dispatch and AURA integration at the shell boundary.

Covers
------
- Shell initialises with aura and event_bus mocks.
- Built-in commands are dispatched without calling AURA.
- Unknown input is forwarded to aura.query().
- PERMISSION_REQUEST events result in a PERMISSION_RESPONSE event.
"""

# TODO: from unittest.mock import MagicMock, patch
# TODO: from shell import Shell


class TestShell:

    def test_instantiation(self):
        """Shell initialises cleanly with aura and event_bus mocks."""
        # TODO: shell = Shell(MagicMock(), MagicMock())
        # TODO: assert shell is not None
        pass

    def test_builtin_command_does_not_call_aura(self):
        """A recognised built-in command must not forward to aura.query()."""
        # TODO: aura = MagicMock()
        # TODO: shell = Shell(aura, MagicMock())
        # TODO: shell.dispatch("help")
        # TODO: aura.query.assert_not_called()
        pass

    def test_unknown_input_forwarded_to_aura(self):
        """Unrecognised input must be passed verbatim to aura.query()."""
        # TODO: aura = MagicMock(return_value="I can help with that.")
        # TODO: shell = Shell(aura, MagicMock())
        # TODO: result = shell.dispatch("what services are running?")
        # TODO: aura.query.assert_called_once_with("what services are running?")
        pass

    def test_dispatch_returns_string(self):
        """dispatch() must always return a string."""
        # TODO: shell = Shell(MagicMock(), MagicMock())
        # TODO: result = shell.dispatch("sysinfo")
        # TODO: assert isinstance(result, str)
        pass
