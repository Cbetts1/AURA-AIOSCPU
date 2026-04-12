"""
AURA-AIOSCPU Module Builder — Self-Expansion Engine
=====================================================
Allows a live AURA instance to scaffold new modules, services, shell
plugins, and configuration files — without stopping or restarting the
system.

The builder reads a compact template description and emits fully
functional Python source, test stubs, and the matching service
descriptor.

Usage (from AURA shell)
-----------------------
  build module <name>                  scaffold a service module
  build plugin <name>                  scaffold a shell plugin
  build service-descriptor <name>      write .service file
  build show-templates                 list available templates

Python API
----------
::

    from services.module_builder import ModuleBuilder
    mb = ModuleBuilder()
    result = mb.scaffold_service("my_feature", description="Does X")
    # result.paths lists created files

Events published
----------------
  MODULE_BUILT   {"name": "...", "type": "service", "paths": [...]}
  MODULE_ERROR   {"name": "...", "error": "..."}
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVICES_D  = os.path.join(_REPO_ROOT, "rootfs", "etc", "aura", "services.d")
_SERVICES_PY = os.path.join(_REPO_ROOT, "services")
_SHELL_PLUG  = os.path.join(_REPO_ROOT, "shell", "plugins")
_TESTS_DIR   = os.path.join(_REPO_ROOT, "tests")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class BuildResult:
    name:    str
    success: bool
    paths:   list[str] = field(default_factory=list)
    errors:  list[str] = field(default_factory=list)
    message: str       = ""

    def to_dict(self) -> dict:
        return {
            "name":    self.name,
            "success": self.success,
            "paths":   self.paths,
            "errors":  self.errors,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_SERVICE_TEMPLATE = '''\
"""
AURA-AIOSCPU {class_name} Service
{"=" * (len(class_name) + 24)}
{description}

Events published
----------------
  {UPPER_NAME}_STARTED   — service has started
  {UPPER_NAME}_STOPPED   — service has stopped
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class {class_name}Service:
    """
    {description}

    Parameters
    ----------
    event_bus : EventBus | None
        Kernel event bus for publishing events.
    """

    def __init__(self, event_bus=None):
        self._bus      = event_bus
        self._running  = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the service."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="{lower_name}-svc"
        )
        self._thread.start()
        self._publish("{UPPER_NAME}_STARTED", {{}})
        logger.info("{class_name}Service: started")

    def stop(self) -> None:
        """Stop the service."""
        self._running = False
        self._publish("{UPPER_NAME}_STOPPED", {{}})
        logger.info("{class_name}Service: stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while self._running:
            time.sleep(1)
            # TODO: implement service logic here

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        return {{
            "running": self._running,
        }}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _publish(self, event_type: str, payload: dict) -> None:
        if self._bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._bus.publish(Event(
                event_type, payload=payload,
                priority=Priority.NORMAL,
                source="{lower_name}_service",
            ))
        except Exception:
            pass
'''

_SERVICE_DESCRIPTOR_TEMPLATE = """\
[Service]
Name={lower_name}
Description={description}
Module=services.{lower_name}_service:{class_name}Service
AutoStart=true
RestartPolicy=on-failure
RestartDelay=5

[Health]
CheckInterval=30
MaxFailures=3
"""

_TEST_TEMPLATE = '''\
"""Tests for {class_name}Service."""
import pytest
from kernel.event_bus import EventBus
from services.{lower_name}_service import {class_name}Service


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def service(bus):
    svc = {class_name}Service(bus)
    yield svc
    svc.stop()


class Test{class_name}Service:
    def test_start_stop(self, service):
        service.start()
        assert service.status()["running"] is True
        service.stop()

    def test_status_dict(self, service):
        s = service.status()
        assert "running" in s

    def test_start_idempotent(self, service):
        service.start()
        service.start()  # second call must not crash
        assert service.status()["running"] is True
        service.stop()
'''

_PLUGIN_TEMPLATE = '''\
"""
AURA-AIOSCPU Shell Plugin: {name}
{"=" * (len(name) + 28)}
{description}
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register(shell) -> None:
    """Register commands with the AURA shell."""
    shell.register("{lower_name}", cmd_{lower_name})
    logger.debug("{name} plugin registered")


def cmd_{lower_name}(args: list[str], shell) -> str:
    """
    {description}

    Usage:  {lower_name} [options]
    """
    # TODO: implement command logic
    return f"{name} plugin — args: {{args!r}}"
'''


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class ModuleBuilder:
    """
    Scaffolding engine for new AURA modules.

    Parameters
    ----------
    event_bus : EventBus | None
        If provided, BUILD events are published on success/error.
    dry_run : bool
        If True, files are rendered and returned but never written.
    """

    def __init__(self, event_bus=None, dry_run: bool = False):
        self._bus     = event_bus
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # Public scaffold methods
    # ------------------------------------------------------------------

    def scaffold_service(
        self,
        name: str,
        description: str = "",
        with_test: bool = True,
        with_descriptor: bool = True,
    ) -> BuildResult:
        """
        Scaffold a new service module.

        Creates:
          services/<name>_service.py
          tests/test_<name>_service.py  (if with_test)
          rootfs/etc/aura/services.d/<name>.service  (if with_descriptor)
        """
        name = _sanitize(name)
        class_name = _to_class_name(name)
        description = description or f"AURA {class_name} service."
        result = BuildResult(name=name, success=False)

        paths: list[tuple[str, str]] = []

        # Service module
        src = self._render_service(name, class_name, description)
        dest = os.path.join(_SERVICES_PY, f"{name}_service.py")
        paths.append((dest, src))

        # Test stub
        if with_test:
            test_src = self._render_test(name, class_name)
            test_dest = os.path.join(_TESTS_DIR, f"test_{name}_service.py")
            paths.append((test_dest, test_src))

        # Service descriptor
        if with_descriptor:
            desc_src = self._render_descriptor(name, class_name, description)
            desc_dest = os.path.join(_SERVICES_D, f"{name}.service")
            paths.append((desc_dest, desc_src))

        written = self._write_all(paths, result)
        if written:
            result.success = True
            result.message = f"Service {name!r} scaffolded ({len(result.paths)} files)"
            self._publish("MODULE_BUILT", {"name": name, "type": "service", "paths": result.paths})
        return result

    def scaffold_plugin(
        self,
        name: str,
        description: str = "",
    ) -> BuildResult:
        """
        Scaffold a new shell plugin.

        Creates:
          shell/plugins/<name>.py
        """
        name = _sanitize(name)
        description = description or f"AURA shell plugin: {name}."
        result = BuildResult(name=name, success=False)

        src  = self._render_plugin(name, description)
        dest = os.path.join(_SHELL_PLUG, f"{name}.py")
        self._write_all([(dest, src)], result)
        if result.paths:
            result.success = True
            result.message = f"Plugin {name!r} scaffolded"
            self._publish("MODULE_BUILT", {"name": name, "type": "plugin", "paths": result.paths})
        return result

    def list_templates(self) -> list[str]:
        return ["service", "plugin", "service-descriptor"]

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def _render_service(self, name: str, class_name: str, description: str) -> str:
        upper = name.upper()
        tpl = _SERVICE_TEMPLATE
        tpl = tpl.replace("{class_name}", class_name)
        tpl = tpl.replace("{lower_name}", name)
        tpl = tpl.replace("{UPPER_NAME}", upper)
        tpl = tpl.replace("{description}", description)
        # expand the title underline (done after other substitutions)
        tpl = _expand_format_exprs(tpl)
        return tpl

    def _render_test(self, name: str, class_name: str) -> str:
        tpl = _TEST_TEMPLATE
        tpl = tpl.replace("{class_name}", class_name)
        tpl = tpl.replace("{lower_name}", name)
        return tpl

    def _render_descriptor(self, name: str, class_name: str, description: str) -> str:
        tpl = _SERVICE_DESCRIPTOR_TEMPLATE
        tpl = tpl.replace("{lower_name}", name)
        tpl = tpl.replace("{class_name}", class_name)
        tpl = tpl.replace("{description}", description)
        return tpl

    def _render_plugin(self, name: str, description: str) -> str:
        tpl = _PLUGIN_TEMPLATE
        tpl = tpl.replace("{name}", _to_class_name(name))
        tpl = tpl.replace("{lower_name}", name)
        tpl = tpl.replace("{description}", description)
        tpl = _expand_format_exprs(tpl)
        return tpl

    # ------------------------------------------------------------------
    # File writing
    # ------------------------------------------------------------------

    def _write_all(self, paths: list[tuple[str, str]], result: BuildResult) -> bool:
        ok = True
        for dest, content in paths:
            if os.path.exists(dest):
                result.errors.append(f"already exists: {dest}")
                ok = False
                continue
            if self._dry_run:
                result.paths.append(dest)
                continue
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "w") as fh:
                    fh.write(content)
                result.paths.append(dest)
                logger.info("ModuleBuilder: wrote %s", dest)
            except OSError as exc:
                result.errors.append(f"write error: {exc}")
                ok = False
        return ok and len(result.paths) > 0

    # ------------------------------------------------------------------
    # Event bus
    # ------------------------------------------------------------------

    def _publish(self, event_type: str, payload: dict) -> None:
        if self._bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._bus.publish(Event(
                event_type, payload=payload,
                priority=Priority.NORMAL,
                source="module_builder",
            ))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    """Convert arbitrary string to a valid Python identifier (snake_case)."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        raise ValueError("Module name cannot be empty")
    return name


def _to_class_name(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def _expand_format_exprs(src: str) -> str:
    """
    Evaluate simple ``{"=" * N}`` and ``{len(...)}`` expressions left in
    template strings after other substitutions.  Uses a safe regex approach.
    """
    def _eval_match(m: re.Match) -> str:
        expr = m.group(1)
        try:
            return str(eval(expr, {"__builtins__": {}}, {"len": len}))  # noqa: S307
        except Exception:
            return m.group(0)

    return re.sub(r'\{([^{}]+)\}', _eval_match, src)
