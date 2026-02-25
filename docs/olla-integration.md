# Olla Integration Guide

Olla is a lightweight Go proxy that sits between Kait and one or more Ollama instances, providing load balancing, health monitoring, and automatic failover for local LLM inference.

## Architecture

```
Kait Sidekick
  -> OllamaClient (local_llm.py)
     -> Olla Proxy (:11435)
        -> Ollama-A (:11434)  [primary]
        -> Ollama-B (:11436)  [secondary, optional]
```

When `KAIT_OLLA_ENABLED=false` (default), Kait talks directly to Ollama at `:11434`.

## Setup

### 1. Install Olla

```bash
bash scripts/install_olla.sh
```

This downloads the Olla binary for your platform to `~/.kait/bin/olla`.

### 2. Configure

Edit `config/olla.yaml`:

```yaml
listen: ":11435"
backends:
  - name: primary
    url: "http://localhost:11434"
    priority: 1
strategy: priority
```

For multi-instance setups, add more backends:

```yaml
backends:
  - name: primary
    url: "http://localhost:11434"
    priority: 1
  - name: secondary
    url: "http://localhost:11436"
    priority: 2
```

### 3. Enable in Kait

Add to your `.env`:

```
KAIT_OLLA_ENABLED=true
KAIT_OLLA_HOST=localhost
KAIT_OLLA_PORT=11435
```

### 4. Start

Olla is managed automatically by Kait's service control and watchdog when enabled. To start manually:

```bash
~/.kait/bin/olla serve --config config/olla.yaml
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAIT_OLLA_ENABLED` | `false` | Enable Olla proxy routing |
| `KAIT_OLLA_HOST` | `localhost` | Olla proxy host |
| `KAIT_OLLA_PORT` | `11435` | Olla proxy port |
| `KAIT_OLLA_CONFIG` | `config/olla.yaml` | Path to Olla config |

## Health Monitoring

- Olla exposes `/healthz` for health checks
- The Kait watchdog checks Olla health when `KAIT_LLM_WATCHDOG_ENABLED=true`
- If Olla becomes unhealthy, the watchdog restarts it automatically

## Circuit Breaker Integration

Olla has its own built-in circuit breakers per backend. Additionally, Kait's circuit breaker for `ollama` covers the entire Olla->Ollama path.

## Troubleshooting

- **Olla not starting**: Check `~/.kait/logs/olla.log`
- **Connection refused**: Verify Ollama is running on the configured backend port
- **Slow responses**: Check if multiple models are loaded; Ollama may need more VRAM
- **Fallback to direct**: Set `KAIT_OLLA_ENABLED=false` to bypass Olla entirely
