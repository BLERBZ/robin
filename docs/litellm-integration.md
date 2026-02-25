# LiteLLM Integration Guide

LiteLLM provides a unified OpenAI-compatible API proxy that gives Kait access to 100+ LLM providers with built-in caching, cost tracking, and automatic failover.

## Architecture

```
Kait Sidekick
  -> LLMGateway (llm_gateway.py)
     -> LiteLLM Proxy (:4000)
        -> Anthropic API (Claude)
        -> OpenAI API (GPT-4o)
        -> [any other configured provider]
```

When `KAIT_LITELLM_ENABLED=false` (default), Kait uses direct bridges (`claude_bridge.py`, `openai_bridge.py`).

## Setup

### 1. Install LiteLLM

```bash
bash scripts/install_litellm.sh
```

This installs `litellm[proxy]` via pip.

### 2. Configure Models

Edit `config/litellm_config.yaml`:

```yaml
model_list:
  - model_name: claude-default
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: openai-default
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
```

### 3. Enable in Kait

Add to your `.env`:

```
KAIT_LITELLM_ENABLED=true
KAIT_LITELLM_PORT=4000
KAIT_LITELLM_MASTER_KEY=your-optional-key
```

### 4. Start

LiteLLM is managed automatically by Kait's service control when enabled. To start manually:

```bash
python -m litellm --config config/litellm_config.yaml --port 4000
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAIT_LITELLM_ENABLED` | `false` | Enable LiteLLM proxy |
| `KAIT_LITELLM_PORT` | `4000` | LiteLLM proxy port |
| `KAIT_LITELLM_MASTER_KEY` | (none) | Optional auth key |
| `KAIT_LITELLM_CLAUDE_MODEL` | `claude-default` | Model alias for Claude |
| `KAIT_LITELLM_OPENAI_MODEL` | `openai-default` | Model alias for OpenAI |

## Model Aliases

Model aliases map Kait's internal names to specific provider models:

| Alias | Default Model |
|-------|--------------|
| `claude-default` | `anthropic/claude-sonnet-4-20250514` |
| `claude-fast` | `anthropic/claude-haiku-4-5-20251001` |
| `claude-strong` | `anthropic/claude-opus-4-6` |
| `openai-default` | `openai/gpt-4o` |
| `openai-fast` | `openai/gpt-4o-mini` |

## Adding Providers

To add a new provider (e.g., Google Gemini), add to `litellm_config.yaml`:

```yaml
  - model_name: gemini-default
    litellm_params:
      model: gemini/gemini-2.0-flash
      api_key: os.environ/GOOGLE_API_KEY
```

## Caching

LiteLLM caches responses locally with a 300-second TTL. Identical requests within the cache window are served instantly at zero cost.

## Cost Tracking

LiteLLM tracks per-call costs. Kait's `LLMCostTracker` (`lib/sidekick/llm_cost_tracker.py`) aggregates this into a local SQLite database at `~/.kait/llm_costs.db`.

## Troubleshooting

- **LiteLLM not starting**: Check `~/.kait/logs/litellm.log`
- **401 errors**: Verify `KAIT_LITELLM_MASTER_KEY` matches the proxy config
- **429 rate limits**: LiteLLM retries automatically (2 retries configured)
- **Fallback to direct bridges**: Set `KAIT_LITELLM_ENABLED=false`; direct `claude_bridge.py` / `openai_bridge.py` remain functional
