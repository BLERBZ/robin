"""Tests for LiteLLM bridge client."""

from __future__ import annotations
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock


class TestLiteLLMClient:
    """Test LiteLLMClient interface."""

    def _make_client(self, enabled=True):
        with patch.dict("os.environ", {
            "KAIT_LITELLM_ENABLED": "true" if enabled else "false",
            "KAIT_LITELLM_PORT": "4000",
        }):
            from lib.sidekick.litellm_bridge import LiteLLMClient
            return LiteLLMClient()

    def test_disabled_returns_none(self):
        client = self._make_client(enabled=False)
        assert client.chat([{"role": "user", "content": "hi"}]) is None

    def test_available_when_healthy(self):
        client = self._make_client()
        with patch.object(client, "health_check", return_value=True):
            assert client.available() is True

    def test_unavailable_when_unhealthy(self):
        client = self._make_client()
        with patch.object(client, "health_check", return_value=False):
            assert client.available() is False

    @patch("urllib.request.urlopen")
    def test_chat_returns_content(self, mock_urlopen):
        client = self._make_client()
        response_data = {
            "choices": [{"message": {"content": "Hello back!"}}]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        result = client.chat([{"role": "user", "content": "hi"}])
        assert result == "Hello back!"

    def test_model_switching(self):
        client = self._make_client()
        client.use_claude_model()
        assert "claude" in client.model
        client.use_openai_model()
        assert "openai" in client.model

    def test_prepare_messages_with_system(self):
        client = self._make_client()
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = client._prepare_messages(msgs, system_override="Be helpful")
        assert result[0]["role"] == "system"
        assert "Be helpful" in result[0]["content"]


class TestLiteLLMSingleton:
    def test_singleton_returns_same_instance(self):
        import lib.sidekick.litellm_bridge as mod
        mod._singleton_instance = None
        c1 = mod.get_litellm_client()
        c2 = mod.get_litellm_client()
        assert c1 is c2
        mod._singleton_instance = None  # cleanup
