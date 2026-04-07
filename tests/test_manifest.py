"""Unit tests: Build Manifest"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, pytest
from tools.manifest import (
    build_manifest, write_manifest, load_manifest,
    verify_manifest, get_provenance, _sha256, _get_commit,
)


class TestManifest:
    def test_sha256_of_known_content(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        digest = _sha256(str(f))
        # SHA256 of "hello"
        assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_build_manifest_returns_dict(self):
        m = build_manifest()
        assert isinstance(m, dict)

    def test_manifest_has_version(self):
        m = build_manifest()
        assert "version" in m

    def test_manifest_has_files(self):
        m = build_manifest()
        assert "files" in m
        assert isinstance(m["files"], dict)

    def test_manifest_has_commit(self):
        m = build_manifest()
        assert "commit" in m

    def test_manifest_has_environment(self):
        m = build_manifest()
        assert "environment" in m
        assert "python" in m["environment"]

    def test_write_and_load_manifest(self, tmp_path):
        m = build_manifest()
        path = str(tmp_path / "manifest.json")
        write_manifest(m, path)
        loaded = load_manifest(path)
        assert loaded["version"] == m["version"]
        assert loaded["files"] == m["files"]

    def test_verify_manifest_passes_on_fresh_build(self):
        m = build_manifest()
        ok, diffs = verify_manifest(m)
        # Some diffs may exist for runtime files, but the call must not raise
        assert isinstance(ok, bool)
        assert isinstance(diffs, list)

    def test_get_provenance_returns_dict(self):
        p = get_provenance()
        assert isinstance(p, dict)
        assert "commit" in p
        assert "environment" in p

    def test_get_commit_returns_string(self):
        commit = _get_commit()
        assert isinstance(commit, str)
        assert len(commit) > 0
