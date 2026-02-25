"""Unified LLM Gateway for Kait Intelligence.

Single entry point for all LLM calls. Internally manages:
- Olla-backed local inference (when KAIT_OLLA_ENABLED=true)
- LiteLLM-backed cloud inference (when KAIT_LITELLM_ENABLED=true)
- Legacy direct bridges as fallback
- Circuit breaker integration
- LLM router for complexity-based routing

Usage:
    from lib.sidekick.llm_gateway import get_llm_gateway
    gw = get_llm_gateway()
    response = gw.chat([{"role": "user", "content": "Hello"}])
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Generator, List, Optional

from lib.diagnostics import log_debug

_LOG_TAG = "llm_gateway"
_ENABLED_VALUES = {"1", "true", "yes", "on"}


class LLMGateway:
    """Unified LLM gateway that routes through the best available provider.

    Routing priority:
    1. LLM Router scores complexity and selects provider
    2. Circuit breakers filter out degraded providers
    3. Olla (if enabled) handles local requests
    4. LiteLLM (if enabled) handles cloud requests
    5. Legacy bridges as fallback
    """

    def __init__(self) -> None:
        self._olla_enabled = os.environ.get("KAIT_OLLA_ENABLED", "false").strip().lower() in _ENABLED_VALUES
        self._litellm_enabled = os.environ.get("KAIT_LITELLM_ENABLED", "false").strip().lower() in _ENABLED_VALUES

        # Lazy-loaded clients
        self._local_client = None
        self._claude_client = None
        self._openai_client = None
        self._litellm_client = None
        self._router = None
        self._cb_registry = None

    # ------------------------------------------------------------------
    # Client accessors (lazy-loaded)
    # ------------------------------------------------------------------

    def _get_local(self):
        if self._local_client is None:
            from lib.sidekick.local_llm import get_llm_client
            self._local_client = get_llm_client()
        return self._local_client

    def _get_claude(self):
        if self._claude_client is None:
            from lib.sidekick.claude_bridge import get_claude_client
            self._claude_client = get_claude_client()
        return self._claude_client

    def _get_openai(self):
        if self._openai_client is None:
            from lib.sidekick.openai_bridge import get_openai_client
            self._openai_client = get_openai_client()
        return self._openai_client

    def _get_litellm(self):
        if self._litellm_client is None:
            from lib.sidekick.litellm_bridge import get_litellm_client
            self._litellm_client = get_litellm_client()
        return self._litellm_client

    def _get_router(self):
        if self._router is None:
            from lib.sidekick.llm_router import get_llm_router
            self._router = get_llm_router()
        return self._router

    def _get_cb_registry(self):
        if self._cb_registry is None:
            try:
                from lib.llm_circuit_breaker import get_circuit_breaker_registry
                self._cb_registry = get_circuit_breaker_registry()
            except Exception:
                self._cb_registry = None
        return self._cb_registry

    # ------------------------------------------------------------------
    # Provider availability (with circuit breaker overlay)
    # ------------------------------------------------------------------

    def _local_available(self) -> bool:
        try:
            client = self._get_local()
            if not client.health_check():
                return False
            reg = self._get_cb_registry()
            if reg and not reg.get("ollama").allow_request():
                return False
            return True
        except Exception:
            return False

    def _claude_available(self) -> bool:
        try:
            client = self._get_claude()
            if not client.available():
                return False
            reg = self._get_cb_registry()
            if reg and not reg.get("claude").allow_request():
                return False
            return True
        except Exception:
            return False

    def _openai_available(self) -> bool:
        try:
            client = self._get_openai()
            if not client.available():
                return False
            reg = self._get_cb_registry()
            if reg and not reg.get("openai").allow_request():
                return False
            return True
        except Exception:
            return False

    def _litellm_available(self) -> bool:
        if not self._litellm_enabled:
            return False
        try:
            client = self._get_litellm()
            if not client.available():
                return False
            reg = self._get_cb_registry()
            if reg and not reg.get("litellm").allow_request():
                return False
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Chat (main API)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        override_provider: Optional[str] = None,
    ) -> Optional[str]:
        """Send a chat request through the best available provider.

        Returns the response text, or None if all providers fail.
        """
        from lib.sidekick.llm_router import LLMProvider

        providers = self._resolve_provider_chain(
            messages, override_provider=override_provider,
        )

        for provider in providers:
            result = self._try_chat(
                provider, messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if result is not None:
                self._record_success(provider)
                return result
            self._record_failure(provider)

        return None

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        override_provider: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Stream response tokens from the best available provider."""
        providers = self._resolve_provider_chain(
            messages, override_provider=override_provider,
        )

        for provider in providers:
            try:
                gen = self._try_chat_stream(
                    provider, messages,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                # Peek at first token to verify the stream works
                first = next(gen, None)
                if first is not None:
                    self._record_success(provider)
                    yield first
                    yield from gen
                    return
                # Empty stream, try next provider
                self._record_failure(provider)
            except Exception:
                self._record_failure(provider)
                continue

    def embed(
        self,
        text: str,
        *,
        model: Optional[str] = None,
    ) -> Optional[List[float]]:
        """Generate an embedding vector. Uses local Ollama only."""
        try:
            client = self._get_local()
            return client.embed(text, model=model)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Provider chain resolution
    # ------------------------------------------------------------------

    def _resolve_provider_chain(
        self,
        messages: List[Dict[str, str]],
        override_provider: Optional[str] = None,
    ) -> List[str]:
        """Determine the ordered list of providers to try."""
        from lib.sidekick.llm_router import LLMProvider

        local_avail = self._local_available()
        claude_avail = self._claude_available()
        openai_avail = self._openai_available()
        litellm_avail = self._litellm_available()

        # Direct override
        if override_provider:
            chain = [override_provider]
            # Add fallbacks
            for p in ["local", "claude", "openai", "litellm"]:
                if p != override_provider:
                    chain.append(p)
            return chain

        # Use router for complexity-based routing
        prompt = ""
        for msg in messages:
            if msg.get("role") == "user":
                prompt = msg.get("content", "")
                break

        try:
            router = self._get_router()
            # Map LiteLLM availability to cloud availability
            effective_claude = claude_avail or (litellm_avail and self._litellm_enabled)
            effective_openai = openai_avail or (litellm_avail and self._litellm_enabled)

            decision = router.route(
                prompt,
                local_available=local_avail,
                claude_available=effective_claude,
                openai_available=effective_openai,
            )

            chain = [decision.provider.value]
            for fb in decision.fallback_chain:
                if fb.value not in chain:
                    chain.append(fb.value)

            # Insert litellm as cloud fallback if enabled
            if litellm_avail and "litellm" not in chain:
                # Place after direct cloud bridges
                chain.append("litellm")

            return chain

        except Exception:
            # Fallback: local -> claude -> openai -> litellm
            chain = []
            if local_avail:
                chain.append("local")
            if claude_avail:
                chain.append("claude")
            if openai_avail:
                chain.append("openai")
            if litellm_avail:
                chain.append("litellm")
            return chain or ["local"]

    # ------------------------------------------------------------------
    # Per-provider chat dispatch
    # ------------------------------------------------------------------

    def _try_chat(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> Optional[str]:
        try:
            if provider == "local":
                client = self._get_local()
                return client.chat(messages, temperature=kwargs.get("temperature", 0.7))
            elif provider == "claude":
                client = self._get_claude()
                return client.chat(
                    messages,
                    system=kwargs.get("system"),
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 4096),
                )
            elif provider == "openai":
                client = self._get_openai()
                return client.chat(
                    messages,
                    system=kwargs.get("system"),
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 4096),
                )
            elif provider == "litellm":
                client = self._get_litellm()
                return client.chat(
                    messages,
                    system=kwargs.get("system"),
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 4096),
                )
        except Exception as exc:
            log_debug(_LOG_TAG, f"Provider {provider} chat failed: {exc}", exc)
        return None

    def _try_chat_stream(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> Generator[str, None, None]:
        if provider == "local":
            client = self._get_local()
            yield from client.chat_stream(messages, temperature=kwargs.get("temperature", 0.7))
        elif provider == "claude":
            client = self._get_claude()
            yield from client.chat_stream(
                messages,
                system=kwargs.get("system"),
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
        elif provider == "openai":
            client = self._get_openai()
            yield from client.chat_stream(
                messages,
                system=kwargs.get("system"),
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
        elif provider == "litellm":
            client = self._get_litellm()
            yield from client.chat_stream(
                messages,
                system=kwargs.get("system"),
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096),
            )

    # ------------------------------------------------------------------
    # Circuit breaker integration
    # ------------------------------------------------------------------

    def _record_success(self, provider: str) -> None:
        try:
            reg = self._get_cb_registry()
            if reg:
                # Map provider names to circuit breaker names
                cb_name = {"local": "ollama"}.get(provider, provider)
                reg.get(cb_name).record_success()
        except Exception:
            pass

    def _record_failure(self, provider: str) -> None:
        try:
            reg = self._get_cb_registry()
            if reg:
                cb_name = {"local": "ollama"}.get(provider, provider)
                reg.get(cb_name).record_failure()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Status / health
    # ------------------------------------------------------------------

    def available_providers(self) -> List[str]:
        """Return list of currently available provider names."""
        providers = []
        if self._local_available():
            providers.append("local")
        if self._claude_available():
            providers.append("claude")
        if self._openai_available():
            providers.append("openai")
        if self._litellm_available():
            providers.append("litellm")
        return providers

    def health(self) -> Dict[str, Any]:
        """Return health status of all providers."""
        return {
            "local": {"available": self._local_available(), "olla_enabled": self._olla_enabled},
            "claude": {"available": self._claude_available()},
            "openai": {"available": self._openai_available()},
            "litellm": {"available": self._litellm_available(), "enabled": self._litellm_enabled},
        }

    def cost_summary(self, window_s: float = 3600) -> Dict[str, Any]:
        """Return cost summary from the observer."""
        try:
            from lib.llm_observability import get_observer
            obs = get_observer()
            return obs.get_summary(window_s=window_s)
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    """Return the shared LLMGateway singleton. Thread-safe."""
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = LLMGateway()
            log_debug(
                _LOG_TAG,
                f"LLM Gateway initialized (olla={_singleton_instance._olla_enabled}, litellm={_singleton_instance._litellm_enabled})",
                None,
            )
        return _singleton_instance
