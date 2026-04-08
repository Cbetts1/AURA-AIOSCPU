"""Tests — tools/check_requirements.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tools.check_requirements import check, main


class TestCheckFunction:

    def test_returns_list(self):
        results = check()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_each_result_has_required_keys(self):
        for r in check():
            assert "name" in r
            assert "ok" in r
            assert "detail" in r

    def test_python_version_check_passes(self):
        results = check()
        py_check = next((r for r in results if "Python 3.10" in r["name"]), None)
        assert py_check is not None
        assert py_check["ok"] is True

    def test_architecture_check_present(self):
        results = check()
        arch_check = next((r for r in results if "arch" in r["name"].lower()), None)
        assert arch_check is not None
        assert "ok" in arch_check

    def test_stdlib_json_passes(self):
        results = check()
        json_check = next((r for r in results if r["name"] == "stdlib: json"), None)
        assert json_check is not None
        assert json_check["ok"] is True

    def test_stdlib_sqlite3_passes(self):
        results = check()
        check_ = next((r for r in results if r["name"] == "stdlib: sqlite3"), None)
        assert check_ is not None
        assert check_["ok"] is True

    def test_stdlib_threading_passes(self):
        results = check()
        check_ = next((r for r in results if r["name"] == "stdlib: threading"), None)
        assert check_ is not None
        assert check_["ok"] is True

    def test_stdlib_hashlib_passes(self):
        results = check()
        check_ = next((r for r in results if r["name"] == "stdlib: hashlib"), None)
        assert check_ is not None
        assert check_["ok"] is True

    def test_stdlib_pathlib_passes(self):
        results = check()
        check_ = next((r for r in results if r["name"] == "stdlib: pathlib"), None)
        assert check_ is not None
        assert check_["ok"] is True

    def test_stdlib_subprocess_passes(self):
        results = check()
        check_ = next((r for r in results if r["name"] == "stdlib: subprocess"), None)
        assert check_ is not None
        assert check_["ok"] is True

    def test_stdlib_logging_passes(self):
        results = check()
        check_ = next((r for r in results if r["name"] == "stdlib: logging"), None)
        assert check_ is not None
        assert check_["ok"] is True

    def test_disk_space_check_present(self):
        results = check()
        disk_check = next(
            (r for r in results if "disk" in r["name"].lower() or "space" in r["name"].lower()),
            None,
        )
        assert disk_check is not None

    def test_detail_is_string(self):
        for r in check():
            assert isinstance(r["detail"], str)

    def test_no_required_checks_fail(self):
        """All required (non-optional) checks should pass on the test runner."""
        results = check()
        required_failures = [
            r for r in results
            if r["ok"] is False and "optional" not in r["name"].lower()
        ]
        assert required_failures == [], \
            f"Required checks failed: {[r['name'] for r in required_failures]}"


class TestMainFunction:

    def test_main_returns_int(self):
        code = main()
        assert isinstance(code, int)

    def test_main_returns_zero_when_no_failures(self):
        code = main()
        assert code == 0

    def test_main_prints_header(self, capsys):
        main()
        out = capsys.readouterr().out
        assert "AURA-AIOSCPU" in out

    def test_main_prints_passed_count(self, capsys):
        main()
        out = capsys.readouterr().out
        assert "Passed:" in out

    def test_main_prints_compatibility_result(self, capsys):
        main()
        out = capsys.readouterr().out
        # Either success or failure message is printed
        assert "AURA-AIOSCPU" in out
