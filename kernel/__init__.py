"""
AURA-AIOSCPU Kernel
===================
Top-level kernel entry point.

Responsibilities
----------------
- Accept a surface mode (Universal / Internal / Hardware Projection).
- Initialise all subsystems in dependency order:
    HAL → Scheduler → EventBus → AURA → ServiceManager → Shell
- Start the kernel loop.
- Provide a clean shutdown path.
"""

# TODO: from kernel.loop import KernelLoop
# TODO: from kernel.scheduler import Scheduler
# TODO: from kernel.event_bus import EventBus
# TODO: from hal import HAL
# TODO: from aura import AURA
# TODO: from services import ServiceManager
# TODO: from shell import Shell


class Kernel:
    """Root kernel object. Owns and coordinates all subsystems."""

    def __init__(self, mode):
        # TODO: store mode
        # TODO: self.hal = HAL()
        # TODO: self.event_bus = EventBus()
        # TODO: self.scheduler = Scheduler(self.event_bus)
        # TODO: self.aura = AURA(self.event_bus)
        # TODO: self.services = ServiceManager(self.event_bus)
        # TODO: self.shell = Shell(self.aura, self.event_bus)
        # TODO: self.loop = KernelLoop(self.scheduler, self.event_bus, self.aura)
        pass

    def start(self) -> None:
        """Activate the mode, start subsystems, and enter the kernel loop."""
        # TODO: self.mode.activate(self)
        # TODO: self.hal start
        # TODO: self.services.discover()
        # TODO: self.shell start in background thread
        # TODO: self.loop.run()   ← blocks until shutdown
        pass

    def shutdown(self) -> None:
        """Gracefully stop all subsystems in reverse-start order."""
        # TODO: self.loop.stop()
        # TODO: stop shell
        # TODO: stop all services
        # TODO: flush logs
        # TODO: teardown HAL
        pass
