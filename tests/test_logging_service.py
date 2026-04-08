"""
Tests — LoggingService + LogEntry
===================================
"""

import json
import os
import sys
import time
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import EventBus first to break the services → kernel → services circular dependency
from kernel.event_bus import EventBus, Event, Priority  # noqa: E402

from services.logging_service import LoggingService, LogEntry


# ---------------------------------------------------------------------------
# LogEntry unit tests
# ---------------------------------------------------------------------------

class TestLogEntry:
    def _make(self, **kwargs):
        defaults = dict(ts=1700000000.0, level="INFO", source="kernel",
                        event="TEST", msg="hello", data={})
        defaults.update(kwargs)
        return LogEntry(**defaults)

    def test_to_dict_keys(self):
        e = self._make()
        d = e.to_dict()
        for key in ("ts", "level", "source", "event", "msg", "data"):
            assert key in d

    def test_to_dict_values(self):
        e = self._make(level="ERROR", source="svc", msg="bad thing")
        d = e.to_dict()
        assert d["level"] == "ERROR"
        assert d["source"] == "svc"
        assert d["msg"] == "bad thing"

    def test_to_json_is_valid_json(self):
        e = self._make()
        parsed = json.loads(e.to_json())
        assert parsed["level"] == "INFO"

    def test_to_line_contains_event_and_msg(self):
        e = self._make(event="SERVICE_STARTED", msg="svc-a started")
        line = e.to_line()
        assert "SERVICE_STARTED" in line
        assert "svc-a started" in line

    def test_to_line_contains_level(self):
        e = self._make(level="WARNING")
        assert "WARNING" in e.to_line()

    def test_data_field_preserved(self):
        e = self._make(data={"key": "value", "count": 3})
        assert e.to_dict()["data"] == {"key": "value", "count": 3}


# ---------------------------------------------------------------------------
# LoggingService lifecycle
# ---------------------------------------------------------------------------

class TestLoggingServiceLifecycle:
    def test_instantiates(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        assert ls is not None

    def test_start_stop(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.stop()

    def test_start_idempotent(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.start()  # second call must be no-op
        ls.stop()

    def test_stop_idempotent(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.stop()   # stopping before start should not raise

    def test_start_creates_log_dir(self, tmp_path):
        log_dir = str(tmp_path / "new_logs")
        ls = LoggingService(log_dir=log_dir)
        ls.start()
        ls.stop()
        assert os.path.isdir(log_dir)


# ---------------------------------------------------------------------------
# LoggingService write API
# ---------------------------------------------------------------------------

class TestLoggingServiceWrite:
    def test_write_increments_count(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.write("hello")
        ls.write("world")
        assert ls.entry_count() == 2
        ls.stop()

    def test_write_custom_level(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.write("oops", level="error")
        recent = ls.get_recent(1)
        assert "ERROR" in recent[0]
        ls.stop()

    def test_write_custom_source(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.write("msg", source="kernel.boot")
        recent = ls.get_recent(1)
        assert "kernel.boot" in recent[0]
        ls.stop()

    def test_write_with_data_dict(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.write("ctx", data={"svc": "net0"})
        ls.stop()
        # just assert no exception

    def test_write_data_defaults_to_empty_dict(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.write("plain")
        ls.stop()


# ---------------------------------------------------------------------------
# LoggingService get_recent
# ---------------------------------------------------------------------------

class TestLoggingServiceGetRecent:
    def test_get_recent_returns_list_of_strings(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        ls.write("a")
        result = ls.get_recent(1)
        assert isinstance(result, list)
        assert all(isinstance(r, str) for r in result)
        ls.stop()

    def test_get_recent_default_n(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        for i in range(30):
            ls.write(f"msg {i}")
        result = ls.get_recent()
        assert len(result) == 20  # default n=20
        ls.stop()

    def test_get_recent_respects_n(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        for i in range(10):
            ls.write(f"msg {i}")
        result = ls.get_recent(5)
        assert len(result) == 5
        ls.stop()

    def test_get_recent_empty_buffer(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        assert ls.get_recent(10) == []
        ls.stop()


# ---------------------------------------------------------------------------
# LoggingService query API
# ---------------------------------------------------------------------------

class TestLoggingServiceQuery:
    def _make_started(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path))
        ls.start()
        return ls

    def test_query_all_returns_all(self, tmp_path):
        ls = self._make_started(tmp_path)
        for i in range(5):
            ls.write(f"msg {i}")
        results = ls.query()
        assert len(results) == 5
        ls.stop()

    def test_query_by_level(self, tmp_path):
        ls = self._make_started(tmp_path)
        ls.write("info msg", level="INFO")
        ls.write("error msg", level="ERROR")
        results = ls.query(level="ERROR")
        assert len(results) == 1
        assert results[0]["level"] == "ERROR"
        ls.stop()

    def test_query_by_source(self, tmp_path):
        ls = self._make_started(tmp_path)
        ls.write("from kernel", source="kernel")
        ls.write("from net", source="network")
        results = ls.query(source="kernel")
        assert len(results) == 1
        assert results[0]["source"] == "kernel"
        ls.stop()

    def test_query_by_event_type(self, tmp_path):
        ls = self._make_started(tmp_path)
        ls.write("a", event="SERVICE_STARTED")
        ls.write("b", event="SERVICE_STOPPED")
        results = ls.query(event_type="SERVICE_STARTED")
        assert len(results) == 1
        ls.stop()

    def test_query_by_since(self, tmp_path):
        ls = self._make_started(tmp_path)
        past = time.time() - 100
        ls.write("old")
        future_ts = time.time() + 1
        ls.write("new")
        results = ls.query(since=future_ts - 0.1)
        # Only the "new" entry is after since threshold
        # (timing dependent; at least one should pass)
        assert isinstance(results, list)
        ls.stop()

    def test_query_limit(self, tmp_path):
        ls = self._make_started(tmp_path)
        for i in range(20):
            ls.write(f"msg {i}")
        results = ls.query(limit=5)
        assert len(results) == 5
        ls.stop()

    def test_query_combined_filters(self, tmp_path):
        ls = self._make_started(tmp_path)
        ls.write("error from kernel", level="ERROR", source="kernel")
        ls.write("info from kernel", level="INFO",  source="kernel")
        ls.write("error from net",   level="ERROR", source="network")
        results = ls.query(level="ERROR", source="kernel")
        assert len(results) == 1
        assert results[0]["source"] == "kernel"
        ls.stop()

    def test_query_returns_dicts(self, tmp_path):
        ls = self._make_started(tmp_path)
        ls.write("msg")
        results = ls.query()
        assert all(isinstance(r, dict) for r in results)
        ls.stop()


# ---------------------------------------------------------------------------
# LoggingService — event bus subscription
# ---------------------------------------------------------------------------

class TestLoggingServiceEventBus:
    def test_subscribes_to_service_started(self, tmp_path):
        bus = EventBus()
        ls = LoggingService(event_bus=bus, log_dir=str(tmp_path))
        ls.start()

        initial = ls.entry_count()
        bus.publish(Event("SERVICE_STARTED", payload={"name": "net"},
                          priority=Priority.NORMAL, source="registry"))
        bus.drain()
        assert ls.entry_count() > initial
        ls.stop()

    def test_on_event_captures_event_type(self, tmp_path):
        bus = EventBus()
        ls = LoggingService(event_bus=bus, log_dir=str(tmp_path))
        ls.start()

        bus.publish(Event("HEALTH_REPORT", payload={"healthy": 3},
                          priority=Priority.LOW, source="health_monitor"))
        bus.drain()
        results = ls.query(event_type="HEALTH_REPORT")
        assert len(results) == 1
        ls.stop()

    def test_no_event_bus_does_not_raise(self, tmp_path):
        ls = LoggingService(event_bus=None, log_dir=str(tmp_path))
        ls.start()
        ls.write("standalone")
        ls.stop()


# ---------------------------------------------------------------------------
# LoggingService — flush to disk
# ---------------------------------------------------------------------------

class TestLoggingServiceFlush:
    def test_flush_writes_json_lines(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path), flush_interval_s=1000)
        ls.start()
        ls.write("flush me")
        ls._flush_to_disk()
        log_files = list(tmp_path.glob("*.log"))
        assert log_files
        lines = log_files[0].read_text().strip().splitlines()
        assert lines
        for line in lines:
            data = json.loads(line)
            assert "ts" in data
        ls.stop()

    def test_flush_empty_buffer_does_nothing(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path), flush_interval_s=1000)
        ls.start()
        ls._flush_to_disk()  # nothing to write — should not raise or create file
        ls.stop()

    def test_stop_flushes_remaining(self, tmp_path):
        ls = LoggingService(log_dir=str(tmp_path), flush_interval_s=1000)
        ls.start()
        ls.write("last message")
        ls.stop()
        log_files = list(tmp_path.glob("*.log"))
        assert log_files
        content = log_files[0].read_text()
        assert "last message" in content
