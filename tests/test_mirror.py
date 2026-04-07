"""Unit tests: Mirror Mode Enforcer"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from kernel.mirror import MirrorModeEnforcer, LegalAlternativeFinder, HostDenial


class TestMirrorModeEnforcer:
    def test_instantiable(self):
        enforcer = MirrorModeEnforcer()
        assert enforcer is not None

    def test_virtual_root_always_passes(self):
        enforcer = MirrorModeEnforcer()
        denial = enforcer.enforce("any.action", privilege_tier="virtual_root")
        assert denial is None

    def test_no_bridge_returns_denial(self):
        enforcer = MirrorModeEnforcer(bridge=None)
        denial = enforcer.enforce("net.listen", privilege_tier="host_root")
        assert isinstance(denial, HostDenial)

    def test_denial_message_contains_action(self):
        enforcer = MirrorModeEnforcer(bridge=None)
        denial = enforcer.enforce("net.listen", privilege_tier="host_root")
        msg = denial.message()
        assert "net.listen" in msg

    def test_denial_aura_response_is_string(self):
        enforcer = MirrorModeEnforcer(bridge=None)
        denial = enforcer.enforce("net.listen", privilege_tier="host_root")
        resp = denial.aura_response()
        assert isinstance(resp, str)
        assert "Host OS denied" in resp

    def test_format_denial_returns_string(self):
        enforcer = MirrorModeEnforcer(bridge=None)
        denial = enforcer.enforce("net.listen", privilege_tier="host_root")
        result = MirrorModeEnforcer.format_denial(denial)
        assert isinstance(result, str)


class TestLegalAlternativeFinder:
    def test_net_listen_has_alternatives(self):
        finder = LegalAlternativeFinder()
        alts = finder.find("net.listen")
        assert len(alts) > 0

    def test_unknown_action_returns_empty(self):
        finder = LegalAlternativeFinder()
        alts = finder.find("completely.unknown.action.xyz")
        assert alts == []

    def test_alternative_has_description(self):
        finder = LegalAlternativeFinder()
        alts = finder.find("net.listen")
        for alt in alts:
            assert alt.description

    def test_suggest_alternatives_text_returns_string(self):
        enforcer = MirrorModeEnforcer()
        text = enforcer.suggest_alternatives_text("net.listen")
        assert isinstance(text, str)
        assert len(text) > 0
