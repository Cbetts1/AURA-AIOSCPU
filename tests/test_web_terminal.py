"""
Tests — Web Terminal Service
=============================
"""

import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from services.web_terminal import WebTerminalService


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_svc(dispatch_fn=None, port=None):
    port = port or _find_free_port()
    svc  = WebTerminalService(
        dispatch_fn=dispatch_fn or (lambda cmd: f"echo:{cmd}"),
        port=port,
    )
    return svc


class TestWebTerminalService:

    def test_instantiation(self):
        svc = WebTerminalService()
        assert svc is not None

    def test_not_running_before_start(self):
        svc = _make_svc()
        assert not svc.is_running

    def test_start_and_stop(self):
        svc = _make_svc()
        assert svc.start()
        assert svc.is_running
        svc.stop()
        assert not svc.is_running

    def test_double_start_is_safe(self):
        svc = _make_svc()
        svc.start()
        assert svc.start()   # second call should return True and not raise
        svc.stop()

    def test_url_contains_port(self):
        port = _find_free_port()
        svc  = WebTerminalService(port=port)
        assert str(port) in svc.url

    def test_port_property(self):
        port = _find_free_port()
        svc  = WebTerminalService(port=port)
        assert svc.port == port

    def test_repr_stopped(self):
        svc = WebTerminalService()
        assert "stopped" in repr(svc)

    def test_repr_running(self):
        svc = _make_svc()
        svc.start()
        r = repr(svc)
        assert "running" in r
        svc.stop()

    def test_http_home_page(self):
        svc = _make_svc()
        svc.start()
        try:
            with urllib.request.urlopen(svc.url, timeout=5) as resp:
                html = resp.read()
            assert b"AURA" in html
            assert b"html" in html.lower()
        finally:
            svc.stop()

    def test_http_status_endpoint(self):
        svc = _make_svc()
        svc.start()
        try:
            with urllib.request.urlopen(svc.url + "api/status", timeout=5) as resp:
                data = json.loads(resp.read())
            assert data["running"] is True
            assert "version" in data
            assert "uptime_s" in data
        finally:
            svc.stop()

    def test_post_cmd_returns_output(self):
        svc = _make_svc(dispatch_fn=lambda cmd: f"GOT:{cmd}")
        svc.start()
        try:
            payload = json.dumps({"cmd": "help"}).encode()
            req = urllib.request.Request(
                svc.url + "api/cmd",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            assert data["output"] == "GOT:help"
            assert "ts" in data
        finally:
            svc.stop()

    def test_post_cmd_empty_body_returns_400(self):
        svc = _make_svc()
        svc.start()
        try:
            req = urllib.request.Request(
                svc.url + "api/cmd",
                data=b"not-json",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
        finally:
            svc.stop()

    def test_404_for_unknown_path(self):
        svc = _make_svc()
        svc.start()
        try:
            try:
                urllib.request.urlopen(svc.url + "no/such/path", timeout=5)
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
        finally:
            svc.stop()

    def test_events_endpoint_returns_list(self):
        svc = _make_svc()
        svc.start()
        try:
            with urllib.request.urlopen(svc.url + "api/events", timeout=5) as resp:
                data = json.loads(resp.read())
            assert isinstance(data, list)
        finally:
            svc.stop()

    def test_stop_before_start_is_safe(self):
        svc = WebTerminalService()
        svc.stop()   # should not raise
