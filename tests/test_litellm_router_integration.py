"""Tests for LiteLLM router integration."""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


class TestRouterWithLiteLLM:
    """Test that router interacts correctly with LiteLLM availability."""

    def test_litellm_in_gateway_fallback_chain(self):
        """When LiteLLM is available, it appears in the gateway fallback chain."""
        from lib.sidekick.llm_gateway import LLMGateway
        gw = LLMGateway()
        with patch.object(gw, "_local_available", return_value=True), \
             patch.object(gw, "_claude_available", return_value=False), \
             patch.object(gw, "_openai_available", return_value=False), \
             patch.object(gw, "_litellm_available", return_value=True):
            chain = gw._resolve_provider_chain([{"role": "user", "content": "hello"}])
            assert "litellm" in chain

    def test_litellm_disabled_not_in_chain(self):
        """When LiteLLM is disabled, it does not appear in chain."""
        from lib.sidekick.llm_gateway import LLMGateway
        gw = LLMGateway()
        with patch.object(gw, "_local_available", return_value=True), \
             patch.object(gw, "_claude_available", return_value=False), \
             patch.object(gw, "_openai_available", return_value=False), \
             patch.object(gw, "_litellm_available", return_value=False):
            chain = gw._resolve_provider_chain([{"role": "user", "content": "hello"}])
            assert "litellm" not in chain
