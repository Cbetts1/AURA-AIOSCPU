"""
Tests — Copilot Bridge
=======================
Unit tests for tools/copilot_bridge.py.

Covers:
  - Finding dataclass
  - Each individual audit function (mocked where needed)
  - Report rendering (Markdown + JSON)
  - run_bridge() return codes
  - CLI smoke test via subprocess
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types

import pytest

# Ensure repo root is on path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.copilot_bridge import (
    Finding,
    LEVEL_PASS,
    LEVEL_WARN,
    LEVEL_FAIL,
    LEVEL_UPGRADE,
    _run_python_check,
    _run_dependency_audit,
    _run_config_review,
    _run_upgrade_hints,
    _render_markdown,
    _render_json,
    run_bridge,
)


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class TestFinding:
    def test_to_dict_keys(self):
        f = Finding("cat", "name", LEVEL_PASS, "detail", "hint")
        d = f.to_dict()
        assert set(d.keys()) == {"category", "name", "level", "detail", "suggestion"}

    def test_to_dict_values(self):
        f = Finding("Sys", "check1", LEVEL_FAIL, "msg", "fix it")
        d = f.to_dict()
        assert d["category"]  == "Sys"
        assert d["name"]      == "check1"
        assert d["level"]     == LEVEL_FAIL
        assert d["detail"]    == "msg"
        assert d["suggestion"] == "fix it"

    def test_defaults(self):
        f = Finding("cat", "name", LEVEL_WARN)
        assert f.detail     == ""
        assert f.suggestion == ""


# ---------------------------------------------------------------------------
# _run_python_check
# ---------------------------------------------------------------------------

class TestPythonCheck:
    def test_returns_list_of_findings(self):
        results = _run_python_check()
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_current_python_passes_or_upgrades(self):
        results = _run_python_check()
        # Current env must be 3.10+ (CI enforces this)
        assert results[0].level in (LEVEL_PASS, LEVEL_UPGRADE)

    def test_finding_has_version_string(self):
        results = _run_python_check()
        assert any(
            f"{sys.version_info.major}.{sys.version_info.minor}" in f.detail
            for f in results
        )


# ---------------------------------------------------------------------------
# _run_dependency_audit
# ---------------------------------------------------------------------------

class TestDependencyAudit:
    def test_returns_list(self):
        results = _run_dependency_audit()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_all_findings_have_required_fields(self):
        for f in _run_dependency_audit():
            assert f.category == "Dependencies"
            assert f.name
            assert f.level in (LEVEL_PASS, LEVEL_FAIL, LEVEL_UPGRADE)

    def test_pytest_required_present(self):
        # pytest must be installed in the test environment
        findings = _run_dependency_audit()
        pytest_findings = [f for f in findings if "pytest" in f.name]
        assert pytest_findings, "No finding for pytest"
        assert pytest_findings[0].level == LEVEL_PASS

    def test_optional_missing_gives_upgrade(self, monkeypatch):
        # Simulate llama_cpp not being installed
        original = importlib.util.find_spec

        def fake_find_spec(name, *args, **kwargs):
            if name == "llama_cpp":
                return None
            return original(name, *args, **kwargs)

        monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
        findings = _run_dependency_audit()
        llama = [f for f in findings if "llama" in f.name.lower()]
        assert llama
        assert llama[0].level == LEVEL_UPGRADE
        assert llama[0].suggestion  # must have an install hint


# ---------------------------------------------------------------------------
# _run_config_review
# ---------------------------------------------------------------------------

class TestConfigReview:
    def test_returns_list(self):
        results = _run_config_review()
        assert isinstance(results, list)

    def test_no_hard_fails_on_default_config(self):
        # Default config should not produce FAIL findings
        results = _run_config_review()
        fails = [f for f in results if f.level == LEVEL_FAIL]
        assert not fails, f"Unexpected config failures: {fails}"

    def test_adaptive_tick_passes(self):
        results = _run_config_review()
        adaptive = [f for f in results if "adaptive" in f.name.lower()]
        assert adaptive
        assert adaptive[0].level == LEVEL_PASS

    def test_watchdog_enabled_passes(self):
        results = _run_config_review()
        wd = [f for f in results if "watchdog" in f.name.lower()]
        assert wd
        assert wd[0].level == LEVEL_PASS

    def test_no_ai_backend_gives_upgrade(self):
        results = _run_config_review()
        backend = [f for f in results if "backend" in f.name.lower()]
        assert backend
        # Default config has no backend — should be UPGRADE
        assert backend[0].level == LEVEL_UPGRADE


# ---------------------------------------------------------------------------
# _run_upgrade_hints
# ---------------------------------------------------------------------------

class TestUpgradeHints:
    def test_returns_list(self):
        results = _run_upgrade_hints()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_dockerfile_passes(self):
        # Dockerfile is present in this repo
        results = _run_upgrade_hints()
        docker = [f for f in results if "docker" in f.name.lower()]
        assert docker
        assert docker[0].level == LEVEL_PASS

    def test_manual_finding_present(self):
        results = _run_upgrade_hints()
        manual = [f for f in results if "manual" in f.name.lower()]
        assert manual, "Expected a finding about MANUAL.md"

    def test_all_findings_have_category(self):
        for f in _run_upgrade_hints():
            assert f.category == "Upgrades"


# ---------------------------------------------------------------------------
# _render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def _sample_findings(self):
        return [
            Finding("Sys",  "check_a", LEVEL_PASS,    "all good"),
            Finding("Sys",  "check_b", LEVEL_WARN,    "marginal"),
            Finding("Sys",  "check_c", LEVEL_FAIL,    "broken",   "fix it"),
            Finding("Deps", "pkg_x",   LEVEL_UPGRADE, "missing",  "install pkg_x"),
        ]

    def test_returns_string(self):
        md = _render_markdown(
            self._sample_findings(), 1.23, run_date="2024-01-01 00:00 UTC"
        )
        assert isinstance(md, str)

    def test_contains_summary_table(self):
        md = _render_markdown(
            self._sample_findings(), 1.0, run_date="now"
        )
        assert "Summary" in md
        assert "Pass" in md or "PASS" in md or "✅" in md

    def test_contains_upgrade_section(self):
        md = _render_markdown(
            self._sample_findings(), 1.0, run_date="now"
        )
        assert "Upgrade Recommendations" in md
        assert "install pkg_x" in md

    def test_contains_failure_section(self):
        md = _render_markdown(
            self._sample_findings(), 1.0, run_date="now"
        )
        assert "Failures" in md
        assert "fix it" in md

    def test_no_failures_section_when_none(self):
        findings = [Finding("Sys", "ok", LEVEL_PASS, "good")]
        md = _render_markdown(findings, 0.5, run_date="now")
        assert "Failures" not in md

    def test_contains_how_it_works(self):
        md = _render_markdown(
            self._sample_findings(), 1.0, run_date="now"
        )
        assert "copilot_bridge.py" in md

    def test_contains_all_categories(self):
        md = _render_markdown(
            self._sample_findings(), 1.0, run_date="now"
        )
        assert "## Sys" in md
        assert "## Deps" in md


# ---------------------------------------------------------------------------
# _render_json
# ---------------------------------------------------------------------------

class TestRenderJson:
    def _sample_findings(self):
        return [
            Finding("Sys", "chk_a", LEVEL_PASS),
            Finding("Sys", "chk_b", LEVEL_FAIL),
            Finding("Dep", "pkg",   LEVEL_UPGRADE),
        ]

    def test_valid_json(self):
        raw = _render_json(self._sample_findings(), 2.5)
        data = json.loads(raw)
        assert "summary" in data
        assert "findings" in data

    def test_summary_counts(self):
        data = json.loads(_render_json(self._sample_findings(), 0.0))
        s = data["summary"]
        assert s["pass"]    == 1
        assert s["fail"]    == 1
        assert s["upgrade"] == 1
        assert s["warn"]    == 0

    def test_findings_list(self):
        data = json.loads(_render_json(self._sample_findings(), 0.0))
        assert len(data["findings"]) == 3
        for f in data["findings"]:
            assert "category" in f
            assert "name" in f
            assert "level" in f


# ---------------------------------------------------------------------------
# run_bridge() — integration (no subprocess, skips pytest)
# ---------------------------------------------------------------------------

class TestRunBridge:
    def test_writes_report_file(self, tmp_path):
        out = str(tmp_path / "report.md")
        rc = run_bridge(run_tests=False, output_path=out, as_json=False)
        assert os.path.isfile(out)
        content = open(out).read()
        assert "AURA-AIOSCPU" in content

    def test_writes_json_report(self, tmp_path):
        out = str(tmp_path / "report.json")
        rc = run_bridge(run_tests=False, output_path=out, as_json=True)
        assert os.path.isfile(out)
        data = json.loads(open(out).read())
        assert "summary" in data

    def test_return_code_0_or_2(self, tmp_path):
        out = str(tmp_path / "r.md")
        rc = run_bridge(run_tests=False, output_path=out)
        # 0 = all good, 2 = upgrades exist (no failures expected in CI)
        assert rc in (0, 2)

    def test_no_hard_fails_in_clean_env(self, tmp_path):
        out = str(tmp_path / "r.json")
        run_bridge(run_tests=False, output_path=out, as_json=True)
        data = json.loads(open(out).read())
        assert data["summary"]["fail"] == 0


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_no_tests_exits_0_or_2(self, tmp_path):
        import subprocess
        out = str(tmp_path / "report.md")
        proc = subprocess.run(
            [sys.executable, "tools/copilot_bridge.py",
             "--no-tests", "--output", out],
            capture_output=True,
            cwd=_REPO_ROOT,
            timeout=120,
        )
        assert proc.returncode in (0, 2), (
            f"Unexpected exit code {proc.returncode}:\n"
            f"{proc.stdout.decode()}\n{proc.stderr.decode()}"
        )

    def test_cli_json_flag(self, tmp_path):
        import subprocess
        out = str(tmp_path / "report.json")
        proc = subprocess.run(
            [sys.executable, "tools/copilot_bridge.py",
             "--no-tests", "--json", "--output", out],
            capture_output=True,
            cwd=_REPO_ROOT,
            timeout=120,
        )
        assert proc.returncode in (0, 2)
        data = json.loads(open(out).read())
        assert "summary" in data
