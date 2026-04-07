"""Unit tests: Kernel Permission Model"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from kernel.permissions import PermissionModel, PermissionDenied


class TestPermissionModel:
    def test_universal_mode_basic_capabilities(self):
        pm = PermissionModel(mode="universal")
        assert pm.is_allowed("fs.write")
        assert pm.is_allowed("net.connect")
        assert pm.is_allowed("fs.read")

    def test_universal_mode_blocked_caps(self):
        pm = PermissionModel(mode="universal")
        with pytest.raises(PermissionDenied):
            pm.check("fs.mount_bind")

    def test_internal_mode_elevated_caps(self):
        pm = PermissionModel(mode="internal")
        assert pm.is_allowed("fs.chmod")

    def test_grant_capability(self):
        pm = PermissionModel(mode="universal")
        pm.grant("net.listen")
        assert pm.is_allowed("net.listen")

    def test_revoke_capability(self):
        pm = PermissionModel(mode="universal")
        pm.grant("net.listen")
        pm.revoke("net.listen")
        assert not pm.is_allowed("net.listen")

    def test_set_mode_changes_allowed_set(self):
        pm = PermissionModel(mode="universal")
        pm.set_mode("hardware")
        assert pm.mode == "hardware"

    def test_permission_denied_is_exception(self):
        assert issubclass(PermissionDenied, Exception)
