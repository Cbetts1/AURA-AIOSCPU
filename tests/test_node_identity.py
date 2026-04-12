"""Tests for vnet.node_identity."""
import json
import os
import pytest

from vnet.node_identity import NodeIdentity, _default_alias, _safe_hostname, CAPABILITIES


@pytest.fixture
def tmp_identity(tmp_path):
    return NodeIdentity(config_dir=str(tmp_path))


class TestNodeIdentity:
    def test_creates_node_id(self, tmp_identity):
        assert len(tmp_identity.node_id) == 36  # UUID format

    def test_persists_across_instances(self, tmp_path):
        a = NodeIdentity(config_dir=str(tmp_path))
        nid = a.node_id
        b = NodeIdentity(config_dir=str(tmp_path))
        assert b.node_id == nid

    def test_alias_default(self, tmp_identity):
        assert "aura" in tmp_identity.alias

    def test_custom_alias(self, tmp_path):
        ni = NodeIdentity(config_dir=str(tmp_path), alias="my-alias")
        assert ni.alias == "my-alias"

    def test_to_dict_keys(self, tmp_identity):
        d = tmp_identity.to_dict()
        for key in ("node_id", "alias", "version", "capabilities", "hostname"):
            assert key in d, f"missing key: {key}"

    def test_capabilities_populated(self, tmp_identity):
        assert len(tmp_identity.capabilities) > 5

    def test_add_capability(self, tmp_identity):
        tmp_identity.add_capability("test.cap", "desc")
        assert "test.cap" in tmp_identity.capabilities

    def test_remove_capability(self, tmp_identity):
        tmp_identity.add_capability("removeme", "x")
        tmp_identity.remove_capability("removeme")
        assert "removeme" not in tmp_identity.capabilities

    def test_remove_nonexistent_capability(self, tmp_identity):
        tmp_identity.remove_capability("does_not_exist")  # must not raise

    def test_capability_summary_returns_dict(self, tmp_identity):
        s = tmp_identity.capability_summary()
        assert isinstance(s, dict)
        assert len(s) > 0

    def test_repr(self, tmp_identity):
        r = repr(tmp_identity)
        assert "NodeIdentity" in r
        assert tmp_identity.node_id in r

    def test_identity_file_created(self, tmp_path):
        NodeIdentity(config_dir=str(tmp_path))
        assert (tmp_path / "node_identity.json").exists()

    def test_identity_file_valid_json(self, tmp_path):
        NodeIdentity(config_dir=str(tmp_path))
        data = json.loads((tmp_path / "node_identity.json").read_text())
        assert "node_id" in data

    def test_capabilities_constant_has_entries(self):
        assert len(CAPABILITIES) >= 10

    def test_safe_hostname_returns_string(self):
        assert isinstance(_safe_hostname(), str)

    def test_default_alias_contains_aura(self):
        assert "aura" in _default_alias()

    def test_version_stored(self, tmp_path):
        ni = NodeIdentity(config_dir=str(tmp_path), version="9.9.9")
        assert ni.version == "9.9.9"
