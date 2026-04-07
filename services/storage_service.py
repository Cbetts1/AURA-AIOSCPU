"""
AURA-AIOSCPU Storage Service
==============================
Manages the rootfs partition layout, SD-card detection, and runtime
filesystem overlays.

Partition model
---------------
  rootfs/
    boot/       ← boot partition  (read-only at runtime)
    system/     ← system partition (read-only at runtime, source of truth)
    user/       ← user partition   (writable — user data, preferences)
    overlay/    ← runtime overlay  (writable — ephemeral changes over system/)
    aura/       ← AURA runtime     (writable — caches, model state)
    services/   ← service runtime  (writable — service state files)
    var/        ← variable data    (writable — db, logs)
    tmp/        ← temporary files  (writable — cleared at boot)
    etc/        ← configuration    (readable — edited via Internal mode only)
    bin/        ← system binaries  (read-only symlinks)
    home/       ← user home dirs   (writable)
    mnt/        ← mount points     (SD card, USB, network mounts)

SD-card detection
-----------------
On Android/Termux, checks /sdcard, /storage/emulated/0, /storage/sdcard1.
On Linux, checks /media, /mnt/sdcard.
Falls back to internal rootfs if no SD card found.

Events published
----------------
  STORAGE_EVENT  { action, path, details }
"""

import json
import logging
import os
import shutil
import time

logger = logging.getLogger(__name__)

# Canonical partition directories within rootfs
PARTITIONS = {
    "boot":     {"writable": False},
    "system":   {"writable": False},
    "user":     {"writable": True},
    "overlay":  {"writable": True},
    "aura":     {"writable": True},
    "services": {"writable": True},
    "var":      {"writable": True},
    "tmp":      {"writable": True},
    "etc":      {"writable": False},  # writable only in Internal mode
    "bin":      {"writable": False},
    "home":     {"writable": True},
    "mnt":      {"writable": True},
}

# SD card probe paths by host type
_SD_PROBES = {
    "android": [
        "/storage/sdcard1",
        "/storage/extSdCard",
        "/sdcard",
        "/storage/emulated/0",
    ],
    "linux": [
        "/media",
        "/mnt/sdcard",
        "/mnt/sd",
    ],
    "macos": [
        "/Volumes",
    ],
    "windows": [],
}


class StorageService:
    """
    Manages rootfs partitions and SD-card mounting.

    Publishes STORAGE_EVENT to the event bus on significant state changes.
    """

    def __init__(self, event_bus=None,
                 rootfs_path: str = "rootfs"):
        self._event_bus  = event_bus
        self._rootfs     = os.path.abspath(rootfs_path)
        self._sd_path: str | None = None
        self._running    = False
        self._state      = "stopped"
        self._layout_path = os.path.join(self._rootfs, "layout.json")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Mount the rootfs, create missing partitions, detect SD card."""
        if self._running:
            return
        self._running = True
        self._state   = "starting"
        logger.info("StorageService: starting (rootfs=%s)", self._rootfs)

        self._ensure_partitions()
        self._clear_tmp()
        self._write_layout()
        self._sd_path = self._detect_sd_card()

        self._state = "running"
        self._publish("mount", self._rootfs,
                      {"sd_card": self._sd_path, "partitions": list(PARTITIONS)})
        logger.info("StorageService: running  sd_card=%s", self._sd_path or "none")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._state   = "stopped"
        self._publish("unmount", self._rootfs, {})
        logger.info("StorageService: stopped")

    # ------------------------------------------------------------------
    # Partition helpers
    # ------------------------------------------------------------------

    def ensure_writable(self, rel_path: str) -> str:
        """
        Return the full path to a writable location for rel_path.

        If rel_path is under a read-only partition, routes through overlay/.
        """
        parts = rel_path.lstrip("/").split("/")
        partition = parts[0] if parts else ""
        if PARTITIONS.get(partition, {}).get("writable", True):
            return os.path.join(self._rootfs, rel_path)
        # Route through overlay
        overlay = os.path.join(self._rootfs, "overlay",
                               rel_path.lstrip("/"))
        os.makedirs(os.path.dirname(overlay), exist_ok=True)
        return overlay

    def partition_path(self, partition: str) -> str:
        """Return the absolute path to a named partition."""
        if partition not in PARTITIONS:
            raise ValueError(f"Unknown partition: {partition!r}")
        return os.path.join(self._rootfs, partition)

    def read_file(self, rel_path: str) -> bytes:
        """Read a file relative to rootfs, checking overlay first."""
        # Check overlay first (runtime changes take precedence)
        overlay_path = os.path.join(self._rootfs, "overlay",
                                    rel_path.lstrip("/"))
        if os.path.isfile(overlay_path):
            with open(overlay_path, "rb") as fh:
                return fh.read()
        full_path = os.path.join(self._rootfs, rel_path)
        with open(full_path, "rb") as fh:
            return fh.read()

    def write_file(self, rel_path: str, data: bytes,
                   force_overlay: bool = False) -> None:
        """Write a file relative to rootfs. Routes through overlay if needed."""
        dest = self.ensure_writable(rel_path) if not force_overlay else \
               os.path.join(self._rootfs, "overlay", rel_path.lstrip("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        self._publish("write", rel_path, {"size": len(data)})

    def list_partition(self, partition: str) -> list[str]:
        """List files in a partition."""
        path = self.partition_path(partition)
        if not os.path.isdir(path):
            return []
        result = []
        for root, dirs, files in os.walk(path):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), self._rootfs)
                result.append(rel)
        return result

    # ------------------------------------------------------------------
    # SD-card management
    # ------------------------------------------------------------------

    def sd_card_path(self) -> str | None:
        """Return the detected SD-card mount path, or None."""
        return self._sd_path

    def is_sd_mounted(self) -> bool:
        return self._sd_path is not None

    def mount_sd_rootfs(self, sd_path: str) -> bool:
        """
        Attempt to use an SD card as the primary rootfs.

        Verifies the SD card has the expected AURA partition layout before
        switching. Returns True if successfully mounted.
        """
        marker = os.path.join(sd_path, "etc", "aura.conf")
        if not os.path.isfile(marker):
            logger.warning("StorageService: SD card at %r has no aura.conf — "
                           "not a valid AURA rootfs", sd_path)
            return False
        self._rootfs  = os.path.abspath(sd_path)
        self._sd_path = sd_path
        self._ensure_partitions()
        self._publish("sd_mount", sd_path, {"rootfs": self._rootfs})
        logger.info("StorageService: switched rootfs to SD card at %r", sd_path)
        return True

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def status(self) -> dict:
        used, total = self._disk_usage()
        return {
            "state":      self._state,
            "rootfs":     self._rootfs,
            "sd_card":    self._sd_path,
            "partitions": list(PARTITIONS.keys()),
            "disk_used":  used,
            "disk_total": total,
        }

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _ensure_partitions(self) -> None:
        """Create any missing partition directories."""
        for name in PARTITIONS:
            path = os.path.join(self._rootfs, name)
            os.makedirs(path, exist_ok=True)
        logger.debug("StorageService: partitions verified")

    def _clear_tmp(self) -> None:
        """Clear the tmp partition at boot (ephemeral by definition)."""
        tmp_path = os.path.join(self._rootfs, "tmp")
        if os.path.isdir(tmp_path):
            for entry in os.scandir(tmp_path):
                try:
                    if entry.is_file() or entry.is_symlink():
                        os.unlink(entry.path)
                    elif entry.is_dir():
                        shutil.rmtree(entry.path)
                except Exception:
                    pass

    def _write_layout(self) -> None:
        """Write the layout manifest to rootfs/layout.json."""
        layout = {
            "version":    "1.0",
            "generated":  time.time(),
            "rootfs":     self._rootfs,
            "partitions": {
                name: {
                    "path":     os.path.join(self._rootfs, name),
                    "writable": info["writable"],
                }
                for name, info in PARTITIONS.items()
            },
        }
        try:
            with open(self._layout_path, "w") as fh:
                json.dump(layout, fh, indent=2)
        except OSError:
            pass  # read-only filesystem — skip

    def _detect_sd_card(self) -> str | None:
        """Best-effort SD-card detection — returns path or None."""
        from host_bridge import detect_host_type
        host = detect_host_type()
        probes = _SD_PROBES.get(host, [])
        for path in probes:
            if os.path.isdir(path) and os.access(path, os.R_OK):
                logger.info("StorageService: detected SD card at %r", path)
                return path
        return None

    def _disk_usage(self) -> tuple[int, int]:
        """Return (used_bytes, total_bytes) for the rootfs partition."""
        try:
            stat = shutil.disk_usage(self._rootfs)
            return stat.used, stat.total
        except Exception:
            return 0, 0

    def _publish(self, action: str, path: str, details: dict) -> None:
        if self._event_bus is None:
            return
        try:
            from kernel.event_bus import Event, Priority
            self._event_bus.publish(
                Event("STORAGE_EVENT",
                      payload={"action": action, "path": path,
                               "details": details},
                      priority=Priority.LOW, source="storage_service")
            )
        except Exception:
            pass
