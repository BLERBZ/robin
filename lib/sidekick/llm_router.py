"""Intelligent LLM routing for Kait AI Sidekick.

Uses RouteLLM's classifier to score query complexity and decide whether to
route to a strong cloud model (Claude/OpenAI) or the local Ollama model.

Only RouteLLM's scoring function is used — all actual LLM calls remain
within Kait's own clients (streaming, mood pulsing, error handling intact).

If RouteLLM is not installed or the router is disabled via env vars, the
system falls back to legacy Ollama-first behavior with Claude escalation
on failure.

Development/Build routing policy:
    Any request that involves developing or building Kait or Robin is
    forced to a cloud provider (Claude preferred, then OpenAI).  Ollama
    is only used as a last resort when neither cloud provider is available.

Environment variables:
    KAIT_ROUTER_ENABLED    - Enable intelligent routing (default: false)
    KAIT_ROUTER_TYPE       - Router type: mf|sw_ranking|bert (default: mf)
    KAIT_ROUTER_THRESHOLD  - Score threshold (default: 0.11593)
    KAIT_ROUTER_STRONG     - Strong provider: claude|openai (default: claude)
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from lib.diagnostics import log_debug

# ---------------------------------------------------------------------------
# .env loader (same pattern as claude_bridge / openai_bridge)
# ---------------------------------------------------------------------------

_REPO_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
_LOG_TAG = "llm_router"


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
# RouteLLM detection
# ---------------------------------------------------------------------------

_routellm_available = False
_routellm_controller = None

try:
    from routellm.controller import Controller as _RouteLLMController  # type: ignore[import-untyped]
    _routellm_available = True
except ImportError:
    _routellm_available = False


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class LLMProvider(Enum):
    """Available LLM providers."""
    LOCAL = "local"      # Ollama
    CLAUDE = "claude"    # Anthropic Claude
    OPENAI = "openai"    # OpenAI


@dataclass
class RoutingDecision:
    """Result of the routing decision."""
    provider: LLMProvider
    score: float                          # 0.0-1.0 complexity score
    reason: str                           # Human-readable explanation
    fallback_chain: List[LLMProvider] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dev/Build detection for Kait & Robin
# ---------------------------------------------------------------------------

# Project names that trigger cloud-first routing
_DEV_PROJECT_RE = re.compile(
    r"\b(?:kait|robin)\b",
    re.IGNORECASE,
)

# Action keywords that indicate development/build intent
_DEV_ACTION_RE = re.compile(
    r"\b(?:"
    r"build|develop|implement|code|refactor|debug|fix|patch|deploy|ship|release"
    r"|architect|scaffold|bootstrap|create|write|engineer|program|compile"
    r"|test|testing|ci|cd|pipeline|merge|pr|pull\s*request|commit"
    r"|feature|bug|issue|sprint|roadmap|milestone|backlog"
    r"|api|endpoint|route|schema|migration|database|model"
    r"|frontend|backend|fullstack|full[\s-]?stack|component|module|service"
    r"|install|setup|config|configure|integrate|upgrade|update|version"
    r")\b",
    re.IGNORECASE,
)


def _is_dev_build_request(prompt: str) -> bool:
    """Return True if the prompt is about developing or building Kait/Robin.

    Both a project name (kait/robin) AND a dev-action keyword must be
    present to avoid false positives on casual mentions.
    """
    return bool(_DEV_PROJECT_RE.search(prompt) and _DEV_ACTION_RE.search(prompt))


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------

class LLMRouter:
    """Intelligent LLM routing engine.

    Uses RouteLLM's classifier to score prompt complexity and route to
    the appropriate provider. Falls back to legacy behavior when disabled
    or when RouteLLM is not installed.
    """

    def __init__(self) -> None:
        # Configuration from env
        enabled_str = _load_repo_env_value("KAIT_ROUTER_ENABLED") or "true"
        self._enabled = enabled_str.lower() in ("1", "true", "yes")
        self._router_type = _load_repo_env_value("KAIT_ROUTER_TYPE") or "mf"
        threshold_str = _load_repo_env_value("KAIT_ROUTER_THRESHOLD") or "0.11593"
        try:
            self._threshold = float(threshold_str)
        except ValueError:
            self._threshold = 0.11593

        strong_str = (_load_repo_env_value("KAIT_ROUTER_STRONG") or "claude").lower()
        if strong_str == "openai":
            self._strong_provider = LLMProvider.OPENAI
        else:
            self._strong_provider = LLMProvider.CLAUDE

        # Initialize RouteLLM controller
        self._controller = None
        self._router_ready = False

        if self._enabled and _routellm_available:
            try:
                self._controller = _RouteLLMController(
                    routers=[self._router_type],
                    strong_model="gpt-4-1106-preview",
                    weak_model="mixtral-8x7b-instruct-v0.1",
                )
                self._router_ready = True
                log_debug(_LOG_TAG, f"RouteLLM initialized (type={self._router_type}, threshold={self._threshold})", None)
            except Exception as exc:
                log_debug(_LOG_TAG, "RouteLLM init failed — falling back to legacy routing", exc)
        elif self._enabled and not _routellm_available:
            log_debug(_LOG_TAG, "Router enabled but routellm not installed (pip install routellm)", None)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def ready(self) -> bool:
        return self._enabled and self._router_ready

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def router_type(self) -> str:
        return self._router_type

    @property
    def strong_provider(self) -> LLMProvider:
        return self._strong_provider

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(
        self,
        prompt: str,
        *,
        override_provider: Optional[LLMProvider] = None,
        local_available: bool = True,
        claude_available: bool = False,
        openai_available: bool = False,
    ) -> RoutingDecision:
        """Decide which provider should handle this prompt.

        Args:
            prompt: The user's input text.
            override_provider: Force a specific provider (e.g. /claude command).
            local_available: Whether Ollama is running.
            claude_available: Whether Claude API key is configured.
            openai_available: Whether OpenAI API key is configured.

        Returns:
            RoutingDecision with provider, score, reason, and fallback_chain.
        """
        # Circuit breaker overlay: suppress providers with open circuits
        try:
            from lib.llm_circuit_breaker import get_circuit_breaker_registry
            cb_reg = get_circuit_breaker_registry()
            if cb_reg.enabled:
                if local_available and not cb_reg.get("ollama").allow_request():
                    local_available = False
                    log_debug(_LOG_TAG, "Circuit breaker: Ollama circuit open, marking unavailable", None)
                if claude_available and not cb_reg.get("claude").allow_request():
                    claude_available = False
                    log_debug(_LOG_TAG, "Circuit breaker: Claude circuit open, marking unavailable", None)
                if openai_available and not cb_reg.get("openai").allow_request():
                    openai_available = False
                    log_debug(_LOG_TAG, "Circuit breaker: OpenAI circuit open, marking unavailable", None)
        except Exception:
            pass  # Circuit breakers unavailable; proceed without overlay

        # Direct override (e.g. /claude or /openai command)
        if override_provider is not None:
            chain = self._build_fallback_chain(
                override_provider, local_available, claude_available, openai_available,
            )
            return RoutingDecision(
                provider=override_provider,
                score=-1.0,
                reason=f"Direct override to {override_provider.value}",
                fallback_chain=chain,
            )

        # Dev/Build of Kait or Robin → force cloud provider
        if _is_dev_build_request(prompt):
            return self._dev_build_route(
                prompt, local_available, claude_available, openai_available,
            )

        # If router is not ready, use legacy logic (local-first)
        if not self._router_ready or not self._controller:
            return self._legacy_route(local_available, claude_available, openai_available, prompt=prompt)

        # Score the prompt with RouteLLM
        try:
            score = self._controller.calculate_strong_win_rate(
                prompt,
                router=self._router_type,
            )
        except Exception as exc:
            log_debug(_LOG_TAG, "RouteLLM scoring failed, using legacy routing", exc)
            return self._legacy_route(local_available, claude_available, openai_available, prompt=prompt)

        # Route based on score vs threshold
        if score >= self._threshold:
            # Complex query → strong model
            primary = self._strong_provider
            reason = f"Complex query (score={score:.3f} >= threshold={self._threshold})"
        else:
            # Simple query → local model
            primary = LLMProvider.LOCAL
            reason = f"Simple query (score={score:.3f} < threshold={self._threshold})"

        # Check if primary is available, fall through if not
        if primary == LLMProvider.LOCAL and not local_available:
            primary = self._strong_provider
            reason += " → local unavailable, using cloud"
        elif primary == LLMProvider.CLAUDE and not claude_available:
            if openai_available:
                primary = LLMProvider.OPENAI
                reason += " → Claude unavailable, using OpenAI"
            elif local_available:
                primary = LLMProvider.LOCAL
                reason += " → Claude unavailable, falling back to local"
        elif primary == LLMProvider.OPENAI and not openai_available:
            if claude_available:
                primary = LLMProvider.CLAUDE
                reason += " → OpenAI unavailable, using Claude"
            elif local_available:
                primary = LLMProvider.LOCAL
                reason += " → OpenAI unavailable, falling back to local"

        chain = self._build_fallback_chain(
            primary, local_available, claude_available, openai_available,
        )

        return RoutingDecision(
            provider=primary,
            score=score,
            reason=reason,
            fallback_chain=chain,
        )

    def _legacy_route(
        self,
        local_available: bool,
        claude_available: bool,
        openai_available: bool,
        *,
        prompt: str = "",
    ) -> RoutingDecision:
        """Legacy routing: local first, then Claude on failure.

        If *prompt* is a Kait/Robin dev/build request, cloud-first routing
        takes priority even in legacy mode.
        """
        # Dev/Build override applies in legacy mode too
        if prompt and _is_dev_build_request(prompt):
            return self._dev_build_route(
                prompt, local_available, claude_available, openai_available,
            )

        if local_available:
            primary = LLMProvider.LOCAL
            reason = "Legacy routing: local-first"
        elif claude_available:
            primary = LLMProvider.CLAUDE
            reason = "Legacy routing: local unavailable, using Claude"
        elif openai_available:
            primary = LLMProvider.OPENAI
            reason = "Legacy routing: local unavailable, using OpenAI"
        else:
            primary = LLMProvider.LOCAL
            reason = "Legacy routing: no providers available"

        chain = self._build_fallback_chain(
            primary, local_available, claude_available, openai_available,
        )
        return RoutingDecision(
            provider=primary,
            score=-1.0,
            reason=reason,
            fallback_chain=chain,
        )

    def _dev_build_route(
        self,
        prompt: str,
        local_available: bool,
        claude_available: bool,
        openai_available: bool,
    ) -> RoutingDecision:
        """Cloud-first routing for Kait/Robin development & build requests.

        Priority: Claude → OpenAI → Ollama (last resort only).
        """
        reason = "Dev/Build request (Kait/Robin) → cloud-first"

        if claude_available:
            primary = LLMProvider.CLAUDE
        elif openai_available:
            primary = LLMProvider.OPENAI
            reason += " → Claude unavailable, using OpenAI"
        elif local_available:
            primary = LLMProvider.LOCAL
            reason += " → no cloud providers available, falling back to local"
        else:
            primary = LLMProvider.LOCAL
            reason += " → no providers available"

        chain = self._build_cloud_first_fallback_chain(
            primary, local_available, claude_available, openai_available,
        )

        log_debug(
            _LOG_TAG,
            f"Dev/Build routing: {primary.value} (chain={[p.value for p in chain]})",
            None,
        )

        return RoutingDecision(
            provider=primary,
            score=1.0,  # Maximum — always treat as complex
            reason=reason,
            fallback_chain=chain,
        )

    def _build_cloud_first_fallback_chain(
        self,
        primary: LLMProvider,
        local_available: bool,
        claude_available: bool,
        openai_available: bool,
    ) -> List[LLMProvider]:
        """Build fallback chain with cloud providers before local."""
        chain: List[LLMProvider] = []
        # Cloud-first order: claude → openai → local
        candidates = [
            (LLMProvider.CLAUDE, claude_available),
            (LLMProvider.OPENAI, openai_available),
            (LLMProvider.LOCAL, local_available),
        ]
        for provider, available in candidates:
            if provider != primary and available:
                chain.append(provider)
        return chain

    def _build_fallback_chain(
        self,
        primary: LLMProvider,
        local_available: bool,
        claude_available: bool,
        openai_available: bool,
    ) -> List[LLMProvider]:
        """Build ordered fallback chain excluding the primary provider."""
        chain: List[LLMProvider] = []
        # Preferred fallback order: local → claude → openai
        candidates = [
            (LLMProvider.LOCAL, local_available),
            (LLMProvider.CLAUDE, claude_available),
            (LLMProvider.OPENAI, openai_available),
        ]
        for provider, available in candidates:
            if provider != primary and available:
                chain.append(provider)
        return chain


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Return the shared LLMRouter singleton.

    Thread-safe. The router is created once on first call.
    """
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = LLMRouter()
        return _singleton_instance
