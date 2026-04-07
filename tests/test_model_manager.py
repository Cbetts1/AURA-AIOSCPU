"""Tests for models.model_manager — ModelManager AI model lifecycle."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.model_manager import (
    ModelManager, ModelInfo, StubInferenceEngine,
    _REGISTRY_FILENAME,
)


# ---------------------------------------------------------------------------
# ModelInfo unit tests
# ---------------------------------------------------------------------------

def test_model_info_defaults():
    info = ModelInfo("test-model", "/models/test.gguf")
    assert info.name        == "test-model"
    assert info.path        == "/models/test.gguf"
    assert info.model_type  == "gguf"
    assert info.size_mb     == 0.0
    assert info.loaded      is False
    assert info.load_time   is None


def test_model_info_to_dict():
    info = ModelInfo("m", "/p", "gguf", 1.5, "A test model")
    d    = info.to_dict()
    assert d["name"]        == "m"
    assert d["path"]        == "/p"
    assert d["model_type"]  == "gguf"
    assert d["size_mb"]     == pytest.approx(1.5)
    assert d["description"] == "A test model"
    assert d["loaded"]      is False


# ---------------------------------------------------------------------------
# StubInferenceEngine unit tests
# ---------------------------------------------------------------------------

def test_stub_engine_returns_string():
    engine = StubInferenceEngine()
    result = engine.infer("hello", {})
    assert isinstance(result, str)
    assert len(result) > 0


def test_stub_engine_includes_prompt():
    engine = StubInferenceEngine()
    result = engine.infer("test prompt", {})
    assert "test prompt" in result


def test_stub_engine_no_exception():
    engine = StubInferenceEngine()
    engine.infer("x", {"tick": 1, "services": []})  # should not raise


# ---------------------------------------------------------------------------
# ModelManager tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr(tmp_path):
    return ModelManager(models_dir=str(tmp_path), max_memory_mb=512)


def test_model_manager_instantiates(mgr):
    assert mgr is not None


def test_list_models_empty_initially(mgr):
    models = mgr.list_models()
    assert isinstance(models, list)
    assert len(models) == 0


def test_active_model_none_initially(mgr):
    assert mgr.active_model_name() is None


def test_register_model(mgr):
    mgr.register("phi", "/models/phi.gguf", description="Phi-2")
    models = mgr.list_models()
    assert len(models) == 1
    assert models[0]["name"] == "phi"


def test_register_model_with_real_file(mgr, tmp_path):
    dummy = tmp_path / "dummy.gguf"
    dummy.write_bytes(b"x" * 1024)
    info = mgr.register("dummy", str(dummy), model_type="gguf")
    assert info.size_mb > 0


def test_register_relative_path(mgr, tmp_path):
    dummy = tmp_path / "rel.gguf"
    dummy.write_bytes(b"y" * 512)
    # relative path should be resolved relative to models_dir
    info = mgr.register("rel", "rel.gguf")
    assert os.path.isabs(info.path)


def test_register_persists_registry(mgr, tmp_path):
    mgr.register("saved", "/p/saved.gguf")
    reg_path = tmp_path / _REGISTRY_FILENAME
    assert reg_path.exists()
    with open(reg_path) as fh:
        data = json.load(fh)
    names = [m["name"] for m in data["models"]]
    assert "saved" in names


def test_registry_loads_on_init(tmp_path):
    # First manager registers a model
    m1 = ModelManager(models_dir=str(tmp_path), max_memory_mb=256)
    m1.register("persisted", "/x/y.gguf")

    # Second manager should load the same registry
    m2 = ModelManager(models_dir=str(tmp_path), max_memory_mb=256)
    names = [m["name"] for m in m2.list_models()]
    assert "persisted" in names


def test_load_nonexistent_model(mgr):
    ok = mgr.load("does_not_exist")
    assert ok is False


def test_load_missing_file(mgr):
    mgr.register("ghost", "/nonexistent/ghost.gguf")
    ok = mgr.load("ghost")
    assert ok is False


def test_load_too_large_model(mgr, tmp_path):
    huge = tmp_path / "huge.gguf"
    huge.write_bytes(b"x")  # tiny file
    info = mgr.register("huge", str(huge))
    # Override size to exceed budget
    info.size_mb = 9999.0
    ok = mgr.load("huge")
    assert ok is False


def test_load_stub_fallback_for_real_file(mgr, tmp_path):
    """A real file that can't be loaded by llama-cpp falls back to stub."""
    f = tmp_path / "fake.gguf"
    f.write_bytes(b"this is not a real model")
    mgr.register("fake", str(f), model_type="gguf")
    ok = mgr.load("fake")
    # Should return True (stub fallback), not crash
    assert ok is True
    assert mgr.active_model_name() == "fake"


def test_infer_with_stub_engine(mgr):
    result = mgr.infer("hello", {"tick": 1})
    assert isinstance(result, str)


def test_unload_resets_active(mgr, tmp_path):
    f = tmp_path / "m.gguf"
    f.write_bytes(b"fake")
    mgr.register("m", str(f))
    mgr.load("m")
    assert mgr.active_model_name() == "m"
    mgr.unload()
    assert mgr.active_model_name() is None


def test_unload_uses_stub_engine(mgr, tmp_path):
    f = tmp_path / "n.gguf"
    f.write_bytes(b"fake")
    mgr.register("n", str(f))
    mgr.load("n")
    mgr.unload()
    # After unload, infer should still work (stub)
    result = mgr.infer("test", {})
    assert isinstance(result, str)


def test_scan_models_dir_empty(mgr):
    found = mgr.scan_models_dir()
    assert found == []


def test_scan_models_dir_finds_files(mgr, tmp_path):
    (tmp_path / "alpha.gguf").write_bytes(b"x")
    (tmp_path / "beta.bin").write_bytes(b"y")
    (tmp_path / "not_a_model.txt").write_bytes(b"z")
    found = mgr.scan_models_dir()
    assert "alpha" in found
    assert "beta"  in found
    assert len(found) == 2  # .txt not included


def test_scan_models_dir_no_duplicates(mgr, tmp_path):
    (tmp_path / "gamma.gguf").write_bytes(b"x")
    mgr.scan_models_dir()  # first scan registers gamma
    found = mgr.scan_models_dir()  # second scan should find nothing new
    assert found == []


def test_thread_safe_infer(mgr):
    """Concurrent infer calls must not raise."""
    import threading
    errors = []

    def call():
        try:
            mgr.infer("q", {})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
