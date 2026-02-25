"""Tests for LLM circuit breaker module."""
import time
import pytest
import lib.llm_circuit_breaker as cb_mod
from lib.llm_circuit_breaker import (
    CircuitState,
    LLMCircuitBreaker,
    CircuitBreakerRegistry,
)


class TestCircuitState:
    def test_initial_state_closed(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_stays_closed_below_threshold(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_success_resets_failure_count(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_open_blocks_requests(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.1, half_open_tests=2)
        cb.record_failure()
        time.sleep(0.15)
        cb.allow_request()  # transitions to HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.1)
        cb.record_failure()
        time.sleep(0.15)
        cb.allow_request()  # transitions to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_reset(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_to_dict(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test_provider")
        d = cb.to_dict()
        assert d["provider"] == "test_provider"
        assert d["state"] == "closed"
        assert "failure_count" in d

    def test_allow_request_closed(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        cb = LLMCircuitBreaker("test")
        assert cb.allow_request() is True


class TestCircuitBreakerRegistry:
    def test_get_creates_new(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "false")
        reg = CircuitBreakerRegistry()
        cb = reg.get("ollama")
        assert cb.provider == "ollama"
        assert cb.state == CircuitState.CLOSED

    def test_get_returns_same_instance(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "false")
        reg = CircuitBreakerRegistry()
        cb1 = reg.get("ollama")
        cb2 = reg.get("ollama")
        assert cb1 is cb2

    def test_get_all(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "false")
        reg = CircuitBreakerRegistry()
        reg.get("ollama")
        reg.get("claude")
        all_breakers = reg.get_all()
        assert "ollama" in all_breakers
        assert "claude" in all_breakers

    def test_get_status(self, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "false")
        reg = CircuitBreakerRegistry()
        reg.get("ollama")
        status = reg.get_status()
        assert "ollama" in status
        assert status["ollama"]["state"] == "closed"

    def test_save_and_load_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KAIT_CB_ENABLED", "true")
        state_file = tmp_path / "llm_health_state.json"
        monkeypatch.setattr(cb_mod, "_STATE_FILE", state_file)

        reg = CircuitBreakerRegistry()
        cb = reg.get("test")
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()  # Opens the circuit
        reg.save_state()
        assert state_file.exists()

        # Create new registry and load
        reg2 = CircuitBreakerRegistry()
        cb2 = reg2.get("test")
        assert cb2.state == CircuitState.OPEN
