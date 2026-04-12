"""Tests for vnet.command_center (CommandCenterClient)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from vnet.node_identity import NodeIdentity
from vnet.command_center import CommandCenterClient


# ---------------------------------------------------------------------------
# Minimal stub CC server
# ---------------------------------------------------------------------------

_COMMANDS_TO_RETURN = []


class _CCHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if "/register" in self.path:
            resp = {"status": "ok", "assigned_id": "cc-assigned", "peers": []}
        elif "/heartbeat" in self.path:
            resp = {"status": "ok", "commands": _COMMANDS_TO_RETURN[:]}
        elif "/deregister" in self.path:
            resp = {"status": "ok"}
        else:
            resp = {"status": "unknown"}
        self.wfile.write(json.dumps(resp).encode())


def _start_cc_server():
    server = HTTPServer(("127.0.0.1", 0), _CCHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, server.server_address[1]


@pytest.fixture
def identity(tmp_path):
    return NodeIdentity(config_dir=str(tmp_path))


@pytest.fixture
def cc_server():
    srv, port = _start_cc_server()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


class TestCommandCenterClient:
    def test_not_configured_by_default(self, identity):
        c = CommandCenterClient(identity)
        assert not c.is_configured

    def test_configured_with_url(self, identity, cc_server):
        c = CommandCenterClient(identity, cc_url=cc_server)
        assert c.is_configured

    def test_register_now_success(self, identity, cc_server):
        c = CommandCenterClient(identity, cc_url=cc_server)
        assert c.register_now() is True
        assert c.is_registered

    def test_register_unreachable_returns_false(self, identity):
        c = CommandCenterClient(identity, cc_url="http://127.0.0.1:1")
        result = c.register_now()
        assert result is False
        assert not c.is_registered

    def test_send_heartbeat_after_register(self, identity, cc_server):
        c = CommandCenterClient(identity, cc_url=cc_server)
        c.register_now()
        assert c.send_heartbeat() is True
        assert c._hb_count == 1

    def test_command_handler_invoked(self, identity, cc_server):
        received = []
        _COMMANDS_TO_RETURN.clear()
        _COMMANDS_TO_RETURN.append({"action": "status"})

        def handler(cmd):
            received.append(cmd)

        c = CommandCenterClient(identity, cc_url=cc_server, command_handler=handler)
        c.register_now()
        c.send_heartbeat()
        assert len(received) == 1
        assert received[0]["action"] == "status"

        _COMMANDS_TO_RETURN.clear()

    def test_status_dict(self, identity, cc_server):
        c = CommandCenterClient(identity, cc_url=cc_server)
        s = c.status()
        for key in ("configured", "registered", "running", "cc_url"):
            assert key in s

    def test_metrics_fn_called(self, identity, cc_server):
        called = []

        def metrics():
            called.append(1)
            return {"cpu": 0.5}

        c = CommandCenterClient(identity, cc_url=cc_server, metrics_fn=metrics)
        c.register_now()
        c.send_heartbeat()
        assert len(called) == 1

    def test_start_no_url_is_noop(self, identity):
        c = CommandCenterClient(identity)
        c.start()
        assert not c._running  # should remain False

    def test_stop_when_not_running(self, identity):
        c = CommandCenterClient(identity)
        c.stop()  # must not raise

    def test_error_count_increments_on_failure(self, identity):
        c = CommandCenterClient(identity, cc_url="http://127.0.0.1:1")
        c.register_now()
        assert c._error_count >= 1
