# Kait LLM Architecture Reference

## Overview

Kait's LLM infrastructure is a continuously operating, self-healing, observable, and autonomously resilient system. It routes all LLM calls through a unified gateway with intelligent routing, circuit breakers, and observability.

## Topology

```
kait_ai_sidekick.py
  -> LLMGateway (lib/sidekick/llm_gateway.py)
     -> LLMRouter (lib/sidekick/llm_router.py)
        + Circuit Breakers (lib/llm_circuit_breaker.py)
        |
        -> local_llm.py --> Olla (:11435) --> [Ollama-A(:11434), ...]
        -> litellm_bridge.py --> LiteLLM (:4000) --> [Claude, OpenAI, ...]
        -> claude_bridge.py (legacy fallback)
        -> openai_bridge.py (legacy fallback)

  LLM Observability (lib/llm_observability.py)
     -> Pulse /api/llm (dashboard)
     -> LLM Learning Bridge -> cognitive_learner

  Circuit Breakers (per-provider)
     -> Watchdog LLM health checks
     -> Auto model switch (OllamaClient._try_smaller_model)
     -> Auto Ollama/Olla/LiteLLM restart
```

## Components

### LLM Gateway (`lib/sidekick/llm_gateway.py`)

Single entry point for all LLM calls. Manages provider chain resolution through the router and circuit breakers.

- `chat()` / `chat_stream()` / `embed()`
- Lazy-loaded clients for all providers
- Thread-safe singleton via `get_llm_gateway()`

### LLM Router (`lib/sidekick/llm_router.py`)

Scores query complexity via RouteLLM and routes to the appropriate provider.

- **Simple queries** (score < threshold) -> local Ollama
- **Complex queries** (score >= threshold) -> cloud provider
- **Dev/Build requests** (Kait/Robin) -> always cloud-first
- Circuit breaker overlay suppresses providers with open circuits

### Circuit Breakers (`lib/llm_circuit_breaker.py`)

Per-provider CLOSED/OPEN/HALF_OPEN state machine:

- **CLOSED**: All requests pass through
- **OPEN**: After N failures, all requests blocked for recovery_timeout_s
- **HALF_OPEN**: After timeout, allow test requests; success closes, failure reopens

State persisted to `~/.kait/llm_health_state.json`.

### LLM Observability (`lib/llm_observability.py`)

Records every LLM call with latency, tokens, cost, errors.

- In-memory ring buffer (1000 records) + rotating JSONL persistence
- `@observed("provider")` decorator for non-invasive instrumentation
- Time-windowed summaries, percentile latencies, provider breakdowns
- Exposed via Pulse `/api/llm` endpoint

### LLM Learning Bridge (`lib/llm_learning_bridge.py`)

Detects patterns in LLM usage and feeds insights to Kait's cognitive learner:

- High error rate detection
- Provider-specific failure tracking
- Latency degradation alerts
- Cost spike detection

### Cost Tracker (`lib/sidekick/llm_cost_tracker.py`)

Persists cost data to SQLite at `~/.kait/llm_costs.db`.

- Per-model and per-provider breakdowns
- Time-period summaries (1h, 24h, 7d, 30d)
- Automatic old record cleanup

## Provider Bridges

| Provider | Bridge | Proxy | Port |
|----------|--------|-------|------|
| Ollama (local) | `local_llm.py` | Olla (optional) | 11434 / 11435 |
| Claude | `claude_bridge.py` | LiteLLM (optional) | API / 4000 |
| OpenAI | `openai_bridge.py` | LiteLLM (optional) | API / 4000 |
| LiteLLM | `litellm_bridge.py` | -- | 4000 |

## Port Allocation

| Service | Port | Purpose |
|---------|------|---------|
| kaitd | 8787 | Core daemon |
| Pulse | 8765 | Dashboard & API |
| Mind | 8080 | Knowledge graph |
| Matrix | 8769 | Matrix integration |
| Ollama | 11434 | Local LLM (external) |
| Olla | 11435 | Ollama load balancer |
| LiteLLM | 4000 | Cloud LLM gateway |

## Configuration Reference

### Environment Variables

| Variable | Default | Phase | Description |
|----------|---------|-------|-------------|
| `KAIT_LLM_OBS_ENABLED` | `true` | 1 | Enable LLM call observability |
| `KAIT_CB_ENABLED` | `true` | 2 | Enable circuit breakers |
| `KAIT_CB_FAILURE_THRESHOLD` | `3` | 2 | Failures to open circuit |
| `KAIT_CB_RECOVERY_TIMEOUT_S` | `60` | 2 | Seconds before half-open probe |
| `KAIT_CB_HALF_OPEN_TESTS` | `2` | 2 | Successes to close from half-open |
| `KAIT_LLM_WATCHDOG_ENABLED` | `false` | 2 | Enable watchdog LLM health checks |
| `KAIT_OLLA_ENABLED` | `false` | 3 | Enable Olla proxy |
| `KAIT_OLLA_HOST` | `localhost` | 3 | Olla proxy host |
| `KAIT_OLLA_PORT` | `11435` | 3 | Olla proxy port |
| `KAIT_LITELLM_ENABLED` | `false` | 4 | Enable LiteLLM proxy |
| `KAIT_LITELLM_PORT` | `4000` | 4 | LiteLLM proxy port |
| `KAIT_LITELLM_MASTER_KEY` | (none) | 4 | LiteLLM auth key |

### Tuneables (`config/tuneables.json`)

```json
"llm_gateway": {
  "olla_enabled": false,
  "litellm_enabled": false,
  "local_timeout_s": 120,
  "cloud_timeout_s": 120,
  "max_retries": 2,
  "cost_alert_threshold_usd": 1.0
}
```

## Rollback

Each feature is gated behind environment variables defaulting to off/safe:

- **Observability**: Set `KAIT_LLM_OBS_ENABLED=false` (observer becomes no-op)
- **Circuit Breakers**: Set `KAIT_CB_ENABLED=false` (breakers default to CLOSED)
- **Olla**: Set `KAIT_OLLA_ENABLED=false` (traffic goes direct to Ollama)
- **LiteLLM**: Set `KAIT_LITELLM_ENABLED=false` (cloud calls use direct bridges)
- **LLM Watchdog**: Set `KAIT_LLM_WATCHDOG_ENABLED=false` (no LLM health checks)
- **Gateway**: Falls through to legacy provider switching in `kait_ai_sidekick.py`

## Troubleshooting

1. **All providers failing**: Check `~/.kait/llm_health_state.json` for circuit breaker states. Reset with `KAIT_CB_ENABLED=false`.
2. **High latency**: Check Pulse dashboard LLM Infrastructure card for p50/p99 metrics.
3. **Cost spike**: Review `~/.kait/llm_costs.db` or Pulse `/api/llm` cost summary.
4. **Ollama OOM**: `OllamaClient._try_smaller_model()` auto-downgrades. Check logs for "Switching to smaller model".
5. **LiteLLM 401**: Verify `KAIT_LITELLM_MASTER_KEY` matches the proxy's `general_settings.master_key`.
