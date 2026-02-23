# Kait Quick Start Guide

Get Kait running in 5 minutes.

If you are brand new, start with `docs/GETTING_STARTED_5_MIN.md` (shorter, newcomer path).
For the full active documentation map, see `docs/DOCS_INDEX.md`.
For term-based navigation, see `docs/GLOSSARY.md`.

## Prerequisites

- Python 3.10+
- pip
- Git
- Windows one-command path: PowerShell
- Mac/Linux one-command path: `curl` + `bash`

## Installation

### Option 1: Windows One Command

```powershell
irm https://raw.githubusercontent.com/vibeforge1111/kait-intel/main/install.ps1 | iex
```

Then run a ready check (from repo root):

```powershell
.\.venv\Scripts\python -m kait.cli up
.\.venv\Scripts\python -m kait.cli health
```

### Option 2: Mac/Linux One Command

```bash
curl -fsSL https://raw.githubusercontent.com/vibeforge1111/kait-intel/main/install.sh | bash
```

Then run a ready check (from repo root):

```bash
./.venv/bin/python -m kait.cli up
./.venv/bin/python -m kait.cli health
```

### Option 3: Quick Install

```bash
cd /path/to/Kait
./scripts/install.sh
```

### Option 4: Manual Install

```bash
# Install dependencies in a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .[services]

# Optional: Enable embeddings (fastembed)
python -m pip install -e .[embeddings]

# Test it works
python -m kait.cli health
```

```powershell
# Windows manual install without activation policy issues:
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[services]"
.\.venv\Scripts\python -m kait.cli health
```

If pip reports `externally-managed-environment`, you are likely running on a
system-managed Python install (Ubuntu/Debian policy). Re-run after creating and
activating a local virtualenv as above.

## Basic Usage

### Check Status

```bash
python3 -m kait.cli status
```

### Start Background Services (Recommended)

These keep the bridge worker running and the dashboard live.

```bash
python3 -m kait.cli up
# or: kait up
```
Lightweight mode (core services only: kaitd + bridge_worker):
```bash
python3 -m kait.cli up --lite
```

Repo shortcuts:
```bash
./scripts/run_local.sh
```

Windows (repo):
```bat
start_kait.bat
```
Preferred launch paths on Windows are `start_kait.bat` and `python -m kait.cli ...`.
`scripts/kait.ps1` and `scripts/kait.cmd` are deprecated compatibility wrappers.
This also starts Mind on `KAIT_MIND_PORT` (default `8080`) if `mind.exe` is available.
Set `KAIT_NO_MIND=1` to skip Mind startup.
Set `KAIT_LITE=1` to skip dashboards/pulse/watchdog (core services only).
Kait auto-detects sibling `../vibeship-kait-pulse`. Set `KAIT_PULSE_DIR` env var if it's elsewhere.
Set `KAIT_PULSE_DIR` to override both.
For this setup, use:
```bat
set KAIT_PULSE_DIR=<KAIT_PULSE_DIR>
```
If Mind CLI is installed but unstable, force Kait's built-in Mind server:
```bat
set KAIT_FORCE_BUILTIN_MIND=1
start_kait.bat
```

Check status:
```bash
python3 -m kait.cli services
# or: kait services
```

### Opportunity Scanner Runtime Checks

Verify scanner status and recent self-Socratic prompts:

```bash
python -c "from lib.opportunity_scanner import get_scanner_status, get_recent_self_opportunities; import json; print(json.dumps(get_scanner_status(), indent=2)); print(json.dumps(get_recent_self_opportunities(limit=5), indent=2))"
```

Inbox workflow (accept/dismiss):
```bash
python -m kait.cli opportunities list --limit 20
python -m kait.cli opportunities accept <id-prefix>
python -m kait.cli opportunities dismiss <id-prefix>
```

Enable Minimax-backed scanner synthesis (optional):

```bash
set KAIT_OPPORTUNITY_LLM_ENABLED=1
set KAIT_OPPORTUNITY_LLM_PROVIDER=minimax
set MINIMAX_API_KEY=your_key_here
set KAIT_MINIMAX_MODEL=MiniMax-M2.5

# Recommended cadence: one LLM "deep scan" at most every 15 minutes per session while you're actively working.
# (Scanner already skips LLM calls when context is insufficient.)
set KAIT_OPPORTUNITY_LLM_COOLDOWN_S=900
```

After setting env vars, restart services (`kait down` then `kait up`) and check scanner heartbeat `llm` fields (`used`, `provider`, `error`).

Verify scanner stats are present in bridge heartbeat:

```bash
python -c "import json; from pathlib import Path; p=Path.home()/'.kait'/'bridge_worker_heartbeat.json'; d=json.loads(p.read_text(encoding='utf-8')); print(json.dumps((d.get('stats') or {}).get('opportunity_scanner') or {}, indent=2))"
```

Inspect persisted scanner artifacts:

```bash
# self-opportunities
python -c "from pathlib import Path; p=Path.home()/'.kait'/'opportunity_scanner'/'self_opportunities.jsonl'; print(p, 'exists=', p.exists())"

# acted outcomes + promotion candidates
python -c "from pathlib import Path; base=Path.home()/'.kait'/'opportunity_scanner'; print((base/'outcomes.jsonl').exists(), (base/'promoted_opportunities.jsonl').exists())"
```

The watchdog auto-restarts workers and warns when the queue grows. Set
`KAIT_NO_WATCHDOG=1` to disable it when using the launch scripts.

Stop services:
```bash
python3 -m kait.cli down
# or: kait down
```

### Observability

Kait observability is provided by three systems:

- **Kait Pulse** (primary web dashboard): http://localhost:${KAIT_PULSE_PORT:-8765}
  - Tabs/surfaces include Mission, Learning, Rabbit, Acceptance, Ops, Chips, Tuneables, Tools, and Trace/Run drilldowns.
- **Obsidian Observatory** (file-based pipeline viewer): `python scripts/generate_observatory.py --force`
  - Full 12-stage pipeline visualization, explorer pages for every data store, auto-syncs every 120s.
- **CLI scripts**: `scripts/kait_dashboard.py`, `scripts/eidos_dashboard.py`

Port overrides:
- `KAITD_PORT`
- `KAIT_PULSE_PORT`
- `KAIT_MIND_PORT`

Tip: `kait up` starts core services + Pulse by default. Use `--no-pulse` for debugging.
Tip: `kait up --lite` skips Pulse and watchdog to reduce background load.

### Production Hardening Defaults

- `kaitd` auth: all mutating `POST` endpoints require `Authorization: Bearer <token>` (token auto-resolves from `KAITD_TOKEN` or `~/.kait/kaitd.token`).
- Queue safety: queue rotation and processed-event consumption both use temp-file + atomic replace.
- Validation loop: bridge cycle runs both prompt validation and outcome-linked validation each cycle.
- Service startup: if Kait Pulse app is unavailable, core services still start and pulse is reported unavailable.

Test gates before push:
```bash
python -m ruff check . --select E9,F63,F7,F82
python -m pytest -q
```

### Automated Always-On (Quick Start)

Keep Kait running at login so hooks never miss events.

#### Windows (Task Scheduler)
Manual setup:
1) Open Task Scheduler -> Create Task
2) Trigger: At log on
3) Action: Start a program
   - Program/script: `kait` (or full `python.exe`)
   - Add arguments: `up --sync-context --project "C:\path\to\your\project"`
   - Start in: `C:\path\to\your\project`

Helper script (creates the task automatically):
```powershell
./scripts/install_autostart_windows.ps1
```

Remove the task:
```powershell
./scripts/remove_autostart_windows.ps1
```

If you get "Access is denied", run PowerShell as Administrator.

#### macOS (launchd)
Create `~/Library/LaunchAgents/co.vibeship.kait.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>co.vibeship.kait</string>
    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/python3</string>
      <string>-m</string>
      <string>kait.cli</string>
      <string>up</string>
      <string>--sync-context</string>
      <string>--project</string>
      <string>/path/to/your/project</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$HOME/.kait/logs/launchd.out</string>
    <key>StandardErrorPath</key><string>$HOME/.kait/logs/launchd.err</string>
  </dict>
</plist>
```

Load it:
```bash
launchctl load -w ~/Library/LaunchAgents/co.vibeship.kait.plist
```

Unload it:
```bash
launchctl unload ~/Library/LaunchAgents/co.vibeship.kait.plist
```

#### Linux (systemd user service)
Create `~/.config/systemd/user/kait-up.service`:
```ini
[Unit]
Description=Kait background services

[Service]
Type=simple
ExecStart=python3 -m kait.cli up --sync-context --project /path/to/your/project
Restart=on-failure

[Install]
WantedBy=default.target
```

Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable --now kait-up.service
```

Stop:
```bash
systemctl --user disable --now kait-up.service
```

#### Fallback (cron)
If you prefer cron:
```
@reboot python3 -m kait.cli up --sync-context --project /path/to/your/project >/dev/null 2>&1
```

### Per-Project Ensure (Optional)

If you want each project to guarantee Kait is running, add this to your
project start script or editor task:

```bash
kait ensure --sync-context --project .
# or: python3 -m kait.cli ensure --sync-context --project .
```

Windows helper (run from project root):
```bat
scripts\ensure_kait.bat
```

macOS/Linux helper:
```bash
kait ensure --sync-context --project "$(pwd)"
```

### Create Learnings (Programmatic)

```python
from lib.cognitive_learner import get_cognitive_learner

cognitive = get_cognitive_learner()

# Learn from a failure
cognitive.learn_struggle_area(
    task_type="regex_patterns",
    failure_reason="Edge cases in complex patterns"
)

# Learn a principle
cognitive.learn_principle(
    principle="Always test edge cases",
    examples=["Empty input", "Null values", "Unicode"]
)
```

### Write to Markdown

```bash
python3 -m kait.cli write
# Creates .learnings/LEARNINGS.md
```

### Optional: Agent Context Injection (Opt-in)

If you spawn sub-agents, you can prepend a compact Kait context block to their
prompts. This is off by default.

```bash
KAIT_AGENT_INJECT=1
KAIT_AGENT_CONTEXT_LIMIT=3
KAIT_AGENT_CONTEXT_MAX_CHARS=1200
```

Use `lib.orchestration.inject_agent_context(prompt)` when preparing sub-agent prompts.

## Optional: Scheduled Sync Backup

If you want a safety net (for sessions launched outside wrappers), run sync on a timer.

**Windows Task Scheduler**
- Action: `kait`
- Args: `sync-context`
- Start in: your repo root
- Trigger: every 10â€“30 minutes

**macOS/Linux (cron)**
```
*/20 * * * * cd /path/to/kait-intel && kait sync-context >/dev/null 2>&1
```

### Promote High-Value Insights

```bash
# Check what's ready
python3 -m kait.cli promote --dry-run

# Actually promote
python3 -m kait.cli promote
# Creates/updates AGENTS.md, CLAUDE.md, etc.
```

## Mind Integration (Optional)

For persistent semantic memory:

```bash
# Install Mind
pip install vibeship-mind

# Start Mind server
python3 -m mind.lite_tier
# If Mind CLI fails, use Kait's built-in server:
python3 mind_server.py

# Sync Kait learnings to Mind
python3 -m kait.cli sync
```

## Semantic Retrieval (Optional)

Enable semantic matching for cognitive insights:

```bash
# Optional: local embeddings
pip install fastembed

# Enable semantic + triggers
# ~/.kait/tuneables.json
#
# "semantic": { "enabled": true, ... }
# "triggers": { "enabled": true, ... }

# Backfill semantic index
python -m kait.index_embeddings --all
# (legacy) python scripts/semantic_reindex.py
```

Use it during real work:
```python
from lib.advisor import advise_on_tool
advice = advise_on_tool("Edit", {"file_path": "src/auth/login.py"}, "edit auth login flow")
```

Semantic retrieval logs and metrics:
- `~/.kait/logs/semantic_retrieval.jsonl`
- `~/.kait/advisor/metrics.json`

## Claude Code Integration

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 /path/to/Kait/hooks/observe.py"
      }]
    }],
    "PostToolUse": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 /path/to/Kait/hooks/observe.py"
      }]
    }],
    "PostToolUseFailure": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 /path/to/Kait/hooks/observe.py"
      }]
    }],
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 /path/to/Kait/hooks/observe.py"
      }]
    }]
  }
}
```

Kait maps these hook names to runtime event types used by chips:
`pre_tool`, `post_tool`, `post_tool_failure`, `user_prompt`.

For predictive advisory to work end-to-end, `PreToolUse` must be enabled.

## Codex Integration (Optional)

Use when you want Codex sessions to receive `KAIT_CONTEXT_FOR_CODEX.md` and
`KAIT_ADVISORY_PAYLOAD.json`.

```bash
# Preferred: launch Codex through the wrapper
scripts/kait-codex.sh
# Windows
scripts\\kait-codex.bat
```

What the wrapper does:

- sets `KAIT_SYNC_TARGETS=codex` if not already set
- sets `CMD` from `KAIT_CODEX_CMD` or `CODEX_CMD` (fallback to `codex`)
- runs `python -m kait.cli sync-context` before launching Codex

If you run sync manually:

```bash
# Either of these enables Codex output during sync
set KAIT_SYNC_TARGETS=codex
set KAIT_CODEX_CMD=codex
# or
python -m kait.cli sync-context
```

Verify Codex sync artifacts are present in the current project:

```bash
test -f KAIT_CONTEXT_FOR_CODEX.md && test -f KAIT_ADVISORY_PAYLOAD.json && echo "ok"
python -m lib.integration_status
```

If status still reports missing Codex sync, confirm:

- the command runs in the same shell/environment where `KAIT_CODEX_CMD` or `CODEX_CMD` is set
- `kait.cli sync-context` is completing successfully
- `KAIT_SYNC_TARGETS` is not overridden to exclude `codex`

## Directory Structure

After running, Kait creates:

```
~/.kait/                      # Config and data
â”œâ”€â”€ cognitive_insights.json    # Raw learnings
â”œâ”€â”€ mind_sync_state.json       # Sync tracking
â”œâ”€â”€ exposures.jsonl            # Surfaced insights (prediction inputs)
â”œâ”€â”€ predictions.jsonl          # Prediction registry
â”œâ”€â”€ outcomes.jsonl             # Outcomes log (skills/orchestration/project)
â”œâ”€â”€ skills_index.json          # Cached skills index
â”œâ”€â”€ skills_effectiveness.json  # Skill success/fail counters
â”œâ”€â”€ orchestration/
â”‚   â”œâ”€â”€ agents.json            # Registered agents
â”‚   â””â”€â”€ handoffs.jsonl         # Handoff history
â””â”€â”€ queue/
    â””â”€â”€ events.jsonl           # Event queue

.learnings/                    # In your project
â”œâ”€â”€ LEARNINGS.md              # Human-readable insights
â””â”€â”€ ERRORS.md                 # Error patterns

AGENTS.md                      # Promoted workflow patterns
CLAUDE.md                      # Promoted conventions
```

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `status` | Show full system status |
| `services` | Show daemon/service status |
| `up` | Start background services (`--lite` for core-only) |
| `ensure` | Start missing services if not running |
| `down` | Stop background services |
| `health` | Quick health check |
| `learnings` | List recent cognitive insights |
| `write` | Write insights to markdown |
| `promote` | Auto-promote high-value insights |
| `sync-context` | Sync bootstrap context to platform files |
| `decay` | Preview/apply decay-based pruning |
| `sync` | Sync to Mind (if running) |
| `queue` | Process offline sync queue |
| `process` | Run bridge worker cycle or drain backlog |
| `validate` | Run validation scan on recent events |
| `events` | Show recent captured events |

## Troubleshooting

### "Mind API: Not available"

Mind isn't running. Either:
- Start Mind: `python3 -m mind.lite_tier`
- Or ignore it â€” Kait works offline and queues for later

### "requests not installed"

```bash
pip install requests
```

### Maintenance script locations

- One-time cleanup scripts now live under `scripts/maintenance/one_time/`.
- Archived manual LLM bridge diagnostics live under `scripts/experimental/manual_llm/`.
- Old top-level cleanup paths remain as compatibility shims.

### Learnings not appearing

Check that the hook is configured correctly and the path is absolute.

If the queue is large or processing stalled, run:

```bash
python -m kait.cli process --drain
```

### Extra logging (optional)

Enable debug logs temporarily when troubleshooting:

```bash
set KAIT_DEBUG=1
```

Tip: leave it off for normal usage to avoid log noise.

### Validation Loop (v1)

The current validation loop focuses on user preferences + communication insights.
Recommended: let it run for a day or two to confirm low false positives, then
expand scope if needed.

## Next Steps

1. **Integrate with your workflow** â€” Set up the hooks
2. **Start Mind** â€” For persistent cross-project learning
3. **Review learnings** â€” `python3 -m kait.cli learnings`
4. **Promote insights** â€” `python3 -m kait.cli promote`

---

*Part of the Vibeship Ecosystem*

