"""Tests for vnet.peer_registry."""
import json
import time
import pytest

from vnet.peer_registry import PeerRegistry, PeerRecord


@pytest.fixture
def reg(tmp_path):
    return PeerRegistry(config_dir=str(tmp_path))


class TestPeerRegistry:
    def test_initially_empty(self, reg):
        assert reg.count() == 0
        assert reg.all() == []

    def test_add_peer(self, reg):
        p = reg.add_or_update("node-abc", alias="peer-one", host="10.0.0.1", port=7332)
        assert p.node_id == "node-abc"
        assert reg.count() == 1

    def test_update_existing_peer(self, reg):
        reg.add_or_update("node-xyz", alias="old", host="1.2.3.4")
        reg.add_or_update("node-xyz", alias="new", status="running")
        p = reg.get("node-xyz")
        assert p.alias == "new"
        assert p.status == "running"
        assert reg.count() == 1

    def test_remove_peer(self, reg):
        reg.add_or_update("n1")
        assert reg.remove("n1") is True
        assert reg.count() == 0

    def test_remove_nonexistent(self, reg):
        assert reg.remove("ghost") is False

    def test_touch_existing(self, reg):
        reg.add_or_update("n2", host="h", port=1)
        assert reg.touch("n2") is True

    def test_touch_nonexistent(self, reg):
        assert reg.touch("ghost") is False

    def test_merge_from_cc(self, reg):
        peers = [
            {"node_id": "cc-1", "alias": "cc1", "host": "h1", "port": 7332},
            {"node_id": "cc-2", "alias": "cc2"},
            {"not_a_valid": "entry"},
        ]
        count = reg.merge_from_cc(peers)
        assert count == 2
        assert reg.count() == 2

    def test_active_vs_stale(self, reg):
        reg.add_or_update("fresh", host="h", port=1)
        stale_peer = reg.add_or_update("stale", host="h2", port=2)
        stale_peer.last_seen = time.time() - 10000  # force stale
        assert "fresh" in [p.node_id for p in reg.active()]
        assert "stale" in [p.node_id for p in reg.stale()]

    def test_to_list(self, reg):
        reg.add_or_update("n1", alias="a")
        result = reg.to_list()
        assert isinstance(result, list)
        assert result[0]["node_id"] == "n1"

    def test_len(self, reg):
        reg.add_or_update("n1")
        reg.add_or_update("n2")
        assert len(reg) == 2

    def test_persistence(self, tmp_path):
        r1 = PeerRegistry(config_dir=str(tmp_path))
        r1.add_or_update("persist-me", alias="p", host="10.0.0.2", port=999)
        r2 = PeerRegistry(config_dir=str(tmp_path))
        assert r2.count() == 1
        assert r2.get("persist-me").alias == "p"

    def test_peers_json_valid(self, tmp_path):
        r = PeerRegistry(config_dir=str(tmp_path))
        r.add_or_update("j1", alias="a")
        data = json.loads((tmp_path / "peers.json").read_text())
        assert isinstance(data, list)
        assert data[0]["node_id"] == "j1"

    def test_peer_record_is_stale(self):
        pr = PeerRecord(node_id="x")
        pr.last_seen = time.time() - 9999
        assert pr.is_stale()

    def test_peer_record_not_stale(self):
        pr = PeerRecord(node_id="y")
        assert not pr.is_stale()

    def test_peer_record_touch(self):
        pr = PeerRecord(node_id="z")
        before = pr.last_seen
        time.sleep(0.01)
        pr.touch()
        assert pr.last_seen >= before

    def test_peer_record_to_dict(self):
        pr = PeerRecord(node_id="d")
        d = pr.to_dict()
        assert d["node_id"] == "d"

    def test_add_with_capabilities(self, reg):
        reg.add_or_update("caps-node", capabilities=["cap.a", "cap.b"])
        p = reg.get("caps-node")
        assert "cap.a" in p.capabilities
