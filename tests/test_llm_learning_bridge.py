"""Tests for the LLM Learning Bridge."""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


class TestLLMLearningBridge:
    def _make_bridge(self):
        from lib.llm_learning_bridge import LLMLearningBridge
        b = LLMLearningBridge()
        b._min_interval_s = 0  # disable throttle for tests
        return b

    def test_generates_high_error_rate_insight(self):
        bridge = self._make_bridge()
        mock_observer = MagicMock()
        mock_observer.enabled = True
        mock_observer.get_summary.return_value = {
            "total_calls": 10,
            "error_rate": 0.4,
            "error_count": 4,
            "p99_latency_ms": 1000,
            "total_cost_usd": 0.001,
        }
        mock_observer.get_provider_stats.return_value = {}

        with patch("lib.llm_learning_bridge.get_observer", return_value=mock_observer), \
             patch.object(bridge, "_feed_to_learner"):
            insights = bridge.analyze_and_learn()
            assert len(insights) >= 1
            assert insights[0]["insight_type"] == "failure"

    def test_generates_latency_insight(self):
        bridge = self._make_bridge()
        mock_observer = MagicMock()
        mock_observer.enabled = True
        mock_observer.get_summary.return_value = {
            "total_calls": 10,
            "error_rate": 0.0,
            "error_count": 0,
            "p99_latency_ms": 8000,
            "total_cost_usd": 0.001,
        }
        mock_observer.get_provider_stats.return_value = {}

        with patch("lib.llm_learning_bridge.get_observer", return_value=mock_observer), \
             patch.object(bridge, "_feed_to_learner"):
            insights = bridge.analyze_and_learn()
            assert any(i["insight_type"] == "pattern" for i in insights)

    def test_skips_when_insufficient_calls(self):
        bridge = self._make_bridge()
        mock_observer = MagicMock()
        mock_observer.enabled = True
        mock_observer.get_summary.return_value = {
            "total_calls": 2,
            "error_rate": 0.0,
            "error_count": 0,
            "p99_latency_ms": 100,
            "total_cost_usd": 0.0,
        }
        mock_observer.get_provider_stats.return_value = {}

        with patch("lib.llm_learning_bridge.get_observer", return_value=mock_observer):
            insights = bridge.analyze_and_learn()
            assert insights == []

    def test_skips_when_observer_disabled(self):
        bridge = self._make_bridge()
        mock_observer = MagicMock()
        mock_observer.enabled = False

        with patch("lib.llm_learning_bridge.get_observer", return_value=mock_observer):
            insights = bridge.analyze_and_learn()
            assert insights == []
