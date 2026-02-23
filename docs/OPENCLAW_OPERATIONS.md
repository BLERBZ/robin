# OpenClaw Operations â€” Running Kait the Seer

Status: `canonical`
Scope: runtime startup, data flow, service health, troubleshooting

## Session Startup Checklist

Every time you start a new OpenClaw session, do this:

Operating policy reference:
- `docs/KAIT_LIGHTWEIGHT_OPERATING_MODE.md`

### 1. Start Kait Services

```powershell
$repo = "<REPO_ROOT>"
$env:KAIT_EMBEDDINGS = "0"

# Core services
$kaitd = Start-Process python -ArgumentList "$repo\kaitd.py" -WorkingDirectory $repo -WindowStyle Hidden -PassThru
$bridge = Start-Process python -ArgumentList "$repo\bridge_worker.py" -WorkingDirectory $repo -WindowStyle Hidden -PassThru
$tailer = Start-Process python -ArgumentList "$repo\adapters\openclaw_tailer.py","--include-subagents" -WorkingDirectory $repo -WindowStyle Hidden -PassThru

# Dashboard
$pulse = Start-Process python -ArgumentList "-m","uvicorn","app:app","--host","127.0.0.1","--port","8765" -WorkingDirectory "<KAIT_PULSE_DIR>" -WindowStyle Hidden -PassThru

Write-Host "kaitd=$($kaitd.Id) bridge=$($bridge.Id) tailer=$($tailer.Id) pulse=$($pulse.Id)"
```

### 2. Verify Everything is Running

```powershell
# Quick health check
Invoke-RestMethod http://127.0.0.1:8787/health                    # kaitd
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8765/       # pulse
Get-Process python | Select-Object Id,@{N='MB';E={[math]::Round($_.WorkingSet64/1MB)}}
```

### 2.1 Verify Advisory Delivery State

```powershell
# Pulse status
$pulse = Invoke-RestMethod http://127.0.0.1:8765/api/status
$pulse.advisory.delivery_badge

# Pulse advisory board
$adv = Invoke-RestMethod http://127.0.0.1:8765/api/advisory
$adv.delivery_badge
```

Target interpretation:
- `live` or `fallback`: acceptable runtime state
- `blocked`: investigate advisory engine/synth/emitter status
- `stale`: advisory is not updating; inspect recent `~/.kait/advisory_engine.jsonl` events

### 3. Verify Claude CLI Auth

```powershell
claude -p "say OK"
```

If it says "Invalid API key", run `claude` and type `/login`.

---

## How Kait Works Inside OpenClaw

### Data Flow

```
You type a message
        â”‚
        â–¼
OpenClaw processes it (tools, responses, etc.)
        â”‚
        â–¼
Session JSONL written to ~/.openclaw/agents/main/sessions/
        â”‚
        â–¼
openclaw_tailer reads new events, sends to kaitd (:8787)
        â”‚
        â–¼
kaitd queues events in ~/.kait/queue/events.jsonl
        â”‚
        â–¼
bridge_worker processes queue every ~30 seconds:
  â”œâ”€ Pattern detection (coding patterns, errors, workflows)
  â”œâ”€ Chip system (domain-specific insights across 7+ domains)
  â”œâ”€ Cognitive learner (builds validated knowledge base)
  â”œâ”€ Feedback ingestion (reads agent self-reports)
  â”œâ”€ Prediction/validation loop
  â”œâ”€ Context sync (writes to all IDE targets)
  â”œâ”€ Auto-tuner (optimizes its own parameters)
  â””â”€ LLM Advisory (calls Claude when enough patterns found)
        â”‚
        â–¼
Outputs written to OpenClaw workspace:
  â”œâ”€ KAIT_CONTEXT.md    (curated insights)
  â”œâ”€ KAIT_ADVISORY.md   (Claude-generated recommendations)
  â””â”€ KAIT_NOTIFICATIONS.md (recent events)
        â”‚
        â–¼
Cron job (every 30 min) tells agent to read + act on advisories
        â”‚
        â–¼
Agent evaluates, acts, reports feedback to kait_reports/
        â”‚
        â–¼
bridge_worker ingests feedback â†’ updates confidence â†’ loop repeats
```

### The Self-Evolution Loop

```
         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
         â”‚                                              â”‚
         â–¼                                              â”‚
    Conversation â”€â”€â†’ Capture â”€â”€â†’ Patterns â”€â”€â†’ Claude   â”‚
                                Advisory               â”‚
                                    â”‚                   â”‚
                                    â–¼                   â”‚
                             Agent evaluates            â”‚
                              â”œâ”€ Act â†’ Report outcome â”€â”€â”˜
                              â””â”€ Skip â†’ Report reason â”€â”€â”˜
```

The `advice_action_rate` metric tracks what % of advice gets acted on. Target: >50%.

---

## Services Reference

| Service | Port | Process | Critical Notes |
|---------|------|---------|----------------|
| kaitd | 8787 | `python kaitd.py` | HTTP event ingestion endpoint |
| bridge_worker | â€” | `python bridge_worker.py` | **MUST set `KAIT_EMBEDDINGS=0`** or 8GB+ RAM leak |
| openclaw_tailer | â€” | `python adapters/openclaw_tailer.py --include-subagents` | Tails session JSONL files |
| Kait Pulse | 8765 | `python -m uvicorn app:app` | **MUST use `-m uvicorn`** not `python app.py` |

### RAM Budget

| Service | Expected | Alert |
|---------|----------|-------|
| kaitd | 30-40MB | >100MB |
| bridge_worker | 60-80MB | >200MB |
| tailer | 20-30MB | >50MB |
| Kait Pulse | 120-170MB | >300MB |
| **Total** | **~350MB** | **>500MB** |

---

## Key Files

### OpenClaw Workspace (`~/.openclaw/workspace/`)

| File | Purpose | Who writes | Who reads |
|------|---------|-----------|-----------|
| `KAIT_CONTEXT.md` | Curated insights | bridge_worker | Agent (cron) |
| `KAIT_ADVISORY.md` | LLM recommendations | bridge_worker | Agent (cron) |
| `KAIT_NOTIFICATIONS.md` | Recent events | bridge_worker | Agent (cron) |
| `kait_reports/*.json` | Agent feedback | Agent | bridge_worker |
| `MEMORY.md` | Long-term memory | Agent | Agent |
| `HEARTBEAT.md` | Heartbeat tasks | Agent | Agent |

### Kait Data (`~/.kait/`)

| File | Purpose |
|------|---------|
| `queue/events.jsonl` | Event queue (FIFO) |
| `cognitive_insights.json` | Validated knowledge base |
| `bridge_worker_heartbeat.json` | Bridge cycle status |
| `feedback_state.json` | Feedback loop metrics |
| `feedback_log.jsonl` | All feedback history |
| `llm_calls.json` | Rate limit tracking (30/hr) |
| `llm_advisory.md` | Latest advisory (backup) |
| `eidos_distillations.jsonl` | Self-model updates |
| `eidos_llm_counter.txt` | Distillation cycle counter |
| `chip_insights/*.jsonl` | Per-chip observations (2MB rotation) |

---

## Cron Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| `kait-context-refresh` | Every 30 min | Checkpoint-style reminder: read Kait files, act only on relevant items, log acted/skipped outcomes |

## Config Lifecycle (Hot-apply vs Restart)

Use this to avoid guessing whether a change is live.

| Config area | Hot-apply | Operator action |
|-------------|-----------|-----------------|
| Advisory runtime (`advisory_engine`, `advisory_gate`, `advisory_packet_store`, `advisory_prefetch`) | Yes | Apply and verify logs/status |
| Synthesizer (`synthesizer` section) | Yes | Apply and verify `get_synth_status` |
| Env vars (`KAIT_*`) | No | Restart affected process |
| Legacy/import-time configs (many modules) | Usually no | Restart affected process |

Verification loop after any config change:
1. Check service health (`kaitd`, `bridge_worker` heartbeat, Mind health)
2. Confirm behavior in a real active cycle (not synthetic-only)
3. Log result in `docs/OPENCLAW_RESEARCH_AND_UPDATES.md`

---

## Troubleshooting

### bridge_worker using too much RAM
- Check `KAIT_EMBEDDINGS` is `0`
- Check for duplicate bridge_worker processes: `Get-WmiObject Win32_Process -Filter "Name='python.exe'" | Where-Object {$_.CommandLine -like "*bridge_worker*"}`
- Kill all and restart one

### Pulse not responding
- Check it's running: `netstat -ano | findstr 8765`
- If port in use, kill old process first
- Always use `-m uvicorn app:app`, never `python app.py`

### Advisory delivery badge is blocked or stale
- Check Pulse advisory status: `Invoke-RestMethod http://127.0.0.1:8765/api/advisory | Select-Object -ExpandProperty delivery_badge`
- Check recent engine events: `Get-Content "$env:USERPROFILE\.kait\advisory_engine.jsonl" -Tail 20`
- If no fresh events, trigger normal tool activity and recheck badge age/state.

### LLM advisory not generating
- Check Claude auth: `claude -p "say OK"` (needs PTY)
- Check rate limit: `Get-Content ~/.kait/llm_calls.json`
- Check bridge heartbeat: `llm_advisory` should be `True`
- Need â‰¥5 patterns or â‰¥2 merged insights to trigger

### No events in queue
- Verify tailer is running and watching the right session
- Check kaitd is accepting: `Invoke-RestMethod http://127.0.0.1:8787/health`

---

## Agent Behavior (Kait the Seer)

### On Cron Refresh (every 30 min)
1. Read `KAIT_ADVISORY.md`
2. For each recommendation: act, defer, or skip
3. Report feedback via `lib/agent_feedback.py`:
   ```python
   import sys; sys.path.insert(0, r"<REPO_ROOT>")
   from lib.agent_feedback import advisory_acted, advisory_skipped, learned_something
   ```
4. Read `KAIT_CONTEXT.md` and `KAIT_NOTIFICATIONS.md`

### On Heartbeat
- Check Kait services health
- Review advisories if not recently reviewed
- Monitor RAM usage

### When Learning Something
Always write it down:
```python
from lib.agent_feedback import learned_something
learned_something("what you learned", "context", confidence=0.9)
```

---

## Git Workflow

- Repo: `vibeforge1111/kait-intel` (PUBLIC)
- Push after every logical chunk
- Today's commits: 14 (Phase 1-2, UTF-8 fixes, live advice, memory leak fix, LLM integration, feedback loop, docs)

