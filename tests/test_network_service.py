"""
Tests — Network Service
========================
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch
from services.network_service import (
    NetworkService, check_connectivity,
    _probe_tcp, _probe_dns, _local_ip,
)


class TestCheckConnectivity:

    def test_returns_dict(self):
        result = check_connectivity()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = check_connectivity()
        for key in ("status", "latency_ms", "dns_ok", "interface", "checked_at"):
            assert key in result, f"Missing key: {key}"

    def test_status_is_valid_string(self):
        result = check_connectivity()
        assert result["status"] in ("online", "offline", "degraded")

    def test_checked_at_is_float(self):
        import time
        before = time.time()
        result = check_connectivity()
        assert result["checked_at"] >= before

    def test_offline_mode_with_unreachable_probes(self):
        """Force all probes to fail → status should be 'offline'."""
        result = check_connectivity(
            probes=[("192.0.2.1", 9999)],   # TEST-NET — always unreachable
            dns_host="this.domain.does.not.exist.local",
            timeout=0.1,
        )
        assert result["status"] == "offline"
        assert result["latency_ms"] is None
        assert result["dns_ok"] is False

    def test_latency_is_none_when_offline(self):
        result = check_connectivity(
            probes=[("192.0.2.1", 9999)],
            timeout=0.1,
        )
        assert result["latency_ms"] is None


class TestProbeHelpers:

    def test_probe_tcp_unreachable_returns_none(self):
        rtt = _probe_tcp("192.0.2.1", 9999, timeout=0.2)
        assert rtt is None

    def test_probe_dns_bad_domain_returns_false(self):
        ok = _probe_dns("this.domain.does.not.exist.local.invalid", timeout=0.5)
        assert ok is False

    def test_local_ip_returns_string_or_none(self):
        ip = _local_ip()
        assert ip is None or isinstance(ip, str)


class TestNetworkService:

    def test_instantiation(self):
        svc = NetworkService()
        assert svc is not None

    def test_last_status_empty_before_first_check(self):
        svc = NetworkService()
        assert svc.last_status == {}

    def test_probe_now_returns_dict(self):
        svc = NetworkService()
        result = svc.probe_now()
        assert isinstance(result, dict)
        assert "status" in result

    def test_is_online_reflects_probe(self):
        svc = NetworkService()
        # Force offline
        with patch("services.network_service.check_connectivity",
                   return_value={"status": "offline", "latency_ms": None,
                                 "dns_ok": False, "interface": None,
                                 "checked_at": 0.0}):
            svc.probe_now()
        assert svc.is_online is False

    def test_start_stop_does_not_raise(self):
        svc = NetworkService(check_interval_s=9999)
        svc.start()
        import time; time.sleep(0.05)
        svc.stop()

    def test_repr_contains_status(self):
        svc = NetworkService()
        r = repr(svc)
        assert "NetworkService" in r
