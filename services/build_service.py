"""
AURA-AIOSCPU Build Service — Self-Build and Self-Repair
========================================================
Allows a running AURA-AIOSCPU instance to rebuild its own rootfs,
verify file integrity, and execute the test suite — all from within
the live system.

This is the foundation of AURA's self-repair capability:
    Shell: rebuild      → BuildService.rebuild_rootfs()
    Shell: repair       → BuildService.verify_integrity() + selective copy
    Shell: test         → BuildService.run_tests()
    Watchdog events     → BuildService.verify_integrity() on degradation

Events published
----------------
  BUILD_STARTED   — build has begun
  BUILD_COMPLETE  — build finished (success or failure)
  TEST_COMPLETE   — test run finished
  INTEGRITY_ALERT — a source file has been modified since last build
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from kernel.event_bus import EventBus, Event, Priority

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PACKAGES = [
    "kernel", "hal", "aura", "services", "shell",
    "host_bridge", "models", "tools", "config", "launch",
]


class BuildResult:
    def __init__(self, success: bool, message: str = "",
                 duration_s: float = 0.0):
        self.success    = success
        self.message    = message
        self.duration_s = duration_s

    def to_dict(self) -> dict:
        return {
            "success":    self.success,
            "message":    self.message,
            "duration_s": round(self.duration_s, 2),
        }


class BuildService:
    """
    In-system self-build and self-repair service.

    All build operations are protected by a mutex so that only one build
    can run at a time, even if triggered concurrently via the shell and
    a watchdog event.
    """

    def __init__(self, event_bus: EventBus,
                 repo_root: str = _REPO_ROOT):
        self._event_bus   = event_bus
        self._root        = repo_root
        self._lock        = threading.Lock()
        self._last_result: BuildResult | None = None
        self._log:        list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rebuild_rootfs(self, async_build: bool = False) -> BuildResult | None:
        """
        Rebuild the distributable rootfs into dist/.

        If *async_build* is True the build runs in a daemon thread and
        None is returned immediately; the result arrives as BUILD_COMPLETE.
        """
        if async_build:
            threading.Thread(
                target=self._do_rebuild, name="aura-rebuild", daemon=True
            ).start()
            return None
        return self._do_rebuild()

    def verify_integrity(self) -> dict:
        """
        SHA-256 each Python source file and compare against the last
        build manifest.  Returns a report dict including a list of
        changed files.
        """
        checksums: dict[str, str] = {}
        repo = Path(self._root)
        manifest_path = repo / "dist" / "manifest.json"
        last_manifest: dict[str, str] = {}

        if manifest_path.exists():
            try:
                with open(manifest_path) as fh:
                    data = json.load(fh)
                last_manifest = data.get("files", {})
            except Exception:
                pass

        for py_file in sorted(repo.rglob("*.py")):
            rel = str(py_file.relative_to(repo))
            if any(p in rel for p in (".git", "__pycache__", "dist", "/tmp")):
                continue
            checksums[rel] = _sha256(py_file)

        changed = [
            rel for rel, chk in checksums.items()
            if rel in last_manifest and last_manifest[rel] != chk
        ]

        if changed:
            self._event_bus.publish(Event(
                "INTEGRITY_ALERT",
                payload={"changed_files": changed},
                priority=Priority.HIGH,
                source="build_service",
            ))

        has_baseline = bool(last_manifest)
        return {
            "total_files":   len(checksums),
            "changed_files": changed,
            "has_baseline":  has_baseline,
            "integrity_ok":  has_baseline and len(changed) == 0,
        }

    def run_tests(self, async_run: bool = False) -> BuildResult | None:
        """Run the full pytest test suite."""
        if async_run:
            threading.Thread(
                target=self._do_run_tests, name="aura-tests", daemon=True
            ).start()
            return None
        return self._do_run_tests()

    def get_build_log(self) -> list[str]:
        return list(self._log)

    def last_build_status(self) -> dict | None:
        return self._last_result.to_dict() if self._last_result else None

    # ------------------------------------------------------------------
    # Snapshot & rollback
    # ------------------------------------------------------------------

    def snapshot(self, label: str = "") -> dict:
        """
        Create a timestamped tarball of rootfs/ in dist/snapshots/.

        Returns a dict with keys: ``success``, ``snapshot_id``, ``path``,
        ``message``, and ``size_bytes``.
        """
        import tarfile
        t0  = time.monotonic()
        ts  = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        sid = f"{ts}_{label}" if label else ts
        snapshots_dir = os.path.join(self._root, "dist", "snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        out_path = os.path.join(snapshots_dir, f"{sid}.tar.gz")
        rootfs_path = os.path.join(self._root, "rootfs")
        try:
            with tarfile.open(out_path, "w:gz") as tar:
                tar.add(rootfs_path, arcname="rootfs")
            size = os.path.getsize(out_path)
            duration = time.monotonic() - t0
            self._log_line(
                f"Snapshot created: {sid}  ({size/1024:.1f} KB  {duration:.2f}s)"
            )
            logger.info("BuildService: snapshot %r at %s", sid, out_path)
            return {
                "success":     True,
                "snapshot_id": sid,
                "path":        out_path,
                "size_bytes":  size,
                "message":     f"Snapshot {sid} created",
            }
        except Exception as exc:
            msg = f"Snapshot failed: {exc}"
            self._log_line(msg)
            logger.exception("BuildService: %s", msg)
            return {
                "success":     False,
                "snapshot_id": sid,
                "path":        "",
                "size_bytes":  0,
                "message":     msg,
            }

    def list_snapshots(self) -> list[dict]:
        """Return metadata for all available snapshots."""
        snapshots_dir = os.path.join(self._root, "dist", "snapshots")
        if not os.path.isdir(snapshots_dir):
            return []
        results = []
        for entry in sorted(os.scandir(snapshots_dir), key=lambda e: e.name):
            if entry.name.endswith(".tar.gz"):
                sid = entry.name[:-7]   # strip .tar.gz
                results.append({
                    "snapshot_id": sid,
                    "path":        entry.path,
                    "size_bytes":  entry.stat().st_size,
                })
        return results

    def rollback(self, snapshot_id: str) -> dict:
        """
        Restore rootfs/ from a previously created snapshot.

        Returns a dict with ``success`` and ``message``.
        """
        import tarfile
        snapshots_dir = os.path.join(self._root, "dist", "snapshots")
        tar_path = os.path.join(snapshots_dir, f"{snapshot_id}.tar.gz")
        if not os.path.exists(tar_path):
            msg = f"Snapshot not found: {snapshot_id!r}"
            return {"success": False, "message": msg}

        rootfs_path = os.path.join(self._root, "rootfs")
        t0 = time.monotonic()
        try:
            # Extract to a temp location first, then swap
            import tempfile
            with tempfile.TemporaryDirectory(dir=self._root) as tmp_dir:
                with tarfile.open(tar_path, "r:gz") as tar:
                    tar.extractall(tmp_dir)
                extracted = os.path.join(tmp_dir, "rootfs")
                if not os.path.isdir(extracted):
                    return {
                        "success": False,
                        "message": "Snapshot archive missing rootfs/ directory",
                    }
                # Back up current rootfs as a safety net
                backup = rootfs_path + ".pre_rollback"
                if os.path.exists(backup):
                    shutil.rmtree(backup)
                shutil.copytree(rootfs_path, backup)
                # Swap in the restored version
                shutil.rmtree(rootfs_path)
                shutil.copytree(extracted, rootfs_path)

            duration = time.monotonic() - t0
            msg = f"Rolled back to {snapshot_id} in {duration:.2f}s"
            self._log_line(msg)
            logger.info("BuildService: %s", msg)
            return {"success": True, "message": msg}
        except Exception as exc:
            msg = f"Rollback failed: {exc}"
            self._log_line(msg)
            logger.exception("BuildService: %s", msg)
            return {"success": False, "message": msg}

    # ------------------------------------------------------------------
    # Private — rebuild
    # ------------------------------------------------------------------

    def _do_rebuild(self) -> BuildResult:
        if not self._lock.acquire(blocking=False):
            return BuildResult(False, "A build is already in progress")

        t0 = time.monotonic()
        self._log.clear()

        try:
            self._event_bus.publish(Event(
                "BUILD_STARTED", payload={"type": "rootfs"},
                priority=Priority.NORMAL, source="build_service",
            ))

            dist_dir   = os.path.join(self._root, "dist")
            rootfs_src = os.path.join(self._root, "rootfs")
            rootfs_dst = os.path.join(dist_dir,   "rootfs")

            os.makedirs(dist_dir, exist_ok=True)
            self._log_line("=== AURA-AIOSCPU Rootfs Build ===")

            # Step 1: copy base rootfs layout
            self._log_line("Step 1: rootfs layout …")
            _required_dirs = [
                "bin", "etc", "home", "tmp",
                "usr/bin", "usr/lib", "var/log", "var/run",
            ]
            for d in _required_dirs:
                os.makedirs(os.path.join(rootfs_dst, d), exist_ok=True)
            if os.path.exists(rootfs_src):
                _copy_tree(rootfs_src, rootfs_dst)
            self._log_line("  ✓ rootfs layout")

            # Step 2: package Python source
            self._log_line("Step 2: packaging source …")
            pkg_dst = os.path.join(rootfs_dst, "usr", "lib", "aura")
            os.makedirs(pkg_dst, exist_ok=True)
            for pkg in PACKAGES:
                src = os.path.join(self._root, pkg)
                if not os.path.exists(src):
                    continue
                dst = os.path.join(pkg_dst, pkg)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(
                    src, dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
                self._log_line(f"  ✓ packaged {pkg}/")

            # Step 3: entry-point launchers
            self._log_line("Step 3: launchers …")
            _write_launcher(
                os.path.join(dist_dir, "aura"),
                "sys.path.insert(0, os.path.join("
                "os.path.dirname(os.path.abspath(__file__)),"
                " 'rootfs', 'usr', 'lib', 'aura'))",
            )
            _write_launcher(
                os.path.join(rootfs_dst, "bin", "aura"),
                "sys.path.insert(0, '/usr/lib/aura')",
            )
            self._log_line("  ✓ launchers")

            # Step 4: manifest — checksums of source files (not dist copies)
            # so verify_integrity() can compare against the same keys
            self._log_line("Step 4: manifest …")
            repo_path = Path(self._root)
            checksums = {}
            for py_file in sorted(repo_path.rglob("*.py")):
                rel = str(py_file.relative_to(repo_path))
                if any(p in rel for p in (".git", "__pycache__", "dist", "/tmp")):
                    continue
                checksums[rel] = _sha256(py_file)
            with open(os.path.join(dist_dir, "manifest.json"), "w") as fh:
                json.dump({
                    "build_time":  time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "version":     "0.1.0",
                    "total_files": len(checksums),
                    "files":       checksums,
                }, fh, indent=2)
            self._log_line(f"  ✓ manifest ({len(checksums)} source files)")

            duration = time.monotonic() - t0
            self._log_line(f"Build complete in {duration:.2f}s ✓")
            result = BuildResult(True, "Build successful", duration)

        except Exception as exc:
            duration = time.monotonic() - t0
            msg = f"Build failed: {exc}"
            self._log_line(msg)
            logger.exception("BuildService: %s", msg)
            result = BuildResult(False, msg, duration)

        finally:
            self._lock.release()

        self._last_result = result
        self._event_bus.publish(Event(
            "BUILD_COMPLETE", payload=result.to_dict(),
            priority=Priority.HIGH, source="build_service",
        ))
        return result

    # ------------------------------------------------------------------
    # Private — tests
    # ------------------------------------------------------------------

    def _do_run_tests(self) -> BuildResult:
        t0 = time.monotonic()
        self._log_line("=== Running test suite ===")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
                capture_output=True, text=True,
                cwd=self._root, timeout=120,
            )
            output = (proc.stdout + proc.stderr).strip()
            self._log_line(output[-2000:] if len(output) > 2000 else output)
            success  = proc.returncode == 0
            msg      = "All tests passed" if success else "Tests failed"
            result   = BuildResult(success, f"{msg}\n{output[-500:]}", time.monotonic() - t0)
        except subprocess.TimeoutExpired:
            result = BuildResult(False, "Test suite timed out", time.monotonic() - t0)
        except Exception as exc:
            result = BuildResult(False, str(exc), time.monotonic() - t0)

        self._event_bus.publish(Event(
            "TEST_COMPLETE", payload=result.to_dict(),
            priority=Priority.NORMAL, source="build_service",
        ))
        return result

    def _log_line(self, msg: str) -> None:
        self._log.append(msg)
        logger.info("BuildService: %s", msg)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_launcher(path: str, sys_path_stmt: str) -> None:
    with open(path, "w") as fh:
        fh.write("#!/usr/bin/env python\n")
        fh.write('"""AURA-AIOSCPU launcher."""\n')
        fh.write("import os, sys\n")
        fh.write(f"{sys_path_stmt}\n")
        fh.write("from launch.launcher import main\n")
        fh.write("if __name__ == '__main__':\n    main()\n")
    os.chmod(path, 0o755)


def _copy_tree(src: str, dst: str) -> None:
    """Copy a directory tree, skipping __pycache__ and .pyc files."""
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(root, src)
        dest_dir = os.path.join(dst, rel)
        os.makedirs(dest_dir, exist_ok=True)
        for f in files:
            if not f.endswith(".pyc"):
                shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))
