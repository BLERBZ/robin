"""Tests for LLM observability module."""
import time
import pytest
from lib.llm_observability import (
    LLMCallRecord,
    LLMObserver,
    estimate_cost,
    _percentile,
    _classify_error,
)


class TestLLMCallRecord:
    def test_auto_total_tokens(self):
        rec = LLMCallRecord(input_tokens=100, output_tokens=50)
        assert rec.total_tokens == 150

    def test_auto_cost_estimation(self):
        rec = LLMCallRecord(model="gpt-4o", input_tokens=1000, output_tokens=500)
        assert rec.estimated_cost_usd > 0

    def test_local_model_zero_cost(self):
        rec = LLMCallRecord(model="ollama", input_tokens=1000, output_tokens=500)
        assert rec.estimated_cost_usd == 0.0

    def test_defaults(self):
        rec = LLMCallRecord()
        assert rec.success is True
        assert rec.provider == ""
        assert rec.error == ""


class TestEstimateCost:
    def test_known_model(self):
        cost = estimate_cost("gpt-4o", 1_000_000, 0)
        assert cost == 2.50

    def test_unknown_model_zero(self):
        cost = estimate_cost("unknown-model", 1000, 1000)
        assert cost == 0.0

    def test_ollama_free(self):
        assert estimate_cost("ollama", 100000, 100000) == 0.0


class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single(self):
        assert _percentile([42.0], 50) == 42.0

    def test_p50(self):
        values = sorted([10.0, 20.0, 30.0, 40.0, 50.0])
        assert _percentile(values, 50) == 30.0

    def test_p99(self):
        values = sorted(float(i) for i in range(100))
        p99 = _percentile(values, 99)
        assert p99 >= 98.0


class TestLLMObserver:
    def _make_observer(self):
        obs = LLMObserver()
        obs._enabled = True
        return obs

    def test_record_and_retrieve(self):
        obs = self._make_observer()
        rec = LLMCallRecord(provider="test", model="test-model", latency_ms=100)
        obs.record(rec)
        recent = obs.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0]["provider"] == "test"

    def test_ring_buffer_max_size(self):
        obs = self._make_observer()
        obs._buffer = __import__("collections").deque(maxlen=5)
        for i in range(10):
            obs.record(LLMCallRecord(provider=f"p{i}", latency_ms=float(i)))
        assert len(obs._buffer) == 5

    def test_get_summary_empty(self):
        obs = self._make_observer()
        summary = obs.get_summary(window_s=60)
        assert summary["total_calls"] == 0
        assert summary["error_rate"] == 0.0

    def test_get_summary_with_records(self):
        obs = self._make_observer()
        obs.record(LLMCallRecord(provider="ollama", latency_ms=100, success=True))
        obs.record(LLMCallRecord(provider="ollama", latency_ms=200, success=True))
        obs.record(LLMCallRecord(provider="claude", latency_ms=500, success=False, error="timeout"))
        summary = obs.get_summary(window_s=60)
        assert summary["total_calls"] == 3
        assert summary["error_count"] == 1

    def test_get_provider_stats(self):
        obs = self._make_observer()
        obs.record(LLMCallRecord(provider="ollama", latency_ms=50))
        obs.record(LLMCallRecord(provider="claude", latency_ms=200))
        stats = obs.get_provider_stats(window_s=60)
        assert "ollama" in stats
        assert "claude" in stats
        assert stats["ollama"]["calls"] == 1

    def test_get_error_rate(self):
        obs = self._make_observer()
        obs.record(LLMCallRecord(provider="test", success=True))
        obs.record(LLMCallRecord(provider="test", success=False, error="err"))
        rate = obs.get_error_rate("test", window_s=60)
        assert rate == 0.5

    def test_get_error_rate_no_records(self):
        obs = self._make_observer()
        assert obs.get_error_rate("nonexistent", window_s=60) == 0.0

    def test_time_window_filtering(self):
        obs = self._make_observer()
        old_rec = LLMCallRecord(provider="old", latency_ms=100)
        old_rec.timestamp = time.time() - 600  # 10 min ago
        obs.record(old_rec)
        obs.record(LLMCallRecord(provider="new", latency_ms=100))
        summary = obs.get_summary(window_s=300)  # 5 min window
        assert summary["total_calls"] == 1

    def test_lifetime_stats(self):
        obs = self._make_observer()
        obs.record(LLMCallRecord(provider="t", estimated_cost_usd=0.01))
        obs.record(LLMCallRecord(provider="t", estimated_cost_usd=0.02))
        lifetime = obs.get_lifetime_stats()
        assert lifetime["total_calls"] == 2
        assert lifetime["total_cost_usd"] == pytest.approx(0.03, abs=0.001)

    def test_disabled_observer_noop(self):
        obs = LLMObserver()
        obs._enabled = False
        obs.record(LLMCallRecord(provider="test"))
        assert len(obs._buffer) == 0


class TestClassifyError:
    def test_timeout(self):
        assert _classify_error(TimeoutError("timed out")) == "timeout"

    def test_rate_limit(self):
        assert _classify_error(Exception("429 rate limit")) == "rate_limit"

    def test_auth(self):
        assert _classify_error(Exception("401 unauthorized")) == "auth"

    def test_connection(self):
        assert _classify_error(ConnectionError("refused")) == "connection"

    def test_generic(self):
        assert _classify_error(Exception("something else")) == "api"
