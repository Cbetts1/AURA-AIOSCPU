"""
AURA-AIOSCPU Kernel
===================
Top-level kernel entry point.

Responsibilities
----------------
- Accept a surface mode (Universal / Internal / Hardware Projection).
- Initialise all subsystems in dependency order:
    HAL → EventBus → Scheduler → AURA → ServiceManager → Shell → KernelLoop
- Start the kernel loop.
- Provide a clean shutdown path.
"""

import logging
import threading

from hal import HAL
from kernel.event_bus import EventBus, Event, Priority
from kernel.loop import KernelLoop
from kernel.scheduler import Scheduler
from aura import AURA
from services import ServiceManager
from shell import Shell

logger = logging.getLogger(__name__)


class Kernel:
    """Root kernel object. Owns and coordinates all subsystems."""

    def __init__(self, mode):
        self.mode = mode

        # Dependency order: HAL first, then comms, then intelligence
        self.hal = HAL()
        self.event_bus = EventBus()
        self.scheduler = Scheduler(self.event_bus)
        self.aura = AURA(self.event_bus)
        self.services = ServiceManager(self.event_bus)
        self.shell = Shell(self.aura, self.event_bus)
        self.loop = KernelLoop(self.scheduler, self.event_bus, self.aura)

        self._shell_thread: threading.Thread | None = None

    def start(self) -> None:
        """Activate the mode, start subsystems, and enter the kernel loop."""
        logger.info("Kernel: starting in mode %r", getattr(self.mode, "NAME", "?"))

        # Bring virtual hardware online
        self.hal.start()

        # Activate the kernel surface mode (registers devices, publishes event)
        self.mode.activate(self)

        # Discover and auto-start services
        self.services.discover()

        # Run the shell in a daemon thread so it doesn't block the loop
        self._shell_thread = threading.Thread(
            target=self.shell.run, name="aura-shell", daemon=True
        )
        self._shell_thread.start()

        # Enter the kernel loop — blocks until SHUTDOWN event or stop()
        self.loop.run()

    def shutdown(self) -> None:
        """Gracefully stop all subsystems in reverse-start order."""
        logger.info("Kernel: shutting down")
        self.loop.stop()
        self.shell.stop()
        if self._shell_thread and self._shell_thread.is_alive():
            self._shell_thread.join(timeout=2.0)
        self.hal.stop()
        logger.info("Kernel: shutdown complete")

