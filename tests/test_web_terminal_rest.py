"""Tests for WebTerminalService REST API endpoints."""

import json
import os
import sys
import urllib.request
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.web_terminal import WebTerminalService


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_svc(**kwargs):
    port = _find_free_port()
    return WebTerminalService(
        dispatch_fn=kwargs.pop("dispatch_fn", lambda cmd: f"echo:{cmd}"),
        port=port,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# /api/services
# ---------------------------------------------------------------------------

class TestServicesEndpoint:

    def test_services_endpoint_returns_json(self):
        svc = _make_svc()
        svc.start()
        try:
            with urllib.request.urlopen(svc.url + "api/services", timeout=5) as r:
                data = json.loads(r.read())
            assert "services" in data
            assert "ts" in data
        finally:
            svc.stop()

    def test_services_endpoint_with_kernel_api(self):
        class _FakeKernelAPI:
            def list_services(self):
                return {"network": "running", "storage": "running"}

        svc = _make_svc(kernel_api=_FakeKernelAPI())
        svc.start()
        try:
            with urllib.request.urlopen(svc.url + "api/services", timeout=5) as r:
                data = json.loads(r.read())
            assert data["services"] == {"network": "running", "storage": "running"}
        finally:
            svc.stop()

    def test_services_endpoint_without_kernel_api(self):
        svc = _make_svc(kernel_api=None)
        svc.start()
        try:
            with urllib.request.urlopen(svc.url + "api/services", timeout=5) as r:
                data = json.loads(r.read())
            # Empty dict when no kernel_api
            assert isinstance(data["services"], dict)
        finally:
            svc.stop()


# ---------------------------------------------------------------------------
# /api/sysinfo
# ---------------------------------------------------------------------------

class TestSysinfoEndpoint:

    def test_sysinfo_endpoint_returns_json(self):
        svc = _make_svc()
        svc.start()
        try:
            with urllib.request.urlopen(svc.url + "api/sysinfo", timeout=5) as r:
                data = json.loads(r.read())
            assert "sysinfo" in data
            assert "ts" in data
        finally:
            svc.stop()

    def test_sysinfo_endpoint_calls_kernel_api(self):
        class _FakeKernelAPI:
            def sysinfo(self):
                return {"arch": "x86_64", "memory_mb": 4096}

        svc = _make_svc(kernel_api=_FakeKernelAPI())
        svc.start()
        try:
            with urllib.request.urlopen(svc.url + "api/sysinfo", timeout=5) as r:
                data = json.loads(r.read())
            assert data["sysinfo"]["arch"] == "x86_64"
        finally:
            svc.stop()


# ---------------------------------------------------------------------------
# POST /api/aura/query
# ---------------------------------------------------------------------------

class TestAuraQueryEndpoint:

    def _post_json(self, url, payload):
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_aura_query_returns_response(self):
        svc = _make_svc(dispatch_fn=lambda cmd: f"ECHO:{cmd}")
        svc.start()
        try:
            data = self._post_json(svc.url + "api/aura/query",
                                   {"prompt": "hello"})
            assert "response" in data
            assert "ts" in data
        finally:
            svc.stop()

    def test_aura_query_uses_kernel_api(self):
        class _FakeKernelAPI:
            def aura_query(self, prompt):
                return f"AURA says: {prompt}"

        svc = _make_svc(kernel_api=_FakeKernelAPI())
        svc.start()
        try:
            data = self._post_json(svc.url + "api/aura/query",
                                   {"prompt": "test"})
            assert data["response"] == "AURA says: test"
        finally:
            svc.stop()

    def test_aura_query_empty_prompt_returns_400(self):
        svc = _make_svc()
        svc.start()
        try:
            try:
                self._post_json(svc.url + "api/aura/query", {"prompt": ""})
                pytest.fail("Expected HTTPError 400 was not raised")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
        finally:
            svc.stop()

    def test_aura_query_missing_prompt_returns_400(self):
        svc = _make_svc()
        svc.start()
        try:
            try:
                self._post_json(svc.url + "api/aura/query", {})
                pytest.fail("Expected HTTPError 400 was not raised")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
        finally:
            svc.stop()

    def test_aura_query_bad_json_returns_400(self):
        svc = _make_svc()
        svc.start()
        try:
            req = urllib.request.Request(
                svc.url + "api/aura/query",
                data=b"not-json",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=5)
                pytest.fail("Expected HTTPError 400 was not raised")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
        finally:
            svc.stop()


# ---------------------------------------------------------------------------
# kernel_api parameter in constructor
# ---------------------------------------------------------------------------

class TestWebTerminalKernelApi:

    def test_constructor_accepts_kernel_api(self):
        svc = WebTerminalService(kernel_api=object())
        assert svc is not None
