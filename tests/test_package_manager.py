"""
Tests — Package Manager
========================
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from services.package_manager import PackageManager, PackageRecord


def _tmp_pm():
    """Return a PackageManager with a temp registry file."""
    tmpdir = tempfile.mkdtemp()
    reg    = os.path.join(tmpdir, "packages.json")
    return PackageManager(registry_path=reg), tmpdir


class TestPackageRecord:

    def test_to_dict_has_required_keys(self):
        rec = PackageRecord("requests", "2.31.0", "HTTP library")
        d = rec.to_dict()
        for key in ("name", "version", "description", "installed_at"):
            assert key in d

    def test_from_dict_roundtrip(self):
        rec = PackageRecord("requests", "2.31.0", "HTTP library")
        d   = rec.to_dict()
        rec2 = PackageRecord.from_dict(d)
        assert rec2.name    == rec.name
        assert rec2.version == rec.version

    def test_repr_contains_name(self):
        rec = PackageRecord("flask")
        assert "flask" in repr(rec)


class TestPackageManager:

    def test_instantiation(self):
        pm, _ = _tmp_pm()
        assert pm is not None

    def test_list_empty_initially(self):
        pm, _ = _tmp_pm()
        assert pm.list_packages() == []

    def test_info_returns_none_for_unknown(self):
        pm, _ = _tmp_pm()
        assert pm.info("nonexistent") is None

    def test_search_empty_for_unknown(self):
        pm, _ = _tmp_pm()
        assert pm.search("xyz") == []

    def test_is_installed_false_initially(self):
        pm, _ = _tmp_pm()
        assert not pm.is_installed("requests")

    def test_registry_persisted_to_json(self):
        pm, tmpdir = _tmp_pm()
        # Manually add a record to test persistence
        from services.package_manager import PackageRecord
        pm._registry["test-pkg"] = PackageRecord("test-pkg", "1.0.0")
        pm._save_registry()
        reg_path = pm._registry_path
        with open(reg_path) as fh:
            data = json.load(fh)
        names = [p["name"] for p in data["packages"]]
        assert "test-pkg" in names

    def test_registry_loaded_from_json(self):
        pm, tmpdir = _tmp_pm()
        pm._registry["test-pkg"] = PackageRecord("test-pkg", "1.0.0")
        pm._save_registry()
        # Create new instance from same registry
        pm2 = PackageManager(registry_path=pm._registry_path)
        assert pm2.is_installed("test-pkg")

    def test_search_finds_by_name(self):
        pm, _ = _tmp_pm()
        pm._registry["requests"] = PackageRecord("requests", "2.31.0", "HTTP library")
        result = pm.search("req")
        assert len(result) == 1
        assert result[0]["name"] == "requests"

    def test_search_finds_by_description(self):
        pm, _ = _tmp_pm()
        pm._registry["requests"] = PackageRecord("requests", "2.31.0", "HTTP library")
        result = pm.search("http")
        assert len(result) == 1

    def test_info_returns_dict_when_found(self):
        pm, _ = _tmp_pm()
        pm._registry["requests"] = PackageRecord("requests", "2.31.0")
        info = pm.info("requests")
        assert info is not None
        assert info["name"] == "requests"

    def test_install_success(self):
        pm, _ = _tmp_pm()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            with patch.object(pm, "_pip_show_version", return_value="2.31.0"):
                with patch.object(pm, "_pip_show_description", return_value="HTTP"):
                    result = pm.install("requests")
        assert result["success"] is True
        assert pm.is_installed("requests")

    def test_install_failure(self):
        pm, _ = _tmp_pm()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No matching distribution"
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = pm.install("nonexistent-pkg-xyz-12345")
        assert result["success"] is False

    def test_uninstall_removes_from_registry(self):
        pm, _ = _tmp_pm()
        pm._registry["requests"] = PackageRecord("requests", "2.31.0")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = pm.uninstall("requests")
        assert result["success"] is True
        assert not pm.is_installed("requests")

    def test_repr_shows_count(self):
        pm, _ = _tmp_pm()
        r = repr(pm)
        assert "PackageManager" in r
