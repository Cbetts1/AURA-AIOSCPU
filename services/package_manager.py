"""
AURA-AIOSCPU Package Manager
==============================
A lightweight package manager that wraps pip and maintains a local registry
of installed packages.  Works fully offline for registry queries; only
``install`` and ``uninstall`` need a network connection (or a local wheel).

Commands (exposed via shell ``pkg`` built-in)
---------------------------------------------
  pkg list              — list installed packages
  pkg install <name>    — install a Python package via pip
  pkg uninstall <name>  — remove a package via pip
  pkg info <name>       — show package metadata
  pkg search <term>     — search installed registry for term
  pkg upgrade <name>    — upgrade to latest version

Registry
--------
The package registry is a JSON file stored at
``rootfs/var/lib/aura/packages.json``.  It records every package that was
installed through AURA so that ``pkg list`` works offline without querying
pip every time.
"""

import json
import logging
import os
import subprocess
import sys
import time
import threading

logger = logging.getLogger(__name__)

_REPO_ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REGISTRY_DIR = os.path.join(_REPO_ROOT, "rootfs", "var", "lib", "aura")
_REGISTRY_FILE = os.path.join(_REGISTRY_DIR, "packages.json")


# ---------------------------------------------------------------------------
# Package record
# ---------------------------------------------------------------------------

class PackageRecord:
    """Metadata for one installed package."""

    def __init__(self, name: str, version: str = "",
                 description: str = "",
                 installed_at: float | None = None):
        self.name         = name
        self.version      = version
        self.description  = description
        self.installed_at = installed_at or time.time()

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "version":      self.version,
            "description":  self.description,
            "installed_at": self.installed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PackageRecord":
        return cls(
            name=d.get("name", ""),
            version=d.get("version", ""),
            description=d.get("description", ""),
            installed_at=d.get("installed_at"),
        )

    def __repr__(self):
        return f"PackageRecord({self.name!r} v{self.version})"


# ---------------------------------------------------------------------------
# PackageManager
# ---------------------------------------------------------------------------

class PackageManager:
    """
    Installs, removes, and tracks Python packages for AURA.

    All pip operations run in a subprocess so they never block the kernel.
    The local registry JSON is updated after each successful install/uninstall.
    """

    def __init__(self,
                 event_bus=None,
                 registry_path: str = _REGISTRY_FILE):
        self._event_bus     = event_bus
        self._registry_path = registry_path
        self._registry: dict[str, PackageRecord] = {}
        self._lock          = threading.Lock()
        os.makedirs(os.path.dirname(registry_path), exist_ok=True)
        self._load_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(self, package: str, upgrade: bool = False) -> dict:
        """
        Install a package via pip.

        Returns a result dict:
          {"success": bool, "message": str, "package": str}
        """
        args = [sys.executable, "-m", "pip", "install", package,
                "--quiet", "--no-input"]
        if upgrade:
            args.append("--upgrade")
        try:
            result = subprocess.run(
                args,
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                version = self._pip_show_version(package)
                with self._lock:
                    self._registry[package.lower()] = PackageRecord(
                        name=package.lower(),
                        version=version,
                        description=self._pip_show_description(package),
                    )
                self._save_registry()
                self._publish_event("PKG_INSTALLED",
                                    {"name": package, "version": version})
                return {
                    "success": True,
                    "message": f"{package} {version} installed successfully.",
                    "package": package,
                }
            else:
                err = result.stderr.strip() or result.stdout.strip()
                return {
                    "success": False,
                    "message": f"pip failed: {err[:300]}",
                    "package": package,
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "pip timed out.", "package": package}
        except Exception as exc:
            return {"success": False, "message": str(exc), "package": package}

    def uninstall(self, package: str) -> dict:
        """Uninstall a package via pip."""
        args = [sys.executable, "-m", "pip", "uninstall", package, "-y", "--quiet"]
        try:
            result = subprocess.run(
                args,
                capture_output=True, text=True, timeout=60,
            )
            with self._lock:
                self._registry.pop(package.lower(), None)
            self._save_registry()
            if result.returncode == 0:
                self._publish_event("PKG_REMOVED", {"name": package})
                return {"success": True, "message": f"{package} removed.", "package": package}
            else:
                err = result.stderr.strip() or result.stdout.strip()
                return {"success": False, "message": f"pip failed: {err[:300]}", "package": package}
        except Exception as exc:
            return {"success": False, "message": str(exc), "package": package}

    def upgrade(self, package: str) -> dict:
        """Upgrade a package to its latest version."""
        return self.install(package, upgrade=True)

    def list_packages(self) -> list[dict]:
        """Return all packages in the local registry."""
        with self._lock:
            return [r.to_dict() for r in sorted(
                self._registry.values(), key=lambda r: r.name
            )]

    def info(self, package: str) -> dict | None:
        """Return registry entry for a package, or None if unknown."""
        with self._lock:
            rec = self._registry.get(package.lower())
        return rec.to_dict() if rec else None

    def search(self, term: str) -> list[dict]:
        """Search installed registry by name or description."""
        term = term.lower()
        with self._lock:
            return [
                r.to_dict() for r in self._registry.values()
                if term in r.name.lower() or term in r.description.lower()
            ]

    def is_installed(self, package: str) -> bool:
        with self._lock:
            return package.lower() in self._registry

    # ------------------------------------------------------------------
    # Registry persistence
    # ------------------------------------------------------------------

    def _load_registry(self) -> None:
        if not os.path.exists(self._registry_path):
            return
        try:
            with open(self._registry_path) as fh:
                data = json.load(fh)
            with self._lock:
                for entry in data.get("packages", []):
                    rec = PackageRecord.from_dict(entry)
                    self._registry[rec.name] = rec
            logger.info("PackageManager: loaded %d packages from registry",
                        len(self._registry))
        except Exception:
            logger.exception("PackageManager: failed to load registry")

    def _save_registry(self) -> None:
        try:
            with self._lock:
                payload = {
                    "updated":  time.time(),
                    "packages": [r.to_dict() for r in self._registry.values()],
                }
            with open(self._registry_path, "w") as fh:
                json.dump(payload, fh, indent=2)
        except Exception:
            logger.exception("PackageManager: failed to save registry")

    # ------------------------------------------------------------------
    # pip helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pip_show_version(package: str) -> str:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "show", package],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def _pip_show_description(package: str) -> str:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "show", package],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.splitlines():
                if line.startswith("Summary:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # Event
    # ------------------------------------------------------------------

    def _publish_event(self, event_type: str, payload: dict) -> None:
        if self._event_bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._event_bus.publish(
                Event(event_type, payload=payload,
                      priority=Priority.NORMAL, source="package_manager")
            )
        except Exception:
            logger.exception("PackageManager: failed to publish event")

    def __repr__(self):
        return f"PackageManager(packages={len(self._registry)})"
