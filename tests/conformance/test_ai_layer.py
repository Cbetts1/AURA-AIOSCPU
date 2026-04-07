"""Conformance: AI Layer (AURA) (Contract 6)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from kernel.event_bus import EventBus
from aura import AURA


class TestAILayer:
    def test_aura_importable(self):
        from aura import AURA  # noqa: F401
        assert AURA

    def test_aura_instantiable(self):
        bus = EventBus()
        aura = AURA(bus)
        assert aura is not None

    def test_aura_query_returns_string(self):
        bus = EventBus()
        aura = AURA(bus)
        result = aura.query("What services are running?")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_aura_has_attach_kernel(self):
        bus = EventBus()
        aura = AURA(bus)
        assert hasattr(aura, "attach_kernel")
        assert callable(aura.attach_kernel)

    def test_aura_has_pulse(self):
        bus = EventBus()
        aura = AURA(bus)
        assert hasattr(aura, "pulse")

    def test_memory_module_importable(self):
        from aura.memory import ConversationMemory  # noqa: F401
        assert ConversationMemory

    def test_memory_add_and_retrieve(self):
        from aura.memory import ConversationMemory
        mem = ConversationMemory(max_turns=10)
        mem.add("user", "Hello")
        mem.add("aura", "Hi there")
        turns = mem.get_turns()
        assert len(turns) == 2
        assert turns[0].role == "user"

    def test_personality_module_importable(self):
        from aura.personality import AURAPersonality  # noqa: F401
        assert AURAPersonality

    def test_personality_format_response(self):
        from aura.personality import AURAPersonality
        p = AURAPersonality()
        result = p.format_response("Services are running.", "", {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_introspection_module_importable(self):
        from aura.introspection import SystemIntrospector  # noqa: F401
        assert SystemIntrospector

    def test_context_builder_importable(self):
        from aura.context_builder import ContextBuilder  # noqa: F401
        assert ContextBuilder

    def test_privilege_module_importable(self):
        from kernel.privilege import AURAPrivilege, VIRTUAL_ROOT_CAPS  # noqa: F401
        assert AURAPrivilege
        assert len(VIRTUAL_ROOT_CAPS) > 0

    def test_privilege_virtual_root_always_true(self):
        from kernel.privilege import AURAPrivilege
        priv = AURAPrivilege()
        assert priv.is_virtual_root()

    def test_privilege_execute_virtual_root(self):
        from kernel.privilege import AURAPrivilege
        priv = AURAPrivilege()
        result = priv.execute_as_virtual_root(
            "service.start",
            lambda: "service started",
            "test execution"
        )
        assert result == "service started"

    def test_override_module_importable(self):
        from kernel.override import CommandOverrideLayer  # noqa: F401
        assert CommandOverrideLayer

    def test_mirror_module_importable(self):
        from kernel.mirror import MirrorModeEnforcer  # noqa: F401
        assert MirrorModeEnforcer

    def test_mirror_virtual_root_always_passes(self):
        from kernel.mirror import MirrorModeEnforcer
        enforcer = MirrorModeEnforcer()
        denial = enforcer.enforce("service.start", privilege_tier="virtual_root")
        assert denial is None
