"""Tests for services.command_channel (CommandChannelService)."""
import json
import socket
import threading
import time
import urllib.request

import pytest

from kernel.event_bus import EventBus  # avoid circular import
from vnet.node_identity import NodeIdentity
from services.command_channel import CommandChannelService, _collect_metrics


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def identity(tmp_path):
    return NodeIdentity(config_dir=str(tmp_path))


@pytest.fixture
def svc(identity):
    port = _free_port()
    s = CommandChannelService(identity, host="127.0.0.1", port=port)
    s.start()
    time.sleep(0.05)
    yield s
    s.stop()


def _get(url: str, key: str = "") -> dict:
    req = urllib.request.Request(url, headers={"X-AURA-Key": key})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _post(url: str, data: dict, key: str = "") -> dict:
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "X-AURA-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


class TestCommandChannelService:
    def _base(self, svc):
        return f"http://{svc.bind_address}"

    def test_is_running(self, svc):
        assert svc.is_running

    def test_status_dict(self, svc):
        s = svc.status()
        assert "running" in s
        assert s["running"] is True

    def test_identity_endpoint(self, svc, identity):
        d = _get(f"{self._base(svc)}/api/node/identity")
        assert d["node_id"] == identity.node_id

    def test_status_endpoint(self, svc):
        d = _get(f"{self._base(svc)}/api/node/status")
        assert d["status"] == "running"
        assert "uptime_s" in d

    def test_capabilities_endpoint(self, svc, identity):
        d = _get(f"{self._base(svc)}/api/node/capabilities")
        assert "capabilities" in d
        assert len(d["capabilities"]) > 0

    def test_metrics_endpoint(self, svc):
        d = _get(f"{self._base(svc)}/api/node/metrics")
        assert "ts" in d

    def test_peers_endpoint_empty(self, svc):
        d = _get(f"{self._base(svc)}/api/peers")
        assert d["peers"] == []

    def test_services_endpoint_no_kernel(self, svc):
        d = _get(f"{self._base(svc)}/api/services")
        assert "services" in d

    def test_health_endpoint_no_monitor(self, svc):
        d = _get(f"{self._base(svc)}/api/health")
        assert "status" in d

    def test_mesh_status_not_configured(self, svc):
        d = _get(f"{self._base(svc)}/api/mesh/status")
        assert "mesh" in d

    def test_logs_endpoint(self, svc):
        svc.append_log("test line")
        d = _get(f"{self._base(svc)}/api/logs")
        assert "lines" in d
        assert "test line" in d["lines"]

    def test_version_endpoint(self, svc, identity):
        d = _get(f"{self._base(svc)}/api/version")
        assert "version" in d
        assert d["node_id"] == identity.node_id

    def test_announce_endpoint(self, svc):
        d = _post(
            f"{self._base(svc)}/api/node/announce",
            {"node_id": "peer-abc", "alias": "p", "host": "1.2.3.4", "port": 7332},
        )
        assert d["status"] == "ok"

    def test_announce_missing_node_id(self, svc):
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post(f"{self._base(svc)}/api/node/announce", {})
        assert exc_info.value.code == 400

    def test_cmd_endpoint_with_dispatch(self, svc):
        svc.set_dispatch_fn(lambda cmd: f"echo:{cmd}")
        d = _post(f"{self._base(svc)}/api/cmd", {"cmd": "hello"})
        assert "echo:hello" in d["output"]

    def test_cmd_endpoint_no_dispatch(self, svc):
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post(f"{self._base(svc)}/api/cmd", {"cmd": "test"})
        assert exc_info.value.code == 503

    def test_cmd_missing_cmd_field(self, svc):
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post(f"{self._base(svc)}/api/cmd", {})
        assert exc_info.value.code == 400

    def test_not_found_returns_404(self, svc):
        import urllib.error
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _get(f"{self._base(svc)}/api/does/not/exist")
        assert exc_info.value.code == 404

    def test_auth_required(self, identity, tmp_path):
        port = _free_port()
        s = CommandChannelService(
            identity, host="127.0.0.1", port=port, api_key="secret"
        )
        s.start()
        time.sleep(0.05)
        try:
            import urllib.error
            # no key → 403
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/api/version")
                urllib.request.urlopen(req, timeout=5)
            assert exc_info.value.code == 403

            # correct key → 200
            d = _get(f"http://127.0.0.1:{port}/api/version", key="secret")
            assert "version" in d
        finally:
            s.stop()

    def test_stop_idempotent(self, svc):
        svc.stop()
        svc.stop()  # second stop must not raise

    def test_bind_address(self, svc):
        assert ":" in svc.bind_address

    def test_append_log_ring_buffer(self, svc):
        for i in range(600):
            svc.append_log(f"line {i}")
        d = _get(f"{self._base(svc)}/api/logs")
        assert d["count"] <= 400 + 1  # ring trimmed

    def test_collect_metrics_returns_dict(self):
        m = _collect_metrics()
        assert isinstance(m, dict)
        assert "ts" in m
