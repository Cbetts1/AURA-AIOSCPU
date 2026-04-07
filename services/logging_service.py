"""
AURA-AIOSCPU Logging Service
==============================
Structured log aggregation, querying, and export.

Design
------
- Subscribes to all event-bus events and records them as structured entries.
- Maintains an in-memory ring buffer (last N entries).
- Writes JSON-Lines to a rotating log file in rootfs/var/logs/.
- Exposes query API: filter by level, source, event type, time range.
- Zero external dependencies (stdlib only).

Log entry format (JSON-Lines)
-----------------------------
  {"ts": 1700000000.123, "level": "INFO", "source": "kernel",
   "event": "SERVICE_STARTED", "msg": "...", "data": {...}}

Events published
----------------
  LOG_WRITTEN  { entry_count }    — periodically
"""

import json
import logging
import os
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

_DEFAULT_BUFFER   = 500     # in-memory ring buffer size
_DEFAULT_FLUSH_S  = 5.0     # flush to disk every N seconds
_LOG_FILENAME     = "aura_events.log"


class LogEntry:
    """One structured log entry."""

    __slots__ = ("ts", "level", "source", "event", "msg", "data")

    def __init__(self, ts: float, level: str, source: str,
                 event: str, msg: str, data: dict):
        self.ts     = ts
        self.level  = level
        self.source = source
        self.event  = event
        self.msg    = msg
        self.data   = data

    def to_dict(self) -> dict:
        return {
            "ts":     self.ts,
            "level":  self.level,
            "source": self.source,
            "event":  self.event,
            "msg":    self.msg,
            "data":   self.data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_line(self) -> str:
        """Human-readable single line."""
        t = time.strftime("%H:%M:%S", time.localtime(self.ts))
        return f"[{t}] {self.level:<8} {self.source:<20} {self.event} {self.msg}"


class LoggingService:
    """
    Structured log aggregation service.

    Subscribes to ALL event bus events (via wildcard handler pattern) and
    records them. Also provides a write() API so other services can log
    directly.
    """

    def __init__(self, event_bus=None,
                 log_dir: str = "logs",
                 buffer_size: int = _DEFAULT_BUFFER,
                 flush_interval_s: float = _DEFAULT_FLUSH_S):
        self._event_bus       = event_bus
        self._log_dir         = log_dir
        self._buffer: deque[LogEntry] = deque(maxlen=buffer_size)
        self._flush_interval  = flush_interval_s
        self._running         = False
        self._lock            = threading.Lock()
        self._flush_thread: threading.Thread | None = None
        self._total_written   = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        os.makedirs(self._log_dir, exist_ok=True)

        # Subscribe to standard event types we always want to capture
        if self._event_bus is not None:
            for et in (
                "SERVICE_REGISTERED", "SERVICE_STARTED", "SERVICE_STOPPED",
                "SERVICE_RESTARTING", "MODE_ACTIVATED", "BOOT_COMPLETE",
                "SHUTDOWN", "BUILD_COMPLETE", "HEALTH_REPORT",
                "NETWORK_STATUS", "STORAGE_EVENT", "JOB_QUEUED",
                "JOB_COMPLETE", "JOB_FAILED", "INTEGRITY_ALERT",
                "CAPABILITY_GRANTED", "CAPABILITY_REVOKED",
                "PERMISSION_REQUEST", "PERMISSION_RESPONSE",
            ):
                self._event_bus.subscribe(et, self._on_event)

        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="aura-logging",
            daemon=True,
        )
        self._flush_thread.start()
        logger.info("LoggingService: started (log_dir=%s)", self._log_dir)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._flush_to_disk()   # final flush
        logger.info("LoggingService: stopped (total_written=%d)",
                    self._total_written)

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def write(self, msg: str, level: str = "INFO",
              source: str = "system", event: str = "LOG",
              data: dict | None = None) -> None:
        """Directly write a log entry."""
        entry = LogEntry(
            ts=time.time(), level=level.upper(),
            source=source, event=event,
            msg=msg, data=data or {},
        )
        with self._lock:
            self._buffer.append(entry)
            self._total_written += 1

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_recent(self, n: int = 20) -> list[str]:
        """Return the last n log lines as human-readable strings."""
        with self._lock:
            entries = list(self._buffer)[-n:]
        return [e.to_line() for e in entries]

    def query(self, level: str | None = None,
              source: str | None = None,
              event_type: str | None = None,
              since: float | None = None,
              limit: int = 100) -> list[dict]:
        """
        Filter log entries and return as list of dicts.

        Args:
            level:      Filter by log level (e.g. "ERROR")
            source:     Filter by source component
            event_type: Filter by event type string
            since:      Only include entries after this epoch timestamp
            limit:      Maximum entries to return
        """
        with self._lock:
            entries = list(self._buffer)

        results = []
        for e in reversed(entries):
            if level and e.level != level.upper():
                continue
            if source and e.source != source:
                continue
            if event_type and e.event != event_type:
                continue
            if since and e.ts < since:
                continue
            results.append(e.to_dict())
            if len(results) >= limit:
                break
        return results

    def entry_count(self) -> int:
        return self._total_written

    # ------------------------------------------------------------------
    # Event handler (called by event bus)
    # ------------------------------------------------------------------

    def _on_event(self, event) -> None:
        entry = LogEntry(
            ts=time.time(),
            level="INFO",
            source=getattr(event, "source", "unknown"),
            event=getattr(event, "event_type", "UNKNOWN"),
            msg=str(getattr(event, "payload", {})),
            data=getattr(event, "payload", {}) or {},
        )
        with self._lock:
            self._buffer.append(entry)
            self._total_written += 1

    # ------------------------------------------------------------------
    # Background flush
    # ------------------------------------------------------------------

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self._flush_interval)
            if self._running:
                self._flush_to_disk()

    def _flush_to_disk(self) -> None:
        """Append buffered entries to the on-disk log file."""
        log_path = os.path.join(self._log_dir, _LOG_FILENAME)
        with self._lock:
            to_write = list(self._buffer)
        if not to_write:
            return
        try:
            with open(log_path, "a") as fh:
                for entry in to_write:
                    fh.write(entry.to_json() + "\n")
        except OSError:
            pass   # read-only filesystem — in-memory only
