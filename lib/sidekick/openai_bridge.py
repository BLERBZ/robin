"""OpenAI API bridge for Kait AI Sidekick.

.. deprecated::
    Direct use of OpenAIClient is deprecated. Use ``LLMGateway`` from
    ``lib.sidekick.llm_gateway`` for all new LLM calls. This module remains
    functional as a fallback provider within the gateway.

Provides an OpenAIClient that mirrors ClaudeClient's chat()/chat_stream()
interface, enabling seamless routing to OpenAI models when the router or
user requests it.

SDK-first: uses the official ``openai`` package (already a project
dependency for TTS).

Usage:
    from lib.sidekick.openai_bridge import get_openai_client
    client = get_openai_client()
    if client.available():
        response = client.chat([{"role": "user", "content": "Hello"}])

Environment variables:
    OPENAI_API_KEY      - API key (already used for TTS)
    KAIT_OPENAI_MODEL   - Override default model (default: gpt-4o)
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from lib.diagnostics import log_debug
from lib.llm_observability import observed

# ---------------------------------------------------------------------------
# .env loader (same pattern as claude_bridge)
# ---------------------------------------------------------------------------

_REPO_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def _load_repo_env_value(*keys: str) -> Optional[str]:
    """Read KEY from process env first, then fallback to repo-level .env."""
    names = [str(k or "").strip() for k in keys if str(k or "").strip()]
    if not names:
        return None

    for name in names:
        val = os.getenv(name)
        if val:
            return str(val)

    try:
        if not _REPO_ENV_FILE.exists():
            return None
        with _REPO_ENV_FILE.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key not in names:
                    continue
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "gpt-4o"
_LOG_TAG = "openai_bridge"

# ---------------------------------------------------------------------------
# SDK detection
# ---------------------------------------------------------------------------

_openai_mod = None
try:
    import openai as _openai_mod  # type: ignore[import-untyped]
except ImportError:
    _openai_mod = None


# ---------------------------------------------------------------------------
# OpenAIClient
# ---------------------------------------------------------------------------

class OpenAIClient:
    """Client for the OpenAI API.

    Mirrors ClaudeClient's chat()/chat_stream() interface for drop-in use
    within the Kait sidekick routing layer.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or _load_repo_env_value("OPENAI_API_KEY")
        self._model = _load_repo_env_value("KAIT_OPENAI_MODEL") or _DEFAULT_MODEL
        self._disabled = False
        self._sdk_client: Any = None

        if self._api_key and _openai_mod is not None:
            try:
                self._sdk_client = _openai_mod.OpenAI(api_key=self._api_key)
            except Exception as exc:
                log_debug(_LOG_TAG, "SDK init failed", exc)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def available(self) -> bool:
        """Return True if an API key is configured and the client is not disabled."""
        return bool(self._api_key) and not self._disabled and self._sdk_client is not None

    @property
    def model(self) -> str:
        return self._model

    # ------------------------------------------------------------------
    # Chat (blocking)
    # ------------------------------------------------------------------

    @observed("openai")
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Optional[str]:
        """Send a chat request and return the full response text.

        Returns None on failure so the caller can fall through to another provider.
        """
        if not self.available():
            return None

        api_messages = self._prepare_messages(messages, system)
        if not api_messages:
            return None

        try:
            response = self._sdk_client.chat.completions.create(
                model=self._model,
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0] if response.choices else None
            if choice and choice.message and choice.message.content:
                return choice.message.content
            return None
        except Exception as exc:
            return self._handle_error(exc)

    # ------------------------------------------------------------------
    # Chat streaming
    # ------------------------------------------------------------------

    @observed("openai")
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """Stream response tokens from OpenAI.

        Yields individual text deltas as they arrive.  Falls through
        (yields nothing) on failure.
        """
        if not self.available():
            return

        api_messages = self._prepare_messages(messages, system)
        if not api_messages:
            return

        try:
            stream = self._sdk_client.chat.completions.create(
                model=self._model,
                messages=api_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
        except Exception as exc:
            self._handle_error(exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_messages(
        self,
        messages: List[Dict[str, str]],
        system_override: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Translate messages into OpenAI's format.

        OpenAI accepts system messages inline, so this is simpler than
        Anthropic's translation.
        """
        api_messages: List[Dict[str, str]] = []

        # Collect system content
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

        # Prepend merged system message
        if system_parts:
            api_messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

        return api_messages

    def _handle_error(self, exc: Exception) -> None:
        """Centralized error handling. Returns None (for chat()) or logs."""
        exc_str = str(exc).lower()
        if "401" in exc_str or "authentication" in exc_str or "invalid" in exc_str:
            self._disabled = True
            log_debug(_LOG_TAG, "Invalid API key — disabling for session", exc)
        elif "429" in exc_str or "rate" in exc_str:
            log_debug(_LOG_TAG, "Rate limited", exc)
        else:
            log_debug(_LOG_TAG, "OpenAI API error", exc)
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Return the shared OpenAIClient singleton.

    Thread-safe. The client is created once on first call.
    """
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = OpenAIClient()
        return _singleton_instance
