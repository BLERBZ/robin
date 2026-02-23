# 🧠 Kait Intelligence — Onboarding Guide

## For New Users

### What is Kait Intelligence?

Kait Intelligence is a **self-evolution layer** for AI agents. It continuously captures patterns from your coding interactions, distills them through the EIDOS framework, and feeds intelligence back to your agent — making it genuinely smarter over time. Unlike static system prompts, Kait creates a living memory that evolves with you.

It works with **OpenClaw** (or any Claude-based agent) and requires **zero API keys** — just Claude OAuth. Set `KAIT_EMBEDDINGS=0` to keep it completely free beyond your normal Claude usage.

### Quick Start

```bash
# One command to install everything:
git clone https://github.com/vibeforge1111/kait-openclaw-installer.git
cd kait-openclaw-installer

# Windows:
.\install.ps1

# Mac/Linux:
chmod +x install.sh && ./install.sh
```

That's it. The installer handles Python deps, OpenClaw, Claude Code CLI, config files, and starts the services. After install, just **code normally** — Kait learns in the background.

### What to Expect in Your First 24 Hours

| Timeframe | What Happens |
|-----------|-------------|
| **Hour 0-1** | Kait starts capturing your interactions silently |
| **Hour 1-3** | First patterns detected (communication style, preferences) |
| **Hour 3-6** | First advisory generated — your agent starts adapting |
| **Hour 6-12** | Pattern confidence grows, behavior adjustments become visible |
| **Hour 12-24** | EIDOS distillations form — deep understanding of your workflow |

You don't need to do anything special. Just work. Kait watches and learns.

### Understanding the Dashboard

Open **http://localhost:8765** (Kait Pulse) to see:

- **Neural Activity** — Real-time visualization of learning events
- **Learnings Feed** — What Kait has captured from your interactions
- **Pattern Map** — Detected behavioral and preference patterns
- **Advisory Log** — History of advisories sent to your agent
- **EIDOS View** — Deep distillations of your working style

---

## For Power Users

### How the Self-Evolution Loop Works

```
You code with your agent
        ↓
Kait captures interactions (tailer)
        ↓
Pattern detection runs locally (no embeddings needed)
        ↓
Bridge cycle: Claude reviews patterns, creates advisories
        ↓
Advisories written to KAIT_ADVISORY.md
        ↓
Your agent reads advisories and adapts
        ↓
You notice the improvement (or give feedback)
        ↓
Feedback feeds back into the loop
        ↓
Repeat — agent gets smarter each cycle
```

### Giving Feedback

Feedback is how you steer Kait's learning. Use `agent_feedback.py`:

```python
from kait.agent_feedback import record_feedback, rate_advisory

# Tell Kait about a preference
record_feedback("User prefers functional style over OOP")

# Rate an advisory (did it help?)
rate_advisory(advisory_id="adv_2026_0210_001", helpful=True, notes="Nailed it")

# Report a correction
record_feedback("User corrected: use 'const' not 'let' by default", signal="correction")
```

Or use the CLI:
```bash
kait learn "User prefers dark mode in all tools"
kait feedback --advisory adv_001 --helpful true
```

### Writing Custom Chips

Chips are pluggable intelligence modules. Create one in `chips/`:

```python
# chips/my_chip.py
from kait.chips.base import Chip

class MyChip(Chip):
    name = "my_custom_chip"
    
    async def process(self, interaction):
        # Your custom pattern detection logic
        if "deadline" in interaction.text.lower():
            return self.signal("deadline_detected", confidence=0.8)
        return None
```

Register in `config/chips.yaml` and restart kaitd.

### Tuning the System

See **[TUNEABLES.md](../TUNEABLES.md)** for all configurable parameters:

- **Memory Gate threshold** (default 0.5) — Controls what gets persisted
- **Pattern confidence** — Minimum confidence to surface a pattern
- **Bridge cycle interval** — How often Claude reviews patterns (default 60 min)
- **Advisory priority weights** — What gets flagged as HIGH vs MED vs LOW

### The `advice_action_rate` Metric

This is your key health metric. It measures: **of all advisories generated, what % led to observable behavior change?**

- **>60%**: Excellent — Kait is well-tuned to your needs
- **30-60%**: Good — Some advisories are noise, consider raising thresholds
- **<30%**: Needs tuning — Lower the memory gate or adjust chip weights

Track it on the dashboard or: `kait status --metrics`

---

## For OpenClaw Users

### How Kait Integrates with OpenClaw

```
┌─────────────────────────────────────┐
│           OpenClaw Agent            │
│                                     │
│  Reads: KAIT_CONTEXT.md            │
│         KAIT_ADVISORY.md           │
│         KAIT_NOTIFICATIONS.md      │
│                                     │
│  Writes: memory/*.md, interactions  │
└──────────────┬──────────────────────┘
               │
    ┌──────────┴──────────┐
    │   Kait Tailer      │  ← Watches OpenClaw workspace
    └──────────┬──────────┘
               │
    ┌──────────┴──────────┐
    │   kaitd (:8787)    │  ← Core intelligence engine
    │   Pattern Detection │
    │   EIDOS Framework   │
    └──────────┬──────────┘
               │
    ┌──────────┴──────────┐
    │   Bridge Worker     │  ← Claude reviews patterns
    └──────────┬──────────┘
               │
    ┌──────────┴──────────┐
    │  Kait Pulse (:8765)│  ← Dashboard
    └─────────────────────┘
```

### Workspace Files

| File | Purpose | Who Writes | Who Reads |
|------|---------|-----------|-----------|
| `KAIT_CONTEXT.md` | Current learnings, patterns, EIDOS | Kait | Agent |
| `KAIT_ADVISORY.md` | Active advisories (HIGH/MED/LOW) | Kait | Agent |
| `KAIT_NOTIFICATIONS.md` | System notifications | Kait | Agent |
| `HEARTBEAT.md` | What agent checks each heartbeat | You/Installer | Agent |
| `SOUL.md` | Agent identity and personality | You/Onboard | Agent |
| `IDENTITY.md` | Human + agent metadata | Onboard script | Agent |

### Cron Setup for Advisory Review

Option 1 — **OpenClaw Cron** (recommended):
```bash
openclaw cron add --every 60m --command "python kaitd.py bridge --once --output openclaw"
```

Option 2 — **System crontab**:
```bash
# Run bridge every hour
0 * * * * cd ~/.kait/kait-intel && KAIT_EMBEDDINGS=0 python3 bridge_worker.py --once
```

Option 3 — **HEARTBEAT.md** (agent-driven):
The default HEARTBEAT.md already includes advisory checking. The agent will read advisories every heartbeat (~30 min).

### HEARTBEAT.md Configuration

The installer sets up HEARTBEAT.md to:
1. Read KAIT_ADVISORY.md for new advisories
2. Read KAIT_NOTIFICATIONS.md for system events
3. Check KAIT_CONTEXT.md for updated learnings
4. Periodically feed observations back to Kait

Edit `~/.openclaw/workspace/HEARTBEAT.md` to customize.

### The `kait` CLI Commands

```bash
kait start              # Start kaitd + bridge + pulse
kait stop               # Stop all services
kait status             # Health check + metrics
kait learn "insight"    # Manually teach Kait something
kait advisory "warning" # Create a manual advisory
kait pattern "pattern"  # Report a detected pattern
kait bridge             # Trigger a bridge cycle manually
kait bridge --once      # Run one cycle and exit
kait logs               # Tail kaitd logs
kait config             # Show current config
```

---

## Why KAIT_EMBEDDINGS=0?

This is **critical** and set by default. Here's why:

1. **Cost**: Embeddings require API calls for every piece of text. Over days of coding, this adds up fast.
2. **Not needed**: Kait's pattern detection uses keyword matching + frequency analysis, which works great without embeddings.
3. **Privacy**: No text leaves your machine for embedding — everything stays local.
4. **Speed**: No network latency for embedding calls.

The only Claude API usage is the bridge cycle (~1 call/hour), which uses your OAuth session.

If you *want* embeddings for advanced semantic matching, set `KAIT_EMBEDDINGS=1` — but understand the cost implications.
