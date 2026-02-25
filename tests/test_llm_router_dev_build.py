"""Tests for Dev/Build cloud-first routing in LLMRouter.

Verifies that requests about developing or building Kait/Robin are
always routed to Claude (preferred) or OpenAI, with Ollama as last resort.
"""

from __future__ import annotations

import pytest

from lib.sidekick.llm_router import (
    LLMProvider,
    LLMRouter,
    _is_dev_build_request,
)


# ---------------------------------------------------------------------------
# _is_dev_build_request detection tests
# ---------------------------------------------------------------------------

class TestDevBuildDetection:
    """Verify the regex-based intent detection."""

    @pytest.mark.parametrize("prompt", [
        "Build the Kait API endpoint",
        "Help me develop Robin's frontend",
        "Implement the new feature for kait",
        "Fix the bug in Robin's routing module",
        "Deploy kait to production",
        "Refactor the Robin backend service",
        "Write tests for Kait",
        "Debug the kait pipeline",
        "Create a new component for robin",
        "Update Kait's database schema",
        "Set up CI/CD for Robin",
        "Configure the Kait integration",
        "Let's build a new Kait feature",
        "I need to upgrade Robin's version",
        "Scaffold the Robin API",
        "Ship the next Kait release",
        "Merge the Kait PR",
    ])
    def test_detects_dev_build_prompts(self, prompt: str):
        assert _is_dev_build_request(prompt) is True

    @pytest.mark.parametrize("prompt", [
        "What is Kait?",                      # No dev action
        "Tell me about Robin",                 # No dev action
        "Build a web scraper",                 # No project name
        "Deploy the application",              # No project name
        "What's the weather today?",           # Neither
        "How does machine learning work?",     # Neither
        "Kait is cool",                        # No dev action
        "I like Robin",                        # No dev action
    ])
    def test_ignores_non_dev_build_prompts(self, prompt: str):
        assert _is_dev_build_request(prompt) is False


# ---------------------------------------------------------------------------
# Router integration tests
# ---------------------------------------------------------------------------

class TestDevBuildRouting:
    """Verify that the router forces cloud-first for dev/build requests."""

    def _make_router(self) -> LLMRouter:
        """Create a router (RouteLLM disabled, testing detection path)."""
        router = LLMRouter.__new__(LLMRouter)
        router._enabled = True
        router._router_type = "mf"
        router._threshold = 0.11593
        router._strong_provider = LLMProvider.CLAUDE
        router._controller = None
        router._router_ready = False
        return router

    def test_routes_to_claude_when_available(self):
        router = self._make_router()
        decision = router.route(
            "Build the Kait API",
            claude_available=True,
            openai_available=True,
            local_available=True,
        )
        assert decision.provider == LLMProvider.CLAUDE
        assert "Dev/Build" in decision.reason
        assert decision.score == 1.0

    def test_fallback_chain_is_cloud_first(self):
        router = self._make_router()
        decision = router.route(
            "Develop the Robin frontend",
            claude_available=True,
            openai_available=True,
            local_available=True,
        )
        assert decision.provider == LLMProvider.CLAUDE
        # Fallback order: openai before local
        assert decision.fallback_chain == [LLMProvider.OPENAI, LLMProvider.LOCAL]

    def test_routes_to_openai_when_claude_unavailable(self):
        router = self._make_router()
        decision = router.route(
            "Fix the Kait bug",
            claude_available=False,
            openai_available=True,
            local_available=True,
        )
        assert decision.provider == LLMProvider.OPENAI
        assert "Claude unavailable" in decision.reason

    def test_routes_to_local_only_as_last_resort(self):
        router = self._make_router()
        decision = router.route(
            "Deploy Robin to production",
            claude_available=False,
            openai_available=False,
            local_available=True,
        )
        assert decision.provider == LLMProvider.LOCAL
        assert "no cloud providers" in decision.reason

    def test_non_dev_build_uses_legacy_routing(self):
        router = self._make_router()
        decision = router.route(
            "What is the meaning of life?",
            claude_available=True,
            openai_available=True,
            local_available=True,
        )
        # Legacy routing → local-first
        assert decision.provider == LLMProvider.LOCAL
        assert "Legacy" in decision.reason

    def test_override_takes_priority_over_dev_build(self):
        router = self._make_router()
        decision = router.route(
            "Build the Kait API",
            override_provider=LLMProvider.LOCAL,
            claude_available=True,
            openai_available=True,
            local_available=True,
        )
        # Direct override wins even for dev/build requests
        assert decision.provider == LLMProvider.LOCAL
        assert "override" in decision.reason.lower()
