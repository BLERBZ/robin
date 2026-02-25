"""Tests for the unified LLM Gateway."""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


class TestLLMGateway:
    def _make_gw(self):
        from lib.sidekick.llm_gateway import LLMGateway
        return LLMGateway()

    def test_chat_returns_first_successful_provider(self):
        gw = self._make_gw()
        with patch.object(gw, "_resolve_provider_chain", return_value=["local", "claude"]), \
             patch.object(gw, "_try_chat", side_effect=[None, "Hello from Claude"]), \
             patch.object(gw, "_record_success"), \
             patch.object(gw, "_record_failure"):
            result = gw.chat([{"role": "user", "content": "hi"}])
            assert result == "Hello from Claude"

    def test_chat_returns_none_when_all_fail(self):
        gw = self._make_gw()
        with patch.object(gw, "_resolve_provider_chain", return_value=["local"]), \
             patch.object(gw, "_try_chat", return_value=None), \
             patch.object(gw, "_record_failure"):
            result = gw.chat([{"role": "user", "content": "hi"}])
            assert result is None

    def test_available_providers(self):
        gw = self._make_gw()
        with patch.object(gw, "_local_available", return_value=True), \
             patch.object(gw, "_claude_available", return_value=False), \
             patch.object(gw, "_openai_available", return_value=True), \
             patch.object(gw, "_litellm_available", return_value=False):
            providers = gw.available_providers()
            assert "local" in providers
            assert "openai" in providers
            assert "claude" not in providers

    def test_health_returns_all_providers(self):
        gw = self._make_gw()
        with patch.object(gw, "_local_available", return_value=True), \
             patch.object(gw, "_claude_available", return_value=True), \
             patch.object(gw, "_openai_available", return_value=False), \
             patch.object(gw, "_litellm_available", return_value=False):
            health = gw.health()
            assert "local" in health
            assert "claude" in health
            assert "openai" in health
            assert "litellm" in health

    def test_override_provider(self):
        gw = self._make_gw()
        chain = gw._resolve_provider_chain(
            [{"role": "user", "content": "hi"}],
            override_provider="claude",
        )
        assert chain[0] == "claude"


class TestGatewaySingleton:
    def test_returns_same_instance(self):
        import lib.sidekick.llm_gateway as mod
        mod._singleton_instance = None
        g1 = mod.get_llm_gateway()
        g2 = mod.get_llm_gateway()
        assert g1 is g2
        mod._singleton_instance = None
