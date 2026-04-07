"""
AURA-AIOSCPU Virtual Storage Device
=====================================
A SQLite-backed virtual block-storage device.

Provides two storage surfaces:

Key-Value store
    namespace:key → value  (configs, runtime state, caches)

File store
    virtual path → bytes   (log files, model data, user files)

Why SQLite?
-----------
- Ships in the Python standard library — zero external dependencies.
- Runs on ARM64 / Android / Termux without any native compilation.
- ACID compliant — safe for concurrent reads from multiple threads.
- Single-file database — easy to back up and copy to an SD card.
"""

import logging
import os
import pickle
import sqlite3
import threading
import time

from hal.devices import VDevice

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv_store (
    namespace TEXT    NOT NULL,
    key       TEXT    NOT NULL,
    value     BLOB,
    updated   REAL,
    PRIMARY KEY (namespace, key)
);
CREATE TABLE IF NOT EXISTS file_store (
    path      TEXT    PRIMARY KEY,
    data      BLOB,
    size      INTEGER,
    updated   REAL
);
CREATE INDEX IF NOT EXISTS idx_kv_ns       ON kv_store  (namespace);
CREATE INDEX IF NOT EXISTS idx_file_parent ON file_store (path);
"""


class VStorageDevice(VDevice):
    """
    Virtual block-storage device backed by a single SQLite database.

    Thread-safe: a single write-lock serialises all mutations while
    reads run concurrently via SQLite's default reader model.
    """

    DEVICE_TYPE = "storage"

    def __init__(self, db_path: str):
        self._db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit
        )
        self._conn.executescript(_SCHEMA)
        logger.info("VStorageDevice: online at %r", self._db_path)

    def stop(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        logger.info("VStorageDevice: offline")

    def status(self) -> str:
        return "online" if self._conn else "offline"

    # ------------------------------------------------------------------
    # Key-Value store
    # ------------------------------------------------------------------

    def kv_set(self, namespace: str, key: str, value) -> None:
        """Write any pickle-serialisable value."""
        data = pickle.dumps(value)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,?,?)",
                (namespace, key, data, time.time()),
            )

    def kv_get(self, namespace: str, key: str, default=None):
        """Read a value; returns *default* if the key does not exist."""
        row = self._conn.execute(
            "SELECT value FROM kv_store WHERE namespace=? AND key=?",
            (namespace, key),
        ).fetchone()
        return pickle.loads(row[0]) if row else default

    def kv_delete(self, namespace: str, key: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM kv_store WHERE namespace=? AND key=?",
                (namespace, key),
            )

    def kv_keys(self, namespace: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT key FROM kv_store WHERE namespace=?", (namespace,)
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # File store
    # ------------------------------------------------------------------

    def file_write(self, path: str, data: bytes) -> None:
        """Write raw bytes to a virtual file path (creates or replaces)."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO file_store VALUES (?,?,?,?)",
                (path, data, len(data), time.time()),
            )

    def file_read(self, path: str) -> bytes:
        """Read raw bytes; raises FileNotFoundError if path does not exist."""
        row = self._conn.execute(
            "SELECT data FROM file_store WHERE path=?", (path,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"VStorageDevice: no file at {path!r}")
        return bytes(row[0])

    def file_exists(self, path: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM file_store WHERE path=?", (path,)
        ).fetchone() is not None

    def file_list(self, prefix: str = "") -> list[str]:
        rows = self._conn.execute(
            "SELECT path FROM file_store WHERE path LIKE ?",
            (prefix + "%",),
        ).fetchall()
        return [r[0] for r in rows]

    def file_delete(self, path: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM file_store WHERE path=?", (path,)
            )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def storage_stats(self) -> dict:
        """Return a quick summary of storage utilisation."""
        kv_count = self._conn.execute(
            "SELECT COUNT(*) FROM kv_store"
        ).fetchone()[0]
        fc, fb = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size),0) FROM file_store"
        ).fetchone()
        db_size = (
            os.path.getsize(self._db_path)
            if os.path.exists(self._db_path) else 0
        )
        return {
            "kv_entries":    kv_count,
            "file_count":    fc,
            "file_bytes":    fb,
            "db_size_bytes": db_size,
        }

    def __repr__(self):
        return f"VStorageDevice(path={self._db_path!r}, status={self.status()})"
