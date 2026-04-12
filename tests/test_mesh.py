"""Tests for vnet.mesh (VirtualMesh)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from vnet.node_identity import NodeIdentity
from vnet.peer_registry import PeerRegistry
from vnet.mesh import VirtualMesh


# ---------------------------------------------------------------------------
# Stub peer HTTP server
# ---------------------------------------------------------------------------

class _PeerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if "/api/node/status" in self.path:
            resp = {
                "node_id":      "peer-123",
                "alias":        "test-peer",
                "status":       "running",
                "capabilities": ["cap.a"],
                "version":      "0.1.0",
            }
            body = json.dumps(resp).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        resp = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp)


def _start_peer_server():
    server = HTTPServer(("127.0.0.1", 0), _PeerHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, server.server_address[1]


@pytest.fixture
def identity(tmp_path):
    return NodeIdentity(config_dir=str(tmp_path))


@pytest.fixture
def peers(tmp_path):
    return PeerRegistry(config_dir=str(tmp_path))


@pytest.fixture
def mesh(identity, peers):
    m = VirtualMesh(identity, peers, sync_interval_s=9999)
    yield m
    m.stop()


class TestVirtualMesh:
    def test_initial_status(self, mesh):
        s = mesh.status()
        assert "running" in s
        assert "peer_count" in s
        assert "coordinator" in s

    def test_start_stop(self, mesh):
        mesh.start()
        assert mesh._running is True
        mesh.stop()
        assert mesh._running is False

    def test_start_idempotent(self, mesh):
        mesh.start()
        mesh.start()  # second call must not crash
        mesh.stop()

    def test_coordinator_self_when_no_peers(self, mesh, identity):
        mesh._compute_coordinator()
        assert mesh.coordinator == identity.node_id
        assert mesh.am_coordinator() is True

    def test_coordinator_lowest_id(self, mesh, peers, identity):
        # Add a peer with lower node_id lexicographically
        low_id = "00000000-0000-0000-0000-000000000000"
        peers.add_or_update(low_id, alias="low", host="127.0.0.1", port=9)
        mesh._compute_coordinator()
        assert mesh.coordinator == low_id
        assert mesh.am_coordinator() is False

    def test_sync_no_peers(self, mesh):
        result = mesh.sync_state()
        assert result["reachable"] == 0
        assert result["unreachable"] == 0

    def test_sync_with_reachable_peer(self, mesh, peers):
        srv, port = _start_peer_server()
        try:
            peers.add_or_update("peer-123", host="127.0.0.1", port=port)
            result = mesh.sync_state()
            assert result["reachable"] == 1
            updated_peer = peers.get("peer-123")
            assert updated_peer.status == "running"
        finally:
            srv.shutdown()

    def test_sync_with_unreachable_peer(self, mesh, peers):
        peers.add_or_update("dead-peer", host="127.0.0.1", port=1)
        result = mesh.sync_state()
        assert result["unreachable"] == 1

    def test_announce_to_peer(self, mesh, peers, identity):
        srv, port = _start_peer_server()
        try:
            pr = peers.add_or_update("ann-peer", host="127.0.0.1", port=port)
            ok = mesh.announce_to_peer(pr)
            assert ok is True
        finally:
            srv.shutdown()

    def test_announce_to_peer_no_host(self, mesh, peers):
        pr = peers.add_or_update("no-host", host="", port=0)
        assert mesh.announce_to_peer(pr) is False

    def test_status_after_sync(self, mesh):
        mesh.sync_state()
        s = mesh.status()
        assert s["sync_count"] == 1
        assert s["last_sync_ts"] is not None
