"""Tests for new AI inference engines — Ollama and OpenAI-compatible."""

import json
import os
import sys
import threading
import http.server
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.model_manager import (
    OllamaInferenceEngine,
    OpenAIInferenceEngine,
    ModelManager,
    StubInferenceEngine,
)


# ---------------------------------------------------------------------------
# OllamaInferenceEngine tests
# ---------------------------------------------------------------------------

class TestOllamaInferenceEngine:

    def test_instantiation(self):
        engine = OllamaInferenceEngine(model="phi3")
        assert engine is not None

    def test_custom_base_url(self):
        engine = OllamaInferenceEngine(base_url="http://192.168.1.1:11434")
        assert "192.168.1.1" in engine._base_url

    def test_is_available_returns_false_when_not_running(self):
        # No Ollama expected in CI
        result = OllamaInferenceEngine.is_available(
            base_url="http://127.0.0.1:9999"
        )
        assert result is False

    def test_infer_raises_on_unreachable(self):
        engine = OllamaInferenceEngine(
            base_url="http://127.0.0.1:9999", timeout_s=2
        )
        with pytest.raises(RuntimeError, match="Ollama"):
            engine.infer("hello", {})

    def test_infer_against_stub_server(self):
        """Spin up a tiny HTTP server that mimics Ollama's /api/generate."""
        response_data = {"response": "I am AURA running on Ollama."}

        class _FakeOllama(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass  # silence

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                body = json.dumps(response_data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = http.server.HTTPServer(("127.0.0.1", 0), _FakeOllama)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            engine = OllamaInferenceEngine(
                model="phi3",
                base_url=f"http://127.0.0.1:{port}",
            )
            result = engine.infer("test prompt", {"tick": 1})
            assert "AURA" in result
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# OpenAIInferenceEngine tests
# ---------------------------------------------------------------------------

class TestOpenAIInferenceEngine:

    def test_instantiation(self):
        engine = OpenAIInferenceEngine(api_key="sk-test")
        assert engine is not None

    def test_default_model(self):
        engine = OpenAIInferenceEngine(api_key="sk-test")
        assert engine._model == "gpt-4o-mini"

    def test_custom_model(self):
        engine = OpenAIInferenceEngine(api_key="sk-test", model="gpt-4o")
        assert engine._model == "gpt-4o"

    def test_infer_raises_without_api_key(self):
        engine = OpenAIInferenceEngine(api_key="", api_base="http://127.0.0.1:1")
        with pytest.raises(RuntimeError, match="API key"):
            engine.infer("hello", {})

    def test_infer_against_stub_server(self):
        """Spin up a tiny HTTP server that mimics OpenAI /v1/chat/completions."""
        response_data = {
            "choices": [
                {"message": {"role": "assistant", "content": "Hello from mock!"}}
            ]
        }

        class _FakeOpenAI(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                body = json.dumps(response_data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = http.server.HTTPServer(("127.0.0.1", 0), _FakeOpenAI)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            engine = OpenAIInferenceEngine(
                api_key="sk-test",
                api_base=f"http://127.0.0.1:{port}/v1",
            )
            result = engine.infer("test", {})
            assert "Hello from mock!" == result
        finally:
            server.shutdown()

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        engine = OpenAIInferenceEngine()
        assert engine._api_key == "sk-from-env"


# ---------------------------------------------------------------------------
# ModelManager.load_ollama / load_openai integration
# ---------------------------------------------------------------------------

class TestModelManagerApiBackends:

    def test_load_ollama_fails_when_unreachable(self, tmp_path):
        mgr = ModelManager(models_dir=str(tmp_path))
        result = mgr.load_ollama(
            model="phi3",
            base_url="http://127.0.0.1:9999",
        )
        assert result is False
        # Falls back to stub
        assert mgr.active_model_name() is None

    def test_load_openai_activates_engine(self, tmp_path):
        mgr = ModelManager(models_dir=str(tmp_path))
        result = mgr.load_openai(model="gpt-4o-mini", api_key="sk-test")
        assert result is True
        assert mgr.active_model_name() == "openai:gpt-4o-mini"

    def test_infer_still_works_after_load_openai_no_actual_call(self, tmp_path):
        """Verify that setting the OpenAI engine doesn't break infer() interface."""
        mgr = ModelManager(models_dir=str(tmp_path))
        mgr.load_openai(model="gpt-4o-mini", api_key="sk-test")
        # We don't call infer() here (would need real key); just confirm
        # the active engine is NOT a StubInferenceEngine.
        with mgr._lock:
            assert not isinstance(mgr._engine, StubInferenceEngine)
