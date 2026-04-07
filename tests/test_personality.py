"""Unit tests: AURA Personality"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from aura.personality import AURAPersonality


class TestAURAPersonality:
    def test_instantiable(self):
        p = AURAPersonality()
        assert p is not None

    def test_format_response_returns_string(self):
        p = AURAPersonality()
        result = p.format_response("test message", "", {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_system_prompt_not_empty(self):
        p = AURAPersonality()
        prompt = p.build_system_prompt({})
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_format_preserves_content(self):
        p = AURAPersonality()
        msg = "All 5 services are running."
        result = p.format_response(msg, "", {})
        # Core content should be present somewhere
        assert "services" in result.lower() or "5" in result or "running" in result.lower()

    def test_error_response_returns_string(self):
        p = AURAPersonality()
        # Use format_response with an error message
        result = p.format_response("Something went wrong", "error", {"mode": "universal"})
        assert isinstance(result, str)
        assert len(result) > 0
