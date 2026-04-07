"""
AURA-AIOSCPU Build Manifest
==============================
Reproducible build manifest with SHA256 integrity verification.

The manifest captures:
  - build timestamp
  - source commit hash (if git available)
  - rootfs partition layout
  - SHA256 of every file in the rootfs
  - build environment metadata

Determinism guarantee
---------------------
Given the same source tree + config + host architecture, every build
produces the same file set and the same content hashes. Timestamps in
the manifest are the ONLY non-deterministic field and are explicitly
marked as such.

Usage::

    # Generate
    from tools.manifest import build_manifest, write_manifest
    m = build_manifest(rootfs_path="rootfs/")
    write_manifest(m, "rootfs/system/manifest.json")

    # Verify
    from tools.manifest import verify_manifest, load_manifest
    manifest = load_manifest("rootfs/system/manifest.json")
    ok, diffs = verify_manifest(manifest, rootfs_path="rootfs/")
    if not ok:
        for d in diffs: print(d)
"""

import hashlib
import json
import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFEST_VERSION = "1.0"
_MANIFEST_PATH    = os.path.join("rootfs", "system", "manifest.json")

# Files to exclude from the manifest (never hash these)
_EXCLUDE_PATTERNS = frozenset({
    "aura.db", "aura.db-shm", "aura.db-wal",  # SQLite WAL files
    "boot.log", "override_audit.jsonl",          # runtime logs
    "aura_events.log",                           # log output
    ".write_probe", ".aura_probe",               # temp probe files
    ".aura_write_probe",
})
_EXCLUDE_DIRS = frozenset({"tmp", "overlay", "mnt"})


# ---------------------------------------------------------------------------
# SHA256 helper
# ---------------------------------------------------------------------------

def _sha256(path: str) -> str:
    """Return the SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Build manifest
# ---------------------------------------------------------------------------

def build_manifest(rootfs_path: str | None = None) -> dict:
    """
    Build a SHA256 manifest of the rootfs.

    Returns a dict ready to be serialised as JSON.
    """
    if rootfs_path is None:
        rootfs_path = os.path.join(_REPO_ROOT, "rootfs")
    rootfs_path = os.path.abspath(rootfs_path)

    files: dict[str, str] = {}
    total_size = 0

    for dirpath, dirnames, filenames in os.walk(rootfs_path):
        # Skip excluded directories (in-place modification to prune walk)
        rel_dir = os.path.relpath(dirpath, rootfs_path)
        top_dir = rel_dir.split(os.sep)[0]
        if top_dir in _EXCLUDE_DIRS:
            dirnames.clear()
            continue

        for filename in sorted(filenames):
            if filename in _EXCLUDE_PATTERNS:
                continue
            full_path = os.path.join(dirpath, filename)
            rel_path  = os.path.relpath(full_path, rootfs_path)
            try:
                digest = _sha256(full_path)
                files[rel_path] = digest
                total_size += os.path.getsize(full_path)
            except (OSError, PermissionError):
                pass

    return {
        "version":       _MANIFEST_VERSION,
        "timestamp":     time.time(),         # non-deterministic (marked)
        "timestamp_note": "timestamps are the only non-deterministic field",
        "rootfs":        rootfs_path,
        "commit":        _get_commit(),
        "environment":   _get_environment(),
        "file_count":    len(files),
        "total_size":    total_size,
        "files":         dict(sorted(files.items())),
    }


# ---------------------------------------------------------------------------
# Write / load
# ---------------------------------------------------------------------------

def write_manifest(manifest: dict, path: str | None = None) -> str:
    """Write manifest to path. Returns the path written."""
    if path is None:
        path = os.path.join(_REPO_ROOT, _MANIFEST_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    logger.info("manifest: written to %r (%d files)", path,
                manifest.get("file_count", 0))
    return path


def load_manifest(path: str | None = None) -> dict:
    """Load a manifest from disk."""
    if path is None:
        path = os.path.join(_REPO_ROOT, _MANIFEST_PATH)
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify_manifest(manifest: dict,
                    rootfs_path: str | None = None) -> tuple[bool, list[str]]:
    """
    Verify the live rootfs against a manifest.

    Returns (ok, diffs) where diffs is a list of human-readable discrepancy
    strings.  ok=True only when diffs is empty.
    """
    if rootfs_path is None:
        rootfs_path = manifest.get("rootfs",
                                   os.path.join(_REPO_ROOT, "rootfs"))

    expected: dict[str, str] = manifest.get("files", {})
    diffs: list[str] = []

    for rel_path, expected_hash in expected.items():
        full_path = os.path.join(rootfs_path, rel_path)
        if not os.path.isfile(full_path):
            diffs.append(f"MISSING  {rel_path}")
            continue
        actual_hash = _sha256(full_path)
        if actual_hash != expected_hash:
            diffs.append(
                f"MODIFIED {rel_path}\n"
                f"  expected {expected_hash[:16]}...\n"
                f"  actual   {actual_hash[:16]}..."
            )

    # Check for new files not in manifest
    for dirpath, dirnames, filenames in os.walk(rootfs_path):
        rel_dir = os.path.relpath(dirpath, rootfs_path)
        top_dir = rel_dir.split(os.sep)[0]
        if top_dir in _EXCLUDE_DIRS:
            dirnames.clear()
            continue
        for filename in filenames:
            if filename in _EXCLUDE_PATTERNS:
                continue
            full_path = os.path.join(dirpath, filename)
            rel_path  = os.path.relpath(full_path, rootfs_path)
            if rel_path not in expected:
                diffs.append(f"NEW      {rel_path}")

    return (len(diffs) == 0), diffs


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def get_provenance() -> dict:
    """
    Return build provenance: commit, timestamp, environment.

    Used by `aura provenance` command.
    """
    manifest_path = os.path.join(_REPO_ROOT, _MANIFEST_PATH)
    manifest: dict = {}
    if os.path.isfile(manifest_path):
        try:
            manifest = load_manifest(manifest_path)
        except Exception:
            pass
    return {
        "build_timestamp":  manifest.get("timestamp"),
        "build_time_human": (
            time.ctime(manifest["timestamp"])
            if manifest.get("timestamp") else "unknown"
        ),
        "commit":           manifest.get("commit", _get_commit()),
        "environment":      manifest.get("environment", _get_environment()),
        "manifest_path":    manifest_path,
        "manifest_exists":  os.path.isfile(manifest_path),
        "file_count":       manifest.get("file_count", 0),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_commit() -> str:
    """Return current git HEAD commit hash, or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "-C", _REPO_ROOT, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _get_environment() -> dict:
    """Return build-time environment metadata."""
    import platform
    return {
        "python":   platform.python_version(),
        "platform": platform.system(),
        "arch":     platform.machine(),
    }
