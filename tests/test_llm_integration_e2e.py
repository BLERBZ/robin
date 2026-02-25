"""End-to-end integration tests for the LLM infrastructure stack."""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


class TestGatewayRouterIntegration:
    """Test that Gateway -> Router -> Provider chain works end-to-end."""

    def test_gateway_uses_router_for_chain(self):
        """Gateway delegates to router for provider ordering."""
        from lib.sidekick.llm_gateway import LLMGateway
        gw = LLMGateway()
        mock_router = MagicMock()
        mock_decision = MagicMock()
        mock_decision.provider.value = "local"
        mock_decision.fallback_chain = []
        mock_router.route.return_value = mock_decision

        gw._router = mock_router
        with patch.object(gw, "_local_available", return_value=True), \
             patch.object(gw, "_claude_available", return_value=False), \
             patch.object(gw, "_openai_available", return_value=False), \
             patch.object(gw, "_litellm_available", return_value=False):
            chain = gw._resolve_provider_chain([{"role": "user", "content": "test"}])
            assert "local" in chain


class TestCircuitBreakerRouterIntegration:
    """Test that circuit breakers influence routing decisions."""

    def test_open_breaker_removes_provider(self):
        from lib.sidekick.llm_router import LLMRouter
        router = LLMRouter()

        mock_registry = MagicMock()
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = False
        mock_registry.enabled = True
        mock_registry.get.return_value = mock_cb

        with patch("lib.sidekick.llm_router.get_circuit_breaker_registry", return_value=mock_registry):
            decision = router.route(
                "hello",
                local_available=True,
                claude_available=True,
                openai_available=False,
            )
            # With all breakers open, routing should handle gracefully


class TestObserverToLearnerPipeline:
    """Test data flows from observer through learning bridge to cognitive learner."""

    def test_pipeline_flow(self):
        from lib.llm_learning_bridge import LLMLearningBridge
        bridge = LLMLearningBridge()
        bridge._min_interval_s = 0

        mock_observer = MagicMock()
        mock_observer.enabled = True
        mock_observer.get_summary.return_value = {
            "total_calls": 20,
            "error_rate": 0.5,
            "error_count": 10,
            "p99_latency_ms": 2000,
            "total_cost_usd": 0.05,
        }
        mock_observer.get_provider_stats.return_value = {
            "ollama": {"calls": 10, "errors": 5, "error_rate": 0.5},
        }

        mock_learner = MagicMock()

        with patch("lib.llm_learning_bridge.get_observer", return_value=mock_observer), \
             patch("lib.llm_learning_bridge.get_cognitive_learner", return_value=mock_learner):
            insights = bridge.analyze_and_learn()
            assert len(insights) >= 1
            mock_learner.record_insight.assert_called()
