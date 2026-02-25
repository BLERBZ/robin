"""Tests for LLM self-healing: watchdog LLM checks, auto-model-switch, recovery."""

from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


class TestAutoModelSwitch:
    """Test _try_smaller_model in OllamaClient."""

    def test_switch_to_smaller_model(self):
        from lib.sidekick.local_llm import OllamaClient
        client = OllamaClient(default_model="llama3.1:70b")
        client._cached_models = [
            {"name": "llama3.1:70b", "size": 70e9},
            {"name": "llama3.1:8b", "size": 8e9},
            {"name": "mistral", "size": 7e9},
        ]
        result = client._try_smaller_model()
        assert result == "llama3.1:8b"
        assert client._default_model == "llama3.1:8b"

    def test_no_smaller_model_available(self):
        from lib.sidekick.local_llm import OllamaClient
        client = OllamaClient(default_model="mistral")
        client._cached_models = [{"name": "mistral", "size": 7e9}]
        result = client._try_smaller_model()
        assert result is None

    def test_unknown_model_falls_back(self):
        from lib.sidekick.local_llm import OllamaClient
        client = OllamaClient(default_model="custom-model")
        client._cached_models = [
            {"name": "custom-model", "size": 100e9},
            {"name": "mistral", "size": 7e9},
        ]
        result = client._try_smaller_model()
        assert result == "mistral"


class TestCircuitBreakerRecovery:
    """Test circuit breaker state transitions for self-healing."""

    def test_breaker_opens_after_threshold(self):
        from lib.llm_circuit_breaker import LLMCircuitBreaker, CircuitState
        cb = LLMCircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_breaker_recovers_via_half_open(self):
        import time
        from lib.llm_circuit_breaker import LLMCircuitBreaker, CircuitState
        cb = LLMCircuitBreaker("test", failure_threshold=2, recovery_timeout_s=0.1, half_open_tests=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.allow_request()  # transitions to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        import time
        from lib.llm_circuit_breaker import LLMCircuitBreaker, CircuitState
        cb = LLMCircuitBreaker("test", failure_threshold=2, recovery_timeout_s=0.1, half_open_tests=2)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.allow_request()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
