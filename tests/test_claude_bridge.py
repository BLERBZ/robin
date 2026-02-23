"""Tests for the Claude API bridge module."""

from __future__ import annotations

import json
import os
import types
from unittest import mock

import pytest

# Import the module under test
from lib.sidekick.claude_bridge import (
    ClaudeClient,
    get_claude_client,
    translate_messages,
    _load_repo_env_value,
)


# ---------------------------------------------------------------------------
# translate_messages
# ---------------------------------------------------------------------------


class TestTranslateMessages:
    """Test the message translation from Ollama format to Anthropic format."""

    def test_system_messages_extracted(self):
        """System messages should be extracted into the system parameter."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        system_text, filtered = translate_messages(messages)
        assert "You are a helpful assistant." in system_text
        assert len(filtered) == 1
        assert filtered[0]["role"] == "user"

    def test_multiple_system_messages_merged(self):
        """Multiple system messages should be joined with double-newline."""
        messages = [
            {"role": "system", "content": "Rule 1"},
            {"role": "system", "content": "Rule 2"},
            {"role": "user", "content": "Hi"},
        ]
        system_text, filtered = translate_messages(messages)
        assert "Rule 1" in system_text
        assert "Rule 2" in system_text
        assert len(filtered) == 1

    def test_system_override_prepended(self):
        """A system_override should appear in the system text."""
        messages = [
            {"role": "system", "content": "From messages"},
            {"role": "user", "content": "Hi"},
        ]
        system_text, _ = translate_messages(messages, system_override="Override text")
        assert system_text.startswith("Override text")
        assert "From messages" in system_text

    def test_user_assistant_preserved(self):
        """User and assistant messages pass through."""
        messages = [
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Answer"},
            {"role": "user", "content": "Follow up"},
        ]
        system_text, filtered = translate_messages(messages)
        assert system_text == ""
        assert len(filtered) == 3
        assert filtered[0]["role"] == "user"
        assert filtered[1]["role"] == "assistant"
        assert filtered[2]["role"] == "user"

    def test_consecutive_same_role_merged(self):
        """Consecutive messages with the same role should be merged."""
        messages = [
            {"role": "user", "content": "Part 1"},
            {"role": "user", "content": "Part 2"},
            {"role": "assistant", "content": "Reply"},
        ]
        _, filtered = translate_messages(messages)
        assert len(filtered) == 2
        assert "Part 1" in filtered[0]["content"]
        assert "Part 2" in filtered[0]["content"]

    def test_assistant_first_gets_user_prefix(self):
        """If first message is assistant, a user prefix should be inserted."""
        messages = [
            {"role": "assistant", "content": "Previous reply"},
            {"role": "user", "content": "New question"},
        ]
        _, filtered = translate_messages(messages)
        assert filtered[0]["role"] == "user"
        assert filtered[1]["role"] == "assistant"

    def test_empty_messages(self):
        """Empty input should return empty output."""
        system_text, filtered = translate_messages([])
        assert system_text == ""
        assert filtered == []


# ---------------------------------------------------------------------------
# ClaudeClient.available()
# ---------------------------------------------------------------------------


class TestClaudeClientAvailable:
    """Test the available() status check."""

    def test_no_api_key(self):
        """Client without API key should report unavailable."""
        with mock.patch.dict(os.environ, {}, clear=True):
            client = ClaudeClient(api_key=None)
            # Force no key
            client._api_key = None
            assert client.available() is False

    def test_with_api_key(self):
        """Client with API key should report available."""
        client = ClaudeClient(api_key="sk-test-key-123")
        assert client.available() is True

    def test_disabled_after_401(self):
        """Client should be disabled after an auth error."""
        client = ClaudeClient(api_key="sk-bad-key")
        client._disabled = True
        assert client.available() is False

    def test_model_default(self):
        """Default model should be claude-sonnet-4-20250514."""
        with mock.patch.dict(os.environ, {}, clear=False):
            # Remove override if present
            os.environ.pop("KAIT_CLAUDE_MODEL", None)
            client = ClaudeClient(api_key="sk-test")
            assert "claude-sonnet" in client.model

    def test_model_override(self):
        """KAIT_CLAUDE_MODEL env var should override default."""
        with mock.patch.dict(os.environ, {"KAIT_CLAUDE_MODEL": "claude-opus-4-20250514"}):
            client = ClaudeClient(api_key="sk-test")
            assert client.model == "claude-opus-4-20250514"


# ---------------------------------------------------------------------------
# ClaudeClient.chat() with mocked HTTP
# ---------------------------------------------------------------------------


class TestClaudeClientChat:
    """Test chat() via mocked httpx responses."""

    def _make_client(self) -> ClaudeClient:
        """Create a client with no SDK, forcing httpx path."""
        client = ClaudeClient(api_key="sk-test-key")
        client._sdk_client = None  # force httpx path
        return client

    def test_chat_success(self):
        """Successful chat should return the text content."""
        client = self._make_client()
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Hello from Claude!"}],
        }
        mock_response.raise_for_status = mock.MagicMock()

        with mock.patch("lib.sidekick.claude_bridge._httpx_mod") as httpx_mock:
            httpx_mock.post.return_value = mock_response
            result = client.chat([{"role": "user", "content": "Hi"}])

        assert result == "Hello from Claude!"

    def test_chat_401_disables(self):
        """A 401 response should disable the client for the session."""
        client = self._make_client()
        mock_response = mock.MagicMock()
        mock_response.status_code = 401

        with mock.patch("lib.sidekick.claude_bridge._httpx_mod") as httpx_mock:
            httpx_mock.post.return_value = mock_response
            result = client.chat([{"role": "user", "content": "Hi"}])

        assert result is None
        assert client._disabled is True

    def test_chat_429_returns_none(self):
        """A 429 rate limit should return None without disabling."""
        client = self._make_client()
        mock_response = mock.MagicMock()
        mock_response.status_code = 429

        with mock.patch("lib.sidekick.claude_bridge._httpx_mod") as httpx_mock:
            httpx_mock.post.return_value = mock_response
            result = client.chat([{"role": "user", "content": "Hi"}])

        assert result is None
        assert client._disabled is False

    def test_chat_unavailable_returns_none(self):
        """Chat on unavailable client should return None immediately."""
        client = ClaudeClient(api_key=None)
        client._api_key = None
        result = client.chat([{"role": "user", "content": "Hi"}])
        assert result is None


# ---------------------------------------------------------------------------
# ClaudeClient.chat_stream() with mocked HTTP SSE
# ---------------------------------------------------------------------------


class TestClaudeClientStream:
    """Test chat_stream() via mocked SSE responses."""

    def _make_client(self) -> ClaudeClient:
        client = ClaudeClient(api_key="sk-test-key")
        client._sdk_client = None
        return client

    def test_stream_yields_tokens(self):
        """Streaming should yield text_delta tokens."""
        client = self._make_client()

        sse_lines = [
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}',
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}',
            'data: {"type":"message_stop"}',
        ]

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = iter(sse_lines)
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch("lib.sidekick.claude_bridge._httpx_mod") as httpx_mock:
            httpx_mock.stream.return_value = mock_resp
            tokens = list(client.chat_stream([{"role": "user", "content": "Hi"}]))

        assert tokens == ["Hello", " world"]

    def test_stream_unavailable_yields_nothing(self):
        """Streaming on unavailable client should yield nothing."""
        client = ClaudeClient(api_key=None)
        client._api_key = None
        tokens = list(client.chat_stream([{"role": "user", "content": "Hi"}]))
        assert tokens == []


# ---------------------------------------------------------------------------
# Graceful degradation integration
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Verify that Claude failure falls through cleanly."""

    def test_chat_network_error_returns_none(self):
        """Network errors should return None, not raise."""
        client = ClaudeClient(api_key="sk-test")
        client._sdk_client = None

        with mock.patch("lib.sidekick.claude_bridge._httpx_mod") as httpx_mock:
            httpx_mock.post.side_effect = ConnectionError("Network down")
            result = client.chat([{"role": "user", "content": "Hi"}])

        assert result is None
        # Client should NOT be disabled on transient network error
        assert client._disabled is False

    def test_stream_network_error_yields_nothing(self):
        """Network errors during streaming should yield nothing."""
        client = ClaudeClient(api_key="sk-test")
        client._sdk_client = None

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.side_effect = ConnectionError("Network down")
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch("lib.sidekick.claude_bridge._httpx_mod") as httpx_mock:
            httpx_mock.stream.return_value = mock_resp
            tokens = list(client.chat_stream([{"role": "user", "content": "Hi"}]))

        assert tokens == []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """Test the get_claude_client singleton."""

    def test_singleton_returns_same_instance(self):
        """Multiple calls should return the same instance."""
        import lib.sidekick.claude_bridge as bridge_mod
        # Reset singleton
        bridge_mod._singleton_instance = None
        a = get_claude_client()
        b = get_claude_client()
        assert a is b
        # Clean up
        bridge_mod._singleton_instance = None
