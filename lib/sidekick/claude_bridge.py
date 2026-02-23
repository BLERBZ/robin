"""Anthropic Claude API bridge for Kait AI Sidekick.

Provides a ClaudeClient that mirrors OllamaClient's chat()/chat_stream()
interface, enabling seamless escalation from local LLM to Claude when the
local model hits its limits or the user explicitly requests Claude.

SDK-first: tries the official ``anthropic`` package, falls back to raw HTTP
via ``httpx`` (already a project dependency).

Usage:
    from lib.sidekick.claude_bridge import get_claude_client
    claude = get_claude_client()
    if claude.available():
        response = claude.chat([{"role": "user", "content": "Hello"}])

Environment variables:
    ANTHROPIC_API_KEY   - API key (also checks CLAUDE_API_KEY)
    KAIT_CLAUDE_MODEL   - Override default model (default: claude-sonnet-4-20250514)
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from lib.diagnostics import log_debug

# ---------------------------------------------------------------------------
# .env loader (mirrors advisory_synthesizer._load_repo_env_value)
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

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_LOG_TAG = "claude_bridge"

# ---------------------------------------------------------------------------
# SDK / HTTP detection
# ---------------------------------------------------------------------------

_anthropic_mod = None
try:
    import anthropic as _anthropic_mod  # type: ignore[import-untyped]
except ImportError:
    _anthropic_mod = None

_httpx_mod = None
try:
    import httpx as _httpx_mod  # type: ignore[import-untyped]
except ImportError:
    _httpx_mod = None


# ---------------------------------------------------------------------------
# Message translation helpers
# ---------------------------------------------------------------------------

def translate_messages(
    messages: List[Dict[str, str]],
    system_override: Optional[str] = None,
) -> tuple[str, List[Dict[str, str]]]:
    """Separate system messages from user/assistant messages.

    Anthropic's API requires system content as a top-level ``system``
    parameter, not inside the ``messages`` array.

    Returns (system_text, filtered_messages).
    """
    system_parts: List[str] = []
    filtered: List[Dict[str, str]] = []

    if system_override:
        system_parts.append(system_override)

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant"):
            filtered.append({"role": role, "content": content})

    # Anthropic requires messages to start with a user message.
    # If the first message is assistant, prepend a minimal user turn.
    if filtered and filtered[0]["role"] == "assistant":
        filtered.insert(0, {"role": "user", "content": "(continued conversation)"})

    # Ensure alternating user/assistant - merge consecutive same-role messages.
    merged: List[Dict[str, str]] = []
    for msg in filtered:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n\n" + msg["content"]
        else:
            merged.append(dict(msg))

    system_text = "\n\n".join(system_parts) if system_parts else ""
    return system_text, merged


# ---------------------------------------------------------------------------
# ClaudeClient
# ---------------------------------------------------------------------------

class ClaudeClient:
    """Client for the Anthropic Claude API.

    Mirrors OllamaClient's chat()/chat_stream() interface for drop-in use
    within the Kait sidekick.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or _load_repo_env_value(
            "ANTHROPIC_API_KEY", "CLAUDE_API_KEY",
        )
        self._model = os.getenv("KAIT_CLAUDE_MODEL", _DEFAULT_MODEL)
        self._disabled = False  # Set True on 401 (invalid key)
        self._sdk_client: Any = None

        if self._api_key and _anthropic_mod is not None:
            try:
                self._sdk_client = _anthropic_mod.Anthropic(api_key=self._api_key)
            except Exception as exc:
                log_debug(_LOG_TAG, "SDK init failed, will use httpx", exc)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def available(self) -> bool:
        """Return True if an API key is configured and the client is not disabled."""
        return bool(self._api_key) and not self._disabled

    @property
    def model(self) -> str:
        return self._model

    # ------------------------------------------------------------------
    # Chat (blocking)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Optional[str]:
        """Send a chat request and return the full response text.

        Returns None on failure (rate-limit, network error, etc.)
        so the caller can fall through to another provider.
        """
        if not self.available():
            return None

        system_text, api_messages = translate_messages(messages, system)
        if not api_messages:
            return None

        # Try SDK first
        if self._sdk_client is not None:
            return self._chat_sdk(system_text, api_messages, temperature, max_tokens)

        # Fallback to raw HTTP
        if _httpx_mod is not None:
            return self._chat_http(system_text, api_messages, temperature, max_tokens)

        log_debug(_LOG_TAG, "No HTTP client available (need anthropic or httpx)", None)
        return None

    def _chat_sdk(
        self,
        system_text: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Optional[str]:
        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            if system_text:
                kwargs["system"] = system_text
            response = self._sdk_client.messages.create(**kwargs)
            text_parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            return "".join(text_parts) if text_parts else None
        except Exception as exc:
            return self._handle_error(exc)

    def _chat_http(
        self,
        system_text: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Optional[str]:
        payload: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system_text:
            payload["system"] = system_text

        try:
            resp = _httpx_mod.post(
                _API_URL,
                json=payload,
                headers=self._http_headers(),
                timeout=120.0,
            )
            if resp.status_code == 401:
                self._disabled = True
                log_debug(_LOG_TAG, "Invalid API key — disabling for session", None)
                return None
            if resp.status_code == 429:
                log_debug(_LOG_TAG, "Rate limited (429)", None)
                return None
            resp.raise_for_status()
            data = resp.json()
            text_parts = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            return "".join(text_parts) if text_parts else None
        except Exception as exc:
            return self._handle_error(exc)

    # ------------------------------------------------------------------
    # Chat streaming
    # ------------------------------------------------------------------

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """Stream response tokens from Claude.

        Yields individual text deltas as they arrive.  Falls through
        (yields nothing) on failure.
        """
        if not self.available():
            return

        system_text, api_messages = translate_messages(messages, system)
        if not api_messages:
            return

        # Try SDK streaming first
        if self._sdk_client is not None:
            yield from self._stream_sdk(system_text, api_messages, temperature, max_tokens)
            return

        # Fallback to raw HTTP SSE
        if _httpx_mod is not None:
            yield from self._stream_http(system_text, api_messages, temperature, max_tokens)
            return

    def _stream_sdk(
        self,
        system_text: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Generator[str, None, None]:
        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            if system_text:
                kwargs["system"] = system_text
            with self._sdk_client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as exc:
            self._handle_error(exc)

    def _stream_http(
        self,
        system_text: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Generator[str, None, None]:
        payload: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text

        try:
            with _httpx_mod.stream(
                "POST",
                _API_URL,
                json=payload,
                headers=self._http_headers(),
                timeout=120.0,
            ) as resp:
                if resp.status_code == 401:
                    self._disabled = True
                    log_debug(_LOG_TAG, "Invalid API key — disabling for session", None)
                    return
                if resp.status_code == 429:
                    log_debug(_LOG_TAG, "Rate limited (429)", None)
                    return
                if resp.status_code >= 400:
                    log_debug(_LOG_TAG, f"API error {resp.status_code}", None)
                    return

                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # strip "data: "
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield text
        except Exception as exc:
            self._handle_error(exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _http_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self._api_key or "",
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

    def _handle_error(self, exc: Exception) -> None:
        """Centralized error handling. Returns None (for chat()) or logs."""
        exc_str = str(exc).lower()
        if "401" in exc_str or "authentication" in exc_str or "invalid" in exc_str:
            self._disabled = True
            log_debug(_LOG_TAG, "Invalid API key — disabling for session", exc)
        elif "429" in exc_str or "rate" in exc_str:
            log_debug(_LOG_TAG, "Rate limited", exc)
        else:
            log_debug(_LOG_TAG, "Claude API error", exc)
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[ClaudeClient] = None


def get_claude_client() -> ClaudeClient:
    """Return the shared ClaudeClient singleton.

    Thread-safe. The client is created once on first call.
    """
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = ClaudeClient()
        return _singleton_instance
