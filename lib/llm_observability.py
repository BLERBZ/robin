"""LLM call observability for Kait Intelligence.

Records every LLM call with latency, token counts, errors, and estimated cost.
Stores metrics in an in-memory ring buffer and a rotating JSONL file.
Exposes aggregation methods for dashboards and health monitoring.

Usage:
    from lib.llm_observability import get_observer, observed
    observer = get_observer()

    # Decorator usage (preferred):
    @observed("ollama")
    def generate(prompt, **kw):
        ...

    # Manual usage:
    observer.record(LLMCallRecord(...))

    # Query:
    summary = observer.get_summary(window_s=300)
    stats = observer.get_provider_stats()

Environment variables:
    KAIT_LLM_OBS_ENABLED  - Enable observability (default: true)
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from lib.diagnostics import log_debug

_LOG_TAG = "llm_obs"
_ENABLED_VALUES = {"1", "true", "yes", "on", ""}
_RING_BUFFER_SIZE = 1000
_JSONL_MAX_BYTES = int(os.environ.get("KAIT_LLM_OBS_JSONL_MAX_BYTES", "10485760"))  # 10 MB
_JSONL_BACKUPS = int(os.environ.get("KAIT_LLM_OBS_JSONL_BACKUPS", "3"))


def _obs_enabled() -> bool:
    raw = os.environ.get("KAIT_LLM_OBS_ENABLED", "true").strip().lower()
    return raw in _ENABLED_VALUES


# ---------------------------------------------------------------------------
# Cost table (USD per 1M tokens)
# ---------------------------------------------------------------------------

_COST_PER_1M_INPUT: Dict[str, float] = {
    # Claude models
    "claude-opus-4-6": 15.0,
    "claude-sonnet-4-6": 3.0,
    "claude-sonnet-4-20250514": 3.0,
    "claude-haiku-4-5-20251001": 0.80,
    # OpenAI models
    "gpt-4o": 2.50,
    "gpt-4o-mini": 0.15,
    "gpt-4-turbo": 10.0,
    "gpt-4-1106-preview": 10.0,
    "gpt-3.5-turbo": 0.50,
    # Local models (free)
    "ollama": 0.0,
}

_COST_PER_1M_OUTPUT: Dict[str, float] = {
    "claude-opus-4-6": 75.0,
    "claude-sonnet-4-6": 15.0,
    "claude-sonnet-4-20250514": 15.0,
    "claude-haiku-4-5-20251001": 4.0,
    "gpt-4o": 10.0,
    "gpt-4o-mini": 0.60,
    "gpt-4-turbo": 30.0,
    "gpt-4-1106-preview": 30.0,
    "gpt-3.5-turbo": 1.50,
    "ollama": 0.0,
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a call. Returns 0.0 for unknown/local models."""
    model_lower = model.lower() if model else ""
    # Check exact match first, then prefix match
    in_rate = _COST_PER_1M_INPUT.get(model_lower, 0.0)
    out_rate = _COST_PER_1M_OUTPUT.get(model_lower, 0.0)
    if in_rate == 0.0 and out_rate == 0.0:
        # Try prefix matching for versioned model names
        for key in _COST_PER_1M_INPUT:
            if model_lower.startswith(key):
                in_rate = _COST_PER_1M_INPUT[key]
                out_rate = _COST_PER_1M_OUTPUT.get(key, 0.0)
                break
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


# ---------------------------------------------------------------------------
# LLMCallRecord
# ---------------------------------------------------------------------------

@dataclass
class LLMCallRecord:
    """Record of a single LLM call."""
    timestamp: float = field(default_factory=time.time)
    provider: str = ""          # "ollama", "claude", "openai", "litellm"
    model: str = ""
    method: str = ""            # "chat", "chat_stream", "generate", "embed"
    caller: str = ""            # calling module/function
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    success: bool = True
    error: str = ""
    error_type: str = ""        # "timeout", "rate_limit", "auth", "connection", "api"
    streaming: bool = False

    def __post_init__(self) -> None:
        if self.total_tokens == 0 and (self.input_tokens or self.output_tokens):
            self.total_tokens = self.input_tokens + self.output_tokens
        if self.estimated_cost_usd == 0.0 and self.model:
            self.estimated_cost_usd = estimate_cost(
                self.model, self.input_tokens, self.output_tokens,
            )


# ---------------------------------------------------------------------------
# JSONL persistence
# ---------------------------------------------------------------------------

def _jsonl_path() -> Path:
    return Path.home() / ".kait" / "logs" / "llm_calls.jsonl"


def _rotate_jsonl(path: Path) -> None:
    """Rotate JSONL file if it exceeds max size."""
    if _JSONL_MAX_BYTES <= 0 or _JSONL_BACKUPS <= 0:
        return
    try:
        if not path.exists() or path.stat().st_size < _JSONL_MAX_BYTES:
            return
    except Exception:
        return
    try:
        for i in range(_JSONL_BACKUPS - 1, 0, -1):
            src = path.with_name(f"{path.name}.{i}")
            dst = path.with_name(f"{path.name}.{i + 1}")
            if src.exists():
                if dst.exists():
                    dst.unlink(missing_ok=True)
                src.replace(dst)
        first = path.with_name(f"{path.name}.1")
        if first.exists():
            first.unlink(missing_ok=True)
        path.replace(first)
    except Exception:
        pass


def _append_jsonl(record: LLMCallRecord) -> None:
    """Append a record to the JSONL file."""
    path = _jsonl_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_jsonl(path)
        line = json.dumps(asdict(record), ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# LLMObserver singleton
# ---------------------------------------------------------------------------

class LLMObserver:
    """Central LLM call metrics collector.

    Thread-safe. Maintains an in-memory ring buffer of recent records
    and writes all records to a rotating JSONL file for persistence.
    """

    def __init__(self) -> None:
        self._buffer: Deque[LLMCallRecord] = deque(maxlen=_RING_BUFFER_SIZE)
        self._lock = threading.Lock()
        self._enabled = _obs_enabled()
        self._total_calls = 0
        self._total_errors = 0
        self._total_cost_usd = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(self, rec: LLMCallRecord) -> None:
        """Record an LLM call. Thread-safe."""
        if not self._enabled:
            return
        with self._lock:
            self._buffer.append(rec)
            self._total_calls += 1
            self._total_cost_usd += rec.estimated_cost_usd
            if not rec.success:
                self._total_errors += 1
        # Write to JSONL outside the lock
        _append_jsonl(rec)

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent records as dicts."""
        with self._lock:
            records = list(self._buffer)
        return [asdict(r) for r in records[-limit:]]

    def get_summary(self, window_s: float = 300) -> Dict[str, Any]:
        """Get summary statistics for the given time window.

        Args:
            window_s: Time window in seconds (default: 5 minutes).

        Returns dict with total_calls, error_count, error_rate, avg_latency_ms,
        p50_latency_ms, p99_latency_ms, total_tokens, total_cost_usd.
        """
        cutoff = time.time() - window_s
        with self._lock:
            records = [r for r in self._buffer if r.timestamp >= cutoff]

        if not records:
            return {
                "window_s": window_s,
                "total_calls": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            }

        latencies = sorted(r.latency_ms for r in records)
        errors = sum(1 for r in records if not r.success)
        total_tokens = sum(r.total_tokens for r in records)
        total_cost = sum(r.estimated_cost_usd for r in records)

        return {
            "window_s": window_s,
            "total_calls": len(records),
            "error_count": errors,
            "error_rate": errors / len(records) if records else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies),
            "p50_latency_ms": _percentile(latencies, 50),
            "p99_latency_ms": _percentile(latencies, 99),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
        }

    def get_provider_stats(self, window_s: float = 300) -> Dict[str, Dict[str, Any]]:
        """Get per-provider statistics for the given time window."""
        cutoff = time.time() - window_s
        with self._lock:
            records = [r for r in self._buffer if r.timestamp >= cutoff]

        providers: Dict[str, List[LLMCallRecord]] = {}
        for r in records:
            providers.setdefault(r.provider, []).append(r)

        result: Dict[str, Dict[str, Any]] = {}
        for provider, recs in providers.items():
            latencies = sorted(r.latency_ms for r in recs)
            errors = sum(1 for r in recs if not r.success)
            result[provider] = {
                "calls": len(recs),
                "errors": errors,
                "error_rate": errors / len(recs) if recs else 0.0,
                "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
                "p50_latency_ms": round(_percentile(latencies, 50), 1),
                "p99_latency_ms": round(_percentile(latencies, 99), 1),
                "total_tokens": sum(r.total_tokens for r in recs),
                "total_cost_usd": round(sum(r.estimated_cost_usd for r in recs), 6),
                "models": list({r.model for r in recs if r.model}),
            }
        return result

    def get_error_rate(self, provider: str, window_s: float = 300) -> float:
        """Get error rate for a specific provider over a time window."""
        cutoff = time.time() - window_s
        with self._lock:
            records = [
                r for r in self._buffer
                if r.timestamp >= cutoff and r.provider == provider
            ]
        if not records:
            return 0.0
        return sum(1 for r in records if not r.success) / len(records)

    def get_p50_latency(self, provider: Optional[str] = None, window_s: float = 300) -> float:
        """Get p50 latency in ms, optionally filtered by provider."""
        return self._get_latency_percentile(50, provider, window_s)

    def get_p99_latency(self, provider: Optional[str] = None, window_s: float = 300) -> float:
        """Get p99 latency in ms, optionally filtered by provider."""
        return self._get_latency_percentile(99, provider, window_s)

    def get_lifetime_stats(self) -> Dict[str, Any]:
        """Get lifetime (session) statistics."""
        with self._lock:
            return {
                "total_calls": self._total_calls,
                "total_errors": self._total_errors,
                "total_cost_usd": round(self._total_cost_usd, 6),
                "buffer_size": len(self._buffer),
                "buffer_capacity": _RING_BUFFER_SIZE,
            }

    def _get_latency_percentile(
        self, pct: float, provider: Optional[str], window_s: float,
    ) -> float:
        cutoff = time.time() - window_s
        with self._lock:
            records = [
                r for r in self._buffer
                if r.timestamp >= cutoff
                and r.success
                and (provider is None or r.provider == provider)
            ]
        if not records:
            return 0.0
        latencies = sorted(r.latency_ms for r in records)
        return _percentile(latencies, pct)


def _percentile(sorted_values: List[float], pct: float) -> float:
    """Calculate percentile from a sorted list of values."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    idx = (pct / 100.0) * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    frac = idx - lower
    return sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower])


# ---------------------------------------------------------------------------
# Decorator: @observed("provider")
# ---------------------------------------------------------------------------

def _detect_caller(depth: int = 3) -> str:
    """Inspect the call stack to identify the calling module/function."""
    try:
        frame = inspect.currentframe()
        for _ in range(depth):
            if frame is None:
                break
            frame = frame.f_back
        if frame is not None:
            module = frame.f_globals.get("__name__", "unknown")
            func = frame.f_code.co_name
            return f"{module}.{func}"
    except Exception:
        pass
    return "unknown"


def observed(provider: str) -> Callable:
    """Decorator that records LLM call metrics to the observer.

    Usage:
        @observed("ollama")
        def chat(self, messages, **kwargs):
            ...  # returns response text

    The decorated function's return value is passed through unchanged.
    On exception, the error is recorded and the exception is re-raised.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            observer = get_observer()
            if not observer.enabled:
                return func(*args, **kwargs)

            caller = _detect_caller(depth=2)
            method_name = func.__name__
            model = _extract_model(args, kwargs)
            is_streaming = "stream" in method_name.lower()
            start = time.monotonic()

            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.monotonic() - start) * 1000

                # Extract token counts from result if available
                input_tokens, output_tokens = _extract_tokens(result, provider)

                observer.record(LLMCallRecord(
                    provider=provider,
                    model=model,
                    method=method_name,
                    caller=caller,
                    latency_ms=round(elapsed_ms, 1),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    success=result is not None,
                    streaming=is_streaming,
                ))
                return result

            except Exception as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                error_type = _classify_error(exc)

                observer.record(LLMCallRecord(
                    provider=provider,
                    model=model,
                    method=method_name,
                    caller=caller,
                    latency_ms=round(elapsed_ms, 1),
                    success=False,
                    error=str(exc)[:200],
                    error_type=error_type,
                    streaming=is_streaming,
                ))
                raise
        return wrapper
    return decorator


def _extract_model(args: tuple, kwargs: dict) -> str:
    """Try to extract the model name from function arguments."""
    # Check kwargs first
    model = kwargs.get("model", "")
    if model:
        return str(model)
    # Check if first arg is a class instance with a _model or model attribute
    if args:
        obj = args[0]
        for attr in ("_model", "model", "_default_model"):
            val = getattr(obj, attr, None)
            if val and isinstance(val, str):
                return val
    return ""


def _extract_tokens(result: Any, provider: str) -> tuple[int, int]:
    """Try to extract token counts from the result.

    Returns (input_tokens, output_tokens). Estimates from text length
    if exact counts aren't available.
    """
    # For most of our bridges, the result is a string
    if isinstance(result, str):
        # Rough estimate: ~4 chars per token
        output_tokens = max(1, len(result) // 4)
        return 0, output_tokens
    if result is None:
        return 0, 0
    return 0, 0


def _classify_error(exc: Exception) -> str:
    """Classify an exception into an error type category."""
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    if "timeout" in exc_str or "timeout" in exc_type:
        return "timeout"
    if "429" in exc_str or "rate" in exc_str:
        return "rate_limit"
    if "401" in exc_str or "auth" in exc_str or "key" in exc_str:
        return "auth"
    if "connection" in exc_str or "connect" in exc_type or "urlopen" in exc_str:
        return "connection"
    return "api"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[LLMObserver] = None


def get_observer() -> LLMObserver:
    """Return the shared LLMObserver singleton. Thread-safe."""
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = LLMObserver()
            if _singleton_instance.enabled:
                log_debug(_LOG_TAG, "LLM observability enabled", None)
        return _singleton_instance
