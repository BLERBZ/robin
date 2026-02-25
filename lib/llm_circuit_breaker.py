"""Per-provider circuit breakers for LLM calls.

Implements a standard CLOSED / OPEN / HALF_OPEN state machine to prevent
cascading failures when an LLM provider is unhealthy.

Usage:
    from lib.llm_circuit_breaker import get_circuit_breaker_registry

    registry = get_circuit_breaker_registry()
    cb = registry.get("ollama")

    if cb.allow_request():
        try:
            result = call_provider(...)
            cb.record_success()
        except Exception:
            cb.record_failure()
    else:
        # Provider circuit is open — skip or use fallback
        ...

Environment variables:
    KAIT_CB_ENABLED            - Enable circuit breakers (default: true)
    KAIT_CB_FAILURE_THRESHOLD  - Failures before opening circuit (default: 3)
    KAIT_CB_RECOVERY_TIMEOUT_S - Seconds before trying half-open (default: 60)
    KAIT_CB_HALF_OPEN_TESTS    - Successes in half-open to close (default: 2)
"""

from __future__ import annotations

import enum
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from lib.diagnostics import log_debug

_COMPONENT = "circuit_breaker"
_ENABLED_VALUES = {"1", "true", "yes", "on"}
_STATE_FILE = Path.home() / ".kait" / "llm_health_state.json"


def _cb_enabled() -> bool:
    return os.environ.get("KAIT_CB_ENABLED", "true").lower().strip() in _ENABLED_VALUES


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ------------------------------------------------------------------
# State enum
# ------------------------------------------------------------------

class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ------------------------------------------------------------------
# Per-provider circuit breaker
# ------------------------------------------------------------------

class LLMCircuitBreaker:
    """State machine circuit breaker for a single LLM provider."""

    def __init__(
        self,
        provider: str,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 60.0,
        half_open_tests: int = 2,
    ) -> None:
        self._provider = provider
        self._failure_threshold = _env_int("KAIT_CB_FAILURE_THRESHOLD", failure_threshold)
        self._recovery_timeout_s = _env_float("KAIT_CB_RECOVERY_TIMEOUT_S", recovery_timeout_s)
        self._half_open_tests = _env_int("KAIT_CB_HALF_OPEN_TESTS", half_open_tests)

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_attempts = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    # -- public properties ------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def last_failure_time(self) -> Optional[float]:
        with self._lock:
            return self._last_failure_time

    # -- core API ---------------------------------------------------

    def allow_request(self) -> bool:
        """Return True if the circuit allows a request through."""
        if not _cb_enabled():
            return True

        with self._lock:
            if self._state is CircuitState.CLOSED:
                return True

            if self._state is CircuitState.OPEN:
                if self._last_failure_time is None:
                    # Shouldn't happen, but be safe.
                    self._transition(CircuitState.HALF_OPEN)
                    return True
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._recovery_timeout_s:
                    self._transition(CircuitState.HALF_OPEN)
                    return True
                return False

            # HALF_OPEN: allow up to half_open_tests requests
            if self._half_open_attempts < self._half_open_tests:
                self._half_open_attempts += 1
                return True
            return False

    def record_success(self) -> None:
        """Record a successful call."""
        if not _cb_enabled():
            return

        with self._lock:
            if self._state is CircuitState.CLOSED:
                self._failure_count = 0

            elif self._state is CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._half_open_tests:
                    self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call."""
        if not _cb_enabled():
            return

        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state is CircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._transition(CircuitState.OPEN)

            elif self._state is CircuitState.HALF_OPEN:
                # Any failure in half-open immediately reopens the circuit.
                self._transition(CircuitState.OPEN)

    def reset(self) -> None:
        """Force-reset the breaker to CLOSED."""
        with self._lock:
            self._transition(CircuitState.CLOSED)

    def to_dict(self) -> dict:
        """Serialize current state for persistence or API responses."""
        with self._lock:
            return {
                "provider": self._provider,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "half_open_attempts": self._half_open_attempts,
                "last_failure_time": self._last_failure_time,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout_s": self._recovery_timeout_s,
                "half_open_tests": self._half_open_tests,
            }

    # -- internal ---------------------------------------------------

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new state. Must be called with self._lock held."""
        old = self._state
        self._state = new_state

        if new_state is CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_attempts = 0

        elif new_state is CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_attempts = 0

        elif new_state is CircuitState.OPEN:
            self._success_count = 0
            self._half_open_attempts = 0

        log_debug(
            _COMPONENT,
            f"[{self._provider}] circuit {old.value} -> {new_state.value} "
            f"(failures={self._failure_count})",
        )


# ------------------------------------------------------------------
# Registry (singleton)
# ------------------------------------------------------------------

class CircuitBreakerRegistry:
    """Thread-safe registry of per-provider circuit breakers."""

    def __init__(self) -> None:
        self._breakers: Dict[str, LLMCircuitBreaker] = {}
        self._lock = threading.Lock()
        self.enabled = _cb_enabled()
        if self.enabled:
            self.load_state()
            log_debug(_COMPONENT, "Circuit breaker registry initialised")

    def get(self, provider: str) -> LLMCircuitBreaker:
        """Get or create a circuit breaker for *provider*."""
        with self._lock:
            cb = self._breakers.get(provider)
            if cb is None:
                cb = LLMCircuitBreaker(provider)
                self._breakers[provider] = cb
            return cb

    def get_all(self) -> Dict[str, LLMCircuitBreaker]:
        """Return a snapshot dict of all registered breakers."""
        with self._lock:
            return dict(self._breakers)

    def get_status(self) -> Dict[str, dict]:
        """Return serialised state of every breaker."""
        with self._lock:
            return {name: cb.to_dict() for name, cb in self._breakers.items()}

    def save_state(self) -> None:
        """Persist breaker states to disk."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = self.get_status()
            _STATE_FILE.write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
            log_debug(_COMPONENT, f"Saved circuit breaker state ({len(payload)} providers)")
        except Exception as exc:
            log_debug(_COMPONENT, f"Failed to save state: {exc}", exc=exc)

    def load_state(self) -> None:
        """Restore breaker states from disk."""
        if not _STATE_FILE.exists():
            return
        try:
            raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            with self._lock:
                for provider, data in raw.items():
                    cb = LLMCircuitBreaker(provider)
                    state_str = data.get("state", "closed")
                    try:
                        cb._state = CircuitState(state_str)
                    except ValueError:
                        cb._state = CircuitState.CLOSED
                    cb._failure_count = data.get("failure_count", 0)
                    cb._success_count = data.get("success_count", 0)
                    cb._half_open_attempts = data.get("half_open_attempts", 0)
                    # last_failure_time from disk is wall-clock; convert concept
                    # We can't restore monotonic timestamps across restarts so
                    # treat persisted OPEN circuits as ready to probe.
                    if cb._state is CircuitState.OPEN:
                        cb._last_failure_time = time.monotonic() - cb._recovery_timeout_s
                    else:
                        cb._last_failure_time = data.get("last_failure_time")
                    self._breakers[provider] = cb
            log_debug(_COMPONENT, f"Loaded circuit breaker state ({len(raw)} providers)")
        except Exception as exc:
            log_debug(_COMPONENT, f"Failed to load state: {exc}", exc=exc)


# ------------------------------------------------------------------
# Singleton access
# ------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Return the global CircuitBreakerRegistry singleton."""
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = CircuitBreakerRegistry()
        return _singleton_instance
