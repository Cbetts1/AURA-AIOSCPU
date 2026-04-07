"""
AURA-AIOSCPU Shell
==================
A text-based, AURA-integrated command shell.

Responsibilities
----------------
- Accept user text input.
- Dispatch recognised OS commands (built-ins) directly.
- Forward unrecognised input to AURA.query() as natural language.
- Display AURA responses and command output.
- Surface PERMISSION_REQUEST events to the user and return consent tokens.

The shell is AURA's primary user-facing interface. It is started by the
kernel in a background thread after all other subsystems are ready.
"""

# TODO: from aura import AURA
# TODO: from kernel.event_bus import EventBus, Event

BANNER = "AURA-AIOSCPU shell — type a command or ask AURA anything."
PROMPT = "aura> "


class Shell:
    """Text-based AURA-integrated shell."""

    def __init__(self, aura, event_bus):
        # TODO: self._aura = aura
        # TODO: self._event_bus = event_bus
        # TODO: self._running = False
        # TODO: self._builtins = self._register_builtins()
        # TODO: subscribe to PERMISSION_REQUEST events
        pass

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the interactive shell loop (blocks the calling thread)."""
        # TODO: self._running = True
        # TODO: print(BANNER)
        # TODO: while self._running:
        #     line = input(PROMPT).strip()
        #     if line:
        #         output = self.dispatch(line)
        #         if output:
        #             print(output)
        pass

    def stop(self) -> None:
        """Signal the shell loop to exit."""
        # TODO: self._running = False
        pass

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def dispatch(self, input_text: str) -> str:
        """Route input to a built-in handler or to AURA.

        Returns the output string to display.
        """
        # TODO: tokens = input_text.split()
        # TODO: if tokens[0] in self._builtins:
        #     return self._builtins[tokens[0]](tokens[1:])
        # TODO: return self._aura.query(input_text)
        return ""

    # ------------------------------------------------------------------
    # Built-in commands
    # ------------------------------------------------------------------

    def _register_builtins(self) -> dict:
        """Return the map of built-in command name → handler function."""
        # TODO: return {
        #     "help"    : self._cmd_help,
        #     "status"  : self._cmd_status,
        #     "services": self._cmd_services,
        #     "sysinfo" : self._cmd_sysinfo,
        #     "exit"    : self._cmd_exit,
        # }
        return {}

    # ------------------------------------------------------------------
    # Permission request handler (subscribed to event bus)
    # ------------------------------------------------------------------

    def _handle_permission_request(self, event) -> None:
        """Display a consent prompt and publish the user's response."""
        # TODO: capability = event.payload.get("capability")
        # TODO: answer = input(f"Grant '{capability}'? [y/N]: ")
        # TODO: granted = answer.strip().lower() == "y"
        # TODO: publish PERMISSION_RESPONSE event with {capability, granted}
        pass
