"""LLM Learning Bridge — feeds observability data into Kait's cognitive learner.

Reads LLM call metrics from the observer, detects patterns (high fallback
rate, cost spikes, latency degradation), and feeds insights into the
cognitive learner for self-improvement.

Designed to run once per bridge cycle.

Usage:
    from lib.llm_learning_bridge import LLMLearningBridge
    bridge = LLMLearningBridge()
    bridge.analyze_and_learn()
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from lib.diagnostics import log_debug

_LOG_TAG = "llm_learning_bridge"

# Thresholds for pattern detection
_HIGH_ERROR_RATE = 0.25          # 25% error rate triggers insight
_HIGH_FALLBACK_RATE = 0.30       # 30% of calls using fallback
_COST_SPIKE_MULTIPLIER = 3.0     # 3x cost increase triggers insight
_LATENCY_DEGRADATION_MS = 5000   # p99 > 5s triggers insight
_MIN_CALLS_FOR_ANALYSIS = 5      # Need at least 5 calls to analyze


class LLMLearningBridge:
    """Bridges LLM observability data to Kait's cognitive learner."""

    def __init__(self) -> None:
        self._last_cost_usd = 0.0
        self._last_run = 0.0
        self._min_interval_s = 60.0  # Don't run more than once per minute

    def analyze_and_learn(self) -> List[Dict[str, Any]]:
        """Analyze recent LLM usage and generate learning insights.

        Returns a list of insight dicts that were fed to the cognitive learner.
        """
        now = time.time()
        if now - self._last_run < self._min_interval_s:
            return []
        self._last_run = now

        try:
            from lib.llm_observability import get_observer
            observer = get_observer()
            if not observer.enabled:
                return []
        except Exception:
            return []

        insights: List[Dict[str, Any]] = []

        # Analyze 5-minute window
        summary = observer.get_summary(window_s=300)
        provider_stats = observer.get_provider_stats(window_s=300)

        if summary["total_calls"] < _MIN_CALLS_FOR_ANALYSIS:
            return []

        # Pattern 1: High error rate
        if summary["error_rate"] > _HIGH_ERROR_RATE:
            insight = {
                "insight_type": "failure",
                "confidence": min(1.0, summary["error_rate"]),
                "evidence": (
                    f"LLM error rate at {summary['error_rate']:.0%} "
                    f"({summary['error_count']}/{summary['total_calls']} calls) "
                    f"in last 5 minutes"
                ),
                "action": "Check provider health. Consider switching default provider.",
                "usage_context": "llm_infrastructure",
            }
            insights.append(insight)

        # Pattern 2: Provider-specific issues
        for provider, stats in provider_stats.items():
            if stats["calls"] < 3:
                continue
            if stats["error_rate"] > _HIGH_ERROR_RATE:
                insight = {
                    "insight_type": "failure",
                    "confidence": min(1.0, stats["error_rate"]),
                    "evidence": (
                        f"Provider '{provider}' has {stats['error_rate']:.0%} error rate "
                        f"({stats['errors']}/{stats['calls']} calls)"
                    ),
                    "action": f"Circuit breaker should handle {provider}. Monitor for recovery.",
                    "usage_context": "llm_infrastructure",
                }
                insights.append(insight)

        # Pattern 3: Latency degradation
        if summary["p99_latency_ms"] > _LATENCY_DEGRADATION_MS:
            insight = {
                "insight_type": "pattern",
                "confidence": 0.7,
                "evidence": (
                    f"LLM p99 latency at {summary['p99_latency_ms']:.0f}ms "
                    f"(threshold: {_LATENCY_DEGRADATION_MS}ms)"
                ),
                "action": "Consider using faster models or reducing max_tokens.",
                "usage_context": "llm_infrastructure",
            }
            insights.append(insight)

        # Pattern 4: Cost spike
        current_cost = summary["total_cost_usd"]
        if (
            self._last_cost_usd > 0
            and current_cost > self._last_cost_usd * _COST_SPIKE_MULTIPLIER
            and current_cost > 0.01  # Ignore negligible amounts
        ):
            insight = {
                "insight_type": "pattern",
                "confidence": 0.6,
                "evidence": (
                    f"LLM cost spike: ${current_cost:.4f} vs previous ${self._last_cost_usd:.4f} "
                    f"({current_cost / self._last_cost_usd:.1f}x increase)"
                ),
                "action": "Review routing decisions. Cloud-heavy usage detected.",
                "usage_context": "llm_infrastructure",
            }
            insights.append(insight)
        self._last_cost_usd = current_cost

        # Feed insights to cognitive learner
        if insights:
            self._feed_to_learner(insights)
            log_debug(_LOG_TAG, f"Generated {len(insights)} LLM insights", None)

        return insights

    def _feed_to_learner(self, insights: List[Dict[str, Any]]) -> None:
        """Feed insights into Kait's cognitive learner."""
        try:
            from lib.cognitive_learner import get_cognitive_learner
            learner = get_cognitive_learner()
            for insight in insights:
                learner.record_insight(
                    category="llm_infrastructure",
                    statement=insight["evidence"],
                    confidence=insight.get("confidence", 0.5),
                    source="llm_learning_bridge",
                    metadata={
                        "type": insight["insight_type"],
                        "action": insight.get("action", ""),
                        "context": insight.get("usage_context", ""),
                    },
                )
        except Exception as exc:
            log_debug(_LOG_TAG, "Failed to feed insights to cognitive learner", exc)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_bridge_instance: Optional[LLMLearningBridge] = None


def get_llm_learning_bridge() -> LLMLearningBridge:
    """Return the shared LLMLearningBridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = LLMLearningBridge()
    return _bridge_instance
