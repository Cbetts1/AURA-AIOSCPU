"""Unit tests: Portability Validator"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.portability import (
    validate, validate_and_print, PortabilityReport, CheckResult,
    _check_host_bridge, _check_python_version, _check_rootfs_layout,
    _check_disk_space, _check_permissions, _check_services, _check_shell,
)


class TestPortabilityValidator:
    def test_check_result_pass(self):
        c = CheckResult("test", CheckResult.PASS, "all good")
        assert c.passed()
        assert not c.failed()

    def test_check_result_fail(self):
        c = CheckResult("test", CheckResult.FAIL, "broken")
        assert c.failed()
        assert not c.passed()

    def test_check_result_warn(self):
        c = CheckResult("test", CheckResult.WARN, "optional missing")
        assert c.warned()

    def test_check_result_to_dict(self):
        c = CheckResult("test", CheckResult.PASS, "ok")
        d = c.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "pass"

    def test_check_host_bridge_passes(self):
        c = _check_host_bridge()
        assert c.name == "host_bridge"
        assert c.passed()

    def test_check_python_version_passes(self):
        c = _check_python_version()
        assert c.name == "python_version"
        assert c.passed()  # We're running on 3.10+

    def test_check_rootfs_layout_passes(self):
        c = _check_rootfs_layout()
        assert c.name == "rootfs_layout"
        assert c.passed()

    def test_check_services_passes(self):
        c = _check_services()
        assert c.name == "services"
        assert c.passed()

    def test_check_shell_passes(self):
        c = _check_shell()
        assert c.name == "shell"
        assert c.passed()

    def test_validate_returns_report(self):
        report = validate()
        assert isinstance(report, PortabilityReport)

    def test_validate_report_has_checks(self):
        report = validate()
        assert len(report.checks) > 0

    def test_validate_report_passes(self):
        report = validate()
        assert report.passed(), f"Portability checks failed:\n{report.to_human()}"

    def test_validate_report_has_safe_modes(self):
        report = validate()
        assert len(report.safe_modes) > 0
        assert "universal" in report.safe_modes

    def test_report_to_dict(self):
        report = validate()
        d = report.to_dict()
        assert "passed" in d
        assert "safe_modes" in d
        assert "checks" in d

    def test_report_to_json(self):
        import json
        report = validate()
        j = report.to_json()
        data = json.loads(j)
        assert "passed" in data

    def test_report_to_human(self):
        report = validate()
        human = report.to_human()
        assert "AURA-AIOSCPU" in human
        assert "Portability" in human
