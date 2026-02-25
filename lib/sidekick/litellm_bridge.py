"""LiteLLM proxy bridge for Kait AI Sidekick.

Provides a unified LiteLLMClient that routes cloud LLM calls through the
LiteLLM proxy, giving Kait access to 100+ providers with caching, cost
tracking, and automatic failover — all through an OpenAI-compatible API.

The LiteLLM proxy must be running (see scripts/install_litellm.sh and
config/litellm_config.yaml).

Usage:
    from lib.sidekick.litellm_bridge import get_litellm_client
    client = get_litellm_client()
    if client.available():
        response = client.chat([{"role": "user", "content": "Hello"}])

Environment variables:
    KAIT_LITELLM_ENABLED       - Enable LiteLLM routing (default: false)
    KAIT_LITELLM_PORT          - Proxy port (default: 4000)
    KAIT_LITELLM_MASTER_KEY    - Optional auth key for the proxy
    KAIT_LITELLM_CLAUDE_MODEL  - Model alias for Claude (default: claude-default)
    KAIT_LITELLM_OPENAI_MODEL  - Model alias for OpenAI (default: openai-default)
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from lib.diagnostics import log_debug
from lib.llm_observability import observed

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LOG_TAG = "litellm_bridge"
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def _litellm_enabled() -> bool:
    return os.environ.get("KAIT_LITELLM_ENABLED", "false").strip().lower() in _ENABLED_VALUES


def _litellm_base_url() -> str:
    host = os.environ.get("KAIT_LITELLM_HOST", "localhost").strip()
    port = os.environ.get("KAIT_LITELLM_PORT", "4000").strip()
    return f"http://{host}:{port}"


def _litellm_master_key() -> Optional[str]:
    key = os.environ.get("KAIT_LITELLM_MASTER_KEY", "").strip()
    return key if key else None


_DEFAULT_CLAUDE_MODEL = "claude-default"
_DEFAULT_OPENAI_MODEL = "openai-default"
_CHAT_TIMEOUT_S = 120
_HEALTH_TIMEOUT_S = 5


# ---------------------------------------------------------------------------
# LiteLLMClient
# ---------------------------------------------------------------------------

class LiteLLMClient:
    """Client for the LiteLLM proxy.

    Mirrors ClaudeClient/OpenAIClient interface for drop-in use within
    the Kait sidekick routing layer. Calls the OpenAI-compatible
    /v1/chat/completions endpoint on the LiteLLM proxy.
    """

    def __init__(self) -> None:
        self._base_url = _litellm_base_url()
        self._master_key = _litellm_master_key()
        self._enabled = _litellm_enabled()
        self._disabled = False

        # Model aliases (configurable via env)
        self._claude_model = (
            os.environ.get("KAIT_LITELLM_CLAUDE_MODEL", "").strip()
            or _DEFAULT_CLAUDE_MODEL
        )
        self._openai_model = (
            os.environ.get("KAIT_LITELLM_OPENAI_MODEL", "").strip()
            or _DEFAULT_OPENAI_MODEL
        )
        self._model = self._claude_model  # Default model

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def available(self) -> bool:
        """Return True if LiteLLM is enabled and the proxy is reachable."""
        if not self._enabled or self._disabled:
            return False
        return self.health_check()

    @property
    def model(self) -> str:
        return self._model

    def health_check(self) -> bool:
        """Check if the LiteLLM proxy is responding."""
        try:
            url = f"{self._base_url}/health"
            req = urllib.request.Request(url, method="GET", headers=self._headers())
            resp = urllib.request.urlopen(req, timeout=_HEALTH_TIMEOUT_S)
            return 200 <= resp.status < 300
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Chat (blocking)
    # ------------------------------------------------------------------

    @observed("litellm")
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """Send a chat request through LiteLLM and return the response text.

        Returns None on failure so the caller can fall through to another provider.
        """
        if not self._enabled or self._disabled:
            return None

        resolved_model = model or self._model
        api_messages = self._prepare_messages(messages, system)
        if not api_messages:
            return None

        payload = {
            "model": resolved_model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            url = f"{self._base_url}/v1/chat/completions"
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers=self._headers(),
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=_CHAT_TIMEOUT_S)
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)

            choices = data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                if content:
                    return content
            return None

        except urllib.error.HTTPError as exc:
            return self._handle_http_error(exc)
        except Exception as exc:
            log_debug(_LOG_TAG, f"LiteLLM chat error: {exc}", exc)
            return None

    # ------------------------------------------------------------------
    # Chat streaming
    # ------------------------------------------------------------------

    @observed("litellm")
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Stream response tokens from LiteLLM.

        Yields individual text deltas as they arrive. Falls through
        (yields nothing) on failure.
        """
        if not self._enabled or self._disabled:
            return

        resolved_model = model or self._model
        api_messages = self._prepare_messages(messages, system)
        if not api_messages:
            return

        payload = {
            "model": resolved_model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            url = f"{self._base_url}/v1/chat/completions"
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers=self._headers(),
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=_CHAT_TIMEOUT_S)

            for raw_line in resp:
                line = raw_line.decode("utf-8").strip() if isinstance(raw_line, bytes) else raw_line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]  # strip "data: "
                if data_str.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

        except Exception as exc:
            log_debug(_LOG_TAG, f"LiteLLM stream error: {exc}", exc)

    # ------------------------------------------------------------------
    # Model selection
    # ------------------------------------------------------------------

    def set_model(self, model: str) -> None:
        """Switch the default model alias."""
        self._model = model

    def use_claude_model(self) -> None:
        """Switch to the Claude model alias."""
        self._model = self._claude_model

    def use_openai_model(self) -> None:
        """Switch to the OpenAI model alias."""
        self._model = self._openai_model

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._master_key:
            headers["Authorization"] = f"Bearer {self._master_key}"
        return headers

    def _prepare_messages(
        self,
        messages: List[Dict[str, str]],
        system_override: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Translate messages into OpenAI-compatible format."""
        api_messages: List[Dict[str, str]] = []
        system_parts: List[str] = []

        if system_override:
            system_parts.append(system_override)

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role in ("user", "assistant"):
                api_messages.append({"role": role, "content": content})

        if system_parts:
            api_messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

        return api_messages

    def _handle_http_error(self, exc: urllib.error.HTTPError) -> None:
        """Handle HTTP errors from the LiteLLM proxy."""
        code = exc.code
        if code == 401:
            self._disabled = True
            log_debug(_LOG_TAG, "Invalid master key — disabling for session", exc)
        elif code == 429:
            log_debug(_LOG_TAG, "Rate limited (429)", exc)
        else:
            log_debug(_LOG_TAG, f"LiteLLM HTTP error {code}", exc)
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[LiteLLMClient] = None


def get_litellm_client() -> LiteLLMClient:
    """Return the shared LiteLLMClient singleton.

    Thread-safe. The client is created once on first call.
    """
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = LiteLLMClient()
            if _singleton_instance._enabled:
                log_debug(_LOG_TAG, f"LiteLLM bridge initialized (base={_singleton_instance._base_url})", None)
        return _singleton_instance
