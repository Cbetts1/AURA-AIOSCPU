"""
AURA-AIOSCPU Kernel
===================
Top-level kernel entry point.

Responsibilities
----------------
- Accept a surface mode (Universal / Internal / Hardware Projection).
- Optionally accept a Config and DeviceProfile for tuning.
- Initialise all subsystems in dependency order:
    HAL (+ storage) → EventBus → Scheduler → PermissionModel →
    ModelManager → AURA → KernelAPI → ServiceManager →
    StorageService → LoggingService → JobQueue → HealthMonitor →
    Shell → Watchdog → BuildService → KernelLoop
- Start the kernel loop.
- Provide a clean shutdown path.
- Expose KernelAPI as the stable interface for services and apps.
"""

import logging
import os
import threading

from hal import HAL
from kernel.event_bus import EventBus, Event, Priority
from kernel.loop import KernelLoop
from kernel.scheduler import Scheduler
from kernel.permissions import PermissionModel
from kernel.api import KernelAPI
from aura import AURA
from services import ServiceManager
from shell import Shell

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Kernel:
    """Root kernel object. Owns and coordinates all subsystems."""

    def __init__(self, mode, config=None, device_profile=None):
        self.mode            = mode
        self._config         = config
        self._device_profile = device_profile

        # ----------------------------------------------------------
        # Read tuning parameters from config
        # ----------------------------------------------------------
        tick_ms      = 16
        adaptive     = True
        max_tick_ms  = 1000
        max_mem_mb   = 512
        services_dir = os.path.join(_REPO_ROOT, "services")
        models_dir   = os.path.join(_REPO_ROOT, "models")
        storage_path = os.path.join(_REPO_ROOT, "rootfs", "var", "aura.db")

        if config is not None:
            tick_ms      = config.get("kernel", "tick_interval_ms", tick_ms)
            adaptive     = config.get("kernel", "adaptive_tick",    adaptive)
            max_tick_ms  = config.get("kernel", "max_tick_interval_ms", max_tick_ms)
            max_mem_mb   = config.get("hal",    "max_memory_mb",    max_mem_mb)
            storage_path = config.get("hal",    "storage_path",     storage_path)
            raw_models   = config.get("aura",   "model_dir",        "models")
            if not os.path.isabs(raw_models):
                models_dir = os.path.join(_REPO_ROOT, raw_models)

        mode_name = getattr(mode, "NAME", "universal")

        # ----------------------------------------------------------
        # Dependency order
        # ----------------------------------------------------------

        # 1 — Virtual hardware
        self.hal = HAL()

        # 2 — Virtual storage (backed by SQLite — mobile-safe)
        from hal.devices.storage import VStorageDevice
        if not os.path.isabs(storage_path):
            storage_path = os.path.join(_REPO_ROOT, storage_path)
        self.storage = VStorageDevice(storage_path)

        # 3 — Event bus (sole comms channel)
        self.event_bus = EventBus()

        # 4 — Scheduler
        self.scheduler = Scheduler(self.event_bus)

        # 5 — Permission model (tied to kernel surface mode)
        self.permissions = PermissionModel(mode=mode_name)

        # 6 — AI model manager (lazy; no model file required at boot)
        from models.model_manager import ModelManager
        self.model_manager = ModelManager(
            models_dir=models_dir,
            max_memory_mb=max_mem_mb,
        )
        self.model_manager.scan_models_dir()

        # 7 — AURA (pulsed every tick; uses model manager for inference)
        self.aura = AURA(self.event_bus, model_manager=self.model_manager)

        # 8 — Kernel API (stable public surface for services/apps)
        self.api = KernelAPI(self, self.permissions)

        # 9 — Service manager
        self.services = ServiceManager(self.event_bus,
                                       services_dir=services_dir)

        # 10 — StorageService (rootfs + SD-card partition management)
        from services.storage_service import StorageService
        self.storage_service = StorageService(
            self.event_bus,
            rootfs_path=os.path.join(_REPO_ROOT, "rootfs"),
        )

        # 11 — LoggingService (structured log aggregation)
        from services.logging_service import LoggingService
        self.logging_service = LoggingService(
            self.event_bus,
            log_dir=os.path.join(_REPO_ROOT, "logs"),
        )

        # 12 — JobQueue (persistent, prioritised job queue)
        from services.job_queue import JobQueue
        self.job_queue = JobQueue(self.event_bus, self.scheduler)

        # 13 — HealthMonitor (health checks + self-healing)
        from services.health_monitor import HealthMonitor
        self.health_monitor = HealthMonitor(
            self.event_bus, self.services, self.job_queue,
        )

        # 14 — BuildService (needed by shell)
        from services.build_service import BuildService
        self.build_service = BuildService(self.event_bus)

        # 15 — Watchdog (self-repair daemon)
        watchdog_cfg = config.get_section("watchdog") if config else {}
        from kernel.watchdog import KernelWatchdog
        self.watchdog = KernelWatchdog(
            self.event_bus, self.services,
            check_interval_ms=watchdog_cfg.get("check_interval_ms", 5000),
            max_failures=watchdog_cfg.get("max_failures", 3),
            auto_restart=watchdog_cfg.get("auto_restart", True),
        )

        # 16 — Network monitor (connectivity events; starts lazily)
        from services.network_service import NetworkService
        self.network_service = NetworkService(self.event_bus)

        # 17 — Package manager
        from services.package_manager import PackageManager
        self.package_manager = PackageManager(self.event_bus)

        # 18 — Web terminal (off by default; user starts with 'web start')
        from services.web_terminal import WebTerminalService
        self.web_terminal = WebTerminalService(
            dispatch_fn=None,   # wired after shell is created (see start())
            event_bus=self.event_bus,
        )

        # 19 — Shell (created last so all service references are ready)
        self.shell = Shell(
            self.aura, self.event_bus,
            kernel_api=self.api,
            build_service=self.build_service,
            model_manager=self.model_manager,
            device_profile=device_profile,
            web_terminal=self.web_terminal,
            network_service=self.network_service,
            package_manager=self.package_manager,
            storage_service=self.storage_service,
            logging_service=self.logging_service,
            job_queue=self.job_queue,
            health_monitor=self.health_monitor,
        )

        # 20 — Kernel loop
        self.loop = KernelLoop(
            self.scheduler, self.event_bus, self.aura,
            tick_interval_ms=tick_ms,
            adaptive=adaptive,
            max_tick_interval_ms=max_tick_ms,
        )

        self._shell_thread: threading.Thread | None = None

    def start(self) -> None:
        """Activate the mode, start subsystems, and enter the kernel loop."""
        mode_name = getattr(self.mode, "NAME", "?")
        logger.info("Kernel: starting in mode %r", mode_name)

        # Bring virtual hardware online
        self.hal.start()
        self.storage.start()
        self.hal.register_device("storage", self.storage)

        # Activate the kernel surface mode (registers devices, publishes event)
        self.mode.activate(self)

        # Sync permission model with the activated mode
        self.permissions.set_mode(mode_name)

        # Wire AURA to the live kernel for deep introspection
        self.aura.attach_kernel(self)

        # Start service mesh
        self.storage_service.start()
        self.logging_service.start()
        self.job_queue.start()
        self.health_monitor.start()

        # Start the self-repair watchdog
        self.watchdog.start()

        # Start the network monitor
        self.network_service.start()

        # Discover and auto-start services (from *.service unit files)
        self.services.discover()

        # Wire the shell's dispatch function into the web terminal
        self.web_terminal._dispatch_fn = self.shell.dispatch

        # Run the shell in a daemon thread so it doesn't block the loop
        self._shell_thread = threading.Thread(
            target=self.shell.run, name="aura-shell", daemon=True
        )
        self._shell_thread.start()

        # Announce boot complete
        self.event_bus.publish(
            Event("BOOT_COMPLETE",
                  payload={"mode": mode_name,
                           "service_count": len(self.services._registry)},
                  priority=Priority.HIGH, source="kernel")
        )
        logger.info("Kernel: boot complete — entering kernel loop")

        # Enter the kernel loop — blocks until SHUTDOWN event or stop()
        self.loop.run()

    def shutdown(self) -> None:
        """Gracefully stop all subsystems in reverse-start order."""
        logger.info("Kernel: shutting down")
        self.watchdog.stop()
        self.network_service.stop()
        self.health_monitor.stop()
        self.job_queue.stop()
        self.logging_service.stop()
        self.storage_service.stop()
        if self.web_terminal.is_running:
            self.web_terminal.stop()
        self.loop.stop()
        self.shell.stop()
        if self._shell_thread and self._shell_thread.is_alive():
            self._shell_thread.join(timeout=2.0)
        self.storage.stop()
        self.hal.stop()
        logger.info("Kernel: shutdown complete")

