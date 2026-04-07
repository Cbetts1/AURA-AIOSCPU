"""Tests for hal.devices.storage — VStorageDevice (SQLite-backed)."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hal.devices.storage import VStorageDevice


@pytest.fixture
def db(tmp_path):
    """Return a started VStorageDevice backed by a temporary file."""
    path = str(tmp_path / "test_aura.db")
    device = VStorageDevice(path)
    device.start()
    yield device
    device.stop()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_device_starts_online(db):
    assert db.status() == "online"


def test_device_stops_offline(tmp_path):
    device = VStorageDevice(str(tmp_path / "t.db"))
    device.start()
    device.stop()
    assert device.status() == "offline"


def test_repr_contains_path(tmp_path):
    device = VStorageDevice(str(tmp_path / "t.db"))
    assert "VStorageDevice" in repr(device)


# ---------------------------------------------------------------------------
# Key-Value store
# ---------------------------------------------------------------------------

def test_kv_set_and_get(db):
    db.kv_set("test", "greeting", "hello")
    assert db.kv_get("test", "greeting") == "hello"


def test_kv_get_missing_returns_default(db):
    assert db.kv_get("ns", "missing", "default") == "default"


def test_kv_set_overwrites(db):
    db.kv_set("ns", "key", "first")
    db.kv_set("ns", "key", "second")
    assert db.kv_get("ns", "key") == "second"


def test_kv_set_various_types(db):
    db.kv_set("types", "int",   42)
    db.kv_set("types", "float", 3.14)
    db.kv_set("types", "list",  [1, 2, 3])
    db.kv_set("types", "dict",  {"a": 1})
    assert db.kv_get("types", "int")   == 42
    assert db.kv_get("types", "float") == pytest.approx(3.14)
    assert db.kv_get("types", "list")  == [1, 2, 3]
    assert db.kv_get("types", "dict")  == {"a": 1}


def test_kv_delete(db):
    db.kv_set("ns", "key", "value")
    db.kv_delete("ns", "key")
    assert db.kv_get("ns", "key") is None


def test_kv_keys_empty_namespace(db):
    assert db.kv_keys("empty_ns") == []


def test_kv_keys_returns_all(db):
    db.kv_set("ns2", "a", 1)
    db.kv_set("ns2", "b", 2)
    db.kv_set("ns2", "c", 3)
    keys = db.kv_keys("ns2")
    assert sorted(keys) == ["a", "b", "c"]


def test_kv_namespace_isolation(db):
    db.kv_set("ns_a", "key", "alpha")
    db.kv_set("ns_b", "key", "beta")
    assert db.kv_get("ns_a", "key") == "alpha"
    assert db.kv_get("ns_b", "key") == "beta"


# ---------------------------------------------------------------------------
# File store
# ---------------------------------------------------------------------------

def test_file_write_and_read(db):
    db.file_write("/etc/test.conf", b"data=1\n")
    assert db.file_read("/etc/test.conf") == b"data=1\n"


def test_file_read_missing_raises(db):
    with pytest.raises(FileNotFoundError):
        db.file_read("/nonexistent/path.txt")


def test_file_exists_true(db):
    db.file_write("/tmp/x.txt", b"hi")
    assert db.file_exists("/tmp/x.txt") is True


def test_file_exists_false(db):
    assert db.file_exists("/tmp/definitely_not_there.txt") is False


def test_file_overwrite(db):
    db.file_write("/tmp/f.txt", b"v1")
    db.file_write("/tmp/f.txt", b"v2")
    assert db.file_read("/tmp/f.txt") == b"v2"


def test_file_delete(db):
    db.file_write("/tmp/del.txt", b"bye")
    db.file_delete("/tmp/del.txt")
    assert db.file_exists("/tmp/del.txt") is False


def test_file_list_prefix(db):
    db.file_write("/logs/2024-01.log", b"a")
    db.file_write("/logs/2024-02.log", b"b")
    db.file_write("/etc/aura.conf",    b"c")
    logs = db.file_list("/logs/")
    assert len(logs) == 2
    assert all(p.startswith("/logs/") for p in logs)


def test_file_list_empty_prefix(db):
    db.file_write("/a/1.txt", b"1")
    db.file_write("/b/2.txt", b"2")
    all_files = db.file_list()
    assert len(all_files) >= 2


def test_file_binary_data(db):
    binary = bytes(range(256))
    db.file_write("/bin/data", binary)
    assert db.file_read("/bin/data") == binary


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_storage_stats_empty(db):
    stats = db.storage_stats()
    assert "kv_entries"    in stats
    assert "file_count"    in stats
    assert "file_bytes"    in stats
    assert "db_size_bytes" in stats


def test_storage_stats_counts(db):
    db.kv_set("ns", "k1", "v1")
    db.kv_set("ns", "k2", "v2")
    db.file_write("/f1.txt", b"hello")
    stats = db.storage_stats()
    assert stats["kv_entries"] >= 2
    assert stats["file_count"] >= 1
    assert stats["file_bytes"] >= 5


def test_storage_stats_db_size(tmp_path):
    device = VStorageDevice(str(tmp_path / "sized.db"))
    device.start()
    device.file_write("/big.bin", b"x" * 10_000)
    stats = device.storage_stats()
    assert stats["db_size_bytes"] > 0
    device.stop()
