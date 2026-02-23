# Kait AI Intel -- Setup and Usage Guide

## 1. Overview

The Kait AI Intel is a **self-evolving, 100% local AI system** that runs
entirely on your machine. No cloud APIs. No telemetry. No external dependencies
beyond [Ollama](https://ollama.com) for local LLM inference.

It integrates with the broader Kait Intelligence platform (EIDOS, Advisory,
Meta-Ralph) and adds:

- **Self-evolution** through 10 progressive stages (Basic through God-like)
- **Persistent memory** via a local SQLite ReasoningBank
- **Multi-agent architecture** with sentiment, creativity, logic, reflection,
  and tool agents
- **A living avatar** that reflects the sidekick's mood, energy, and evolution
  stage -- in text, ASCII art, or an optional Pygame graphical renderer
- **User resonance tracking** that adapts personality and responses over time
- **Background self-improvement** during idle time (reflection cycles, prompt
  refinement, pattern extraction)
- **v1.2: Token streaming** -- responses appear in real-time as tokens arrive
- **v1.2: Dynamic correction injection** -- past mistakes are actively avoided
- **v1.2: Mandatory creativity** -- every response has a creative kait
- **v1.2: Proactive insights** -- the sidekick surfaces learnings during idle
- **v1.2: Behavior rules** -- actionable patterns extracted from interactions
- **v1.3: Pre-flight diagnostics** (`--check`) -- validates Ollama, models, disk, GPU before launch
- **v1.3: In-session health check** (`/health`) -- run diagnostics without restarting
- **v1.3: Daemon mode** (`--daemon`) -- auto-reconnects to Ollama if it drops
- **v1.3: Persistent behavior rules** -- learned rules survive across sessions (SQLite-backed)
- **v1.3: Quickstart script** -- one-command bootstrap (`bash quickstart.sh`)
- **v1.3: Context search** -- efficient prefix-based context lookup in ReasoningBank
- **v1.4: Session resume** -- warm welcome-back greeting with last session context
- **v1.4: Semantic memory** -- keyword-overlap retrieval of relevant past interactions
- **v1.4: Conversation export** (`/export`) -- save sessions as markdown
- **v1.4: LLM retry with trimming** -- auto-retry with smaller context on failure
- **v1.4: Response timing** -- shows generation time and interaction count
- **v1.4: Sentiment kaitline** -- visual trend in `/status` output

The sidekick learns from every interaction, records corrections, tracks
resonance, and periodically reflects on its own behavior to improve.

---

## 2. System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.10+ | 3.11 or 3.12 |
| RAM | 16 GB | 32 GB (required for 70B models) |
| GPU | None (CPU works, slower) | NVIDIA GPU with 8+ GB VRAM |
| Disk | 10 GB free (for models) | 20+ GB |
| OS | Linux, macOS, Windows (WSL) | Linux or macOS |

**Software dependencies:**

- **Ollama** -- required for local LLM inference
- **Python stdlib only** -- the sidekick has zero required pip dependencies
- **pygame** -- optional, only needed for the graphical avatar window

macOS users with Apple Silicon get GPU acceleration automatically through
Ollama's Metal backend. No extra drivers needed.

---

## 3. Installation

### 3.1 Clone the Repository

```bash
git clone https://github.com/your-org/kait-intel.git
cd kait-intel
```

### 3.2 Python Dependencies

The sidekick is built on Python's standard library. The only optional
dependency is `pygame` for the graphical avatar:

```bash
# Optional: install pygame for the graphical avatar window
pip install pygame
```

There is no `requirements.txt` needed for the core sidekick. All modules
(`reasoning_bank`, `local_llm`, `agents`, `avatar`, `resonance`, `reflection`,
`tools`, `evolution`) use only stdlib.

### 3.3 Install Ollama

**Linux / WSL:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS (Homebrew):**

```bash
brew install ollama
```

**Windows:**

Download the installer from [ollama.com/download](https://ollama.com/download).

### 3.4 Pull a Model

```bash
# Recommended for most systems (8B parameters, ~4.7 GB)
ollama pull llama3.1:8b

# For GPU systems with 32+ GB VRAM (70B parameters, ~40 GB)
ollama pull llama3.1:70b

# Other supported models (auto-detected in preference order)
ollama pull llama3
ollama pull mistral
```

The sidekick auto-detects the best available model in this order:
`llama3.1:70b` > `llama3.1:8b` > `llama3:latest` > `mistral` > largest
available model. You can override this with the `KAIT_OLLAMA_MODEL`
environment variable.

### 3.5 Start Ollama

```bash
ollama serve
```

Leave this running in a separate terminal, or configure it as a system service.
Ollama listens on `localhost:11434` by default.

---

## 4. Quick Start

### One-Command Bootstrap (recommended)

```bash
bash quickstart.sh
```

This script handles everything: checks Python, installs/starts Ollama, pulls a
model if needed, runs pre-flight diagnostics, and launches the sidekick. Pass
flags through:

```bash
bash quickstart.sh --avatar-gui    # Launch with graphical avatar
bash quickstart.sh --daemon        # Launch in daemon mode
```

### Pre-flight Check

```bash
python kait_ai_sidekick.py --check
```

Validates that your system is ready: Python version, Ollama installed and
running, models available, data directory writable, disk space, and GPU
detection. Exits with code 0 on success, 1 on failure.

### Interactive Mode (default)

```bash
python kait_ai_sidekick.py
```

This launches the infinite interaction loop. You will see:

```
    ____                   _
   / ___| _ __   __ _ _ __| | __
   \___ \| '_ \ / _` | '__| |/ /
    ___) | |_) | (_| | |  |   <
   |____/| .__/ \__,_|_|  |_|\_\
         |_|  AI Sidekick v1.4.0

  100% Local | Self-Evolving | Brings a Kait to Everything
  Session: a1b2c3d4e5f6 | Type /help for commands

  Connecting to local LLM...
  Connected! Using model: llama3.1:8b
  GPU detected: Apple Silicon (Metal)

  Systems are BLAZING -- let's light this up!
  [Ember -- Stage 1]  Balanced energy. Kait is steady.

  Evolution: Stage 1 - Basic | Interactions: 0

[You] hello!
```

### With Graphical Avatar

```bash
python kait_ai_sidekick.py --avatar-gui
```

Opens a 400x400 Pygame window rendering a real-time particle avatar. The avatar
shows a central pulsing orb, an aura ring that shifts with mood, particle
fields, and neural lines that intensify during high-kait states. Requires
`pygame`.

### Check Evolution Status

```bash
python kait_ai_sidekick.py --status
```

Prints the current evolution report and ReasoningBank statistics, then exits.

### Reset Evolution State

```bash
python kait_ai_sidekick.py --reset
```

Resets all evolution metrics back to Stage 1. Destructive -- use with caution.

### Daemon Mode (auto-reconnect)

```bash
python kait_ai_sidekick.py --daemon
```

Runs the sidekick with a background reconnect thread. If Ollama goes down,
the sidekick continues in offline mode and automatically reconnects every 30
seconds when Ollama comes back. Writes a PID file to `~/.kait/sidekick.pid`
for external monitoring.

### Show Version

```bash
python kait_ai_sidekick.py --version
```

---

## 5. Architecture

### 5.1 Module Overview

The sidekick is organized under `lib/sidekick/` with these modules:

| Module | Purpose |
|--------|---------|
| `reasoning_bank.py` | SQLite persistence -- interactions, corrections, contexts, preferences, personality, evolutions |
| `local_llm.py` | Ollama HTTP client (stdlib `urllib` only) -- generation, chat, streaming, embeddings, GPU detection |
| `agents.py` | Multi-agent sub-system -- Sentiment, Creativity, Logic, Tool, and Reflection agents with orchestrator |
| `avatar.py` | Living avatar -- text descriptions, ASCII art, optional Pygame particle renderer with 12 mood profiles |
| `resonance.py` | User resonance -- rule-based sentiment analysis, preference tracking, resonance scoring |
| `reflection.py` | Self-reflection -- periodic introspection cycles, behavior evolution, prompt refinement, scheduling |
| `tools.py` | Sandboxed local tools -- calculator, file I/O, system info, datetime, JSON, text analysis, SQL query |
| `evolution.py` | 10-stage evolution engine -- metrics tracking, threshold checks, stage advancement, persistence |

### 5.2 Data Flow

```
                          User Input
                              |
                              v
                  +---------------------+
                  |  Sentiment Agent    |----> Mood classification
                  +---------------------+         |
                              |                   v
                  +---------------------+   +------------+
                  |  Creativity Agent   |   |   Avatar   |
                  +---------------------+   |  (update   |
                              |             |   mood)    |
                  +---------------------+   +------------+
                  |  Tool Agent         |
                  | (detect tool need)  |---> Tool Registry ---> Sandboxed Exec
                  +---------------------+
                              |
                  +---------------------+
                  |  Logic Agent        |
                  | (reasoning chains)  |
                  +---------------------+
                              |
                  +---------------------+
                  |  ReasoningBank      |<--- Context retrieval
                  | (memory lookup)     |     (corrections, preferences, traits)
                  +---------------------+
                              |
                              v
                  +---------------------+
                  |  LLM Generation     |<--- System prompt + agent fragments
                  |  (Ollama /api/chat) |     + tool output + context + history
                  +---------------------+
                              |
                              v
                        AI Response
                              |
              +---------------+----------------+
              |               |                |
              v               v                v
         +--------+   +-----------+   +--------------+
         | Avatar |   | Resonance |   | ReasoningBank|
         | render |   | tracking  |   | (save inter- |
         +--------+   +-----------+   |  action)     |
                              |       +--------------+
                              v                |
                      +-------------+          v
                      |  Evolution  |   Learn from
                      |  (record    |   interaction
                      |   outcome)  |
                      +-------------+
                              |
              +---------------+----------------+
              |               |                |
     Maybe Reflect    Maybe Evolve    Idle Learning
     (periodic)       (threshold)     (background)
```

### 5.3 Integration with Kait Intelligence

The sidekick optionally integrates with the existing Kait Intelligence
platform:

- **EIDOS** -- If `lib.eidos.store` is importable, the sidekick can read from
  the EIDOS evidence store. This is a soft dependency; the sidekick runs
  fine without it.
- **Advisory** -- The sidekick's ReasoningBank tables are compatible with the
  advisory pipeline's feedback and packet systems.
- **Meta-Ralph** -- Evolution events and personality shifts can feed into
  Meta-Ralph's meta-cognitive learning loops.

---

## 6. Commands Reference

All commands start with `/` and are case-insensitive.

| Command | Description |
|---------|-------------|
| `/status` | Show system status: version, session, model, evolution stage, interaction count, resonance, agent activity |
| `/health` | Run self-diagnostics: Ollama, models, DB, disk space, GPU |
| `/avatar` | Display the current avatar state (text description + ASCII art) |
| `/evolve` | Show detailed evolution progress report with gap analysis for next stage |
| `/reflect` | Manually trigger a self-reflection cycle |
| `/tools` | List all available local tools |
| `/tool <name> <args>` | Execute a specific tool (see Section 10 for details) |
| `/history` | Show the last 10 interactions with timestamps |
| `/corrections` | Show learned corrections from user feedback |
| `/personality` | Show current personality traits with visual bars |
| `/export [name]` | Export conversation as markdown to `~/.kait/exports/` |
| `/correct <text>` | Correct the last response -- records the correction for learning |
| `/feedback <1-5>` | Rate the last response (1 = bad, 5 = great) -- updates resonance and evolution |
| `/help` | Show the commands help screen |
| `/quit` | Exit gracefully (also `/exit`, `/bye`) |

### Examples

```
[You] /tool calculator 2**10 + 42
  Result: 1066

[You] /feedback 5
  Feedback recorded: 5/5. Thank you!

[You] /correct The answer should have included the units in meters.
  Correction recorded. I'll learn from this!

[You] /personality
  Personality traits:
    warmth          [================----] 0.82
    curiosity       [==============------] 0.70
    directness      [============--------] 0.60
```

---

## 7. Evolution Stages

The sidekick progresses through 10 stages based on accumulated experience.
Each stage requires meeting **all** thresholds simultaneously:

| Stage | Name | Interactions | Corrections | Resonance | Quality | Reflections | Description |
|-------|------|-------------|-------------|-----------|---------|-------------|-------------|
| 1 | **Basic** | 0 | 0 | 0.00 | 0.00 | 0 | Default responses. Learning the ropes. |
| 2 | **Adaptive** | 25 | 5 | 0.20 | 0.40 | 1 | Learning preferences. Adjusting to user patterns. |
| 3 | **Resonant** | 75 | 15 | 0.35 | 0.50 | 3 | Personality emerging. Finding shared frequency. |
| 4 | **Creative** | 200 | 30 | 0.45 | 0.58 | 7 | Generating novel responses. Breaking templates. |
| 5 | **Insightful** | 500 | 60 | 0.55 | 0.65 | 15 | Deep pattern recognition. Connecting dots across domains. |
| 6 | **Anticipatory** | 1,000 | 100 | 0.65 | 0.72 | 30 | Predicting user needs before they arise. |
| 7 | **Empathic** | 2,000 | 150 | 0.74 | 0.78 | 50 | Emotional intelligence. Reading between the lines. |
| 8 | **Wise** | 4,000 | 200 | 0.82 | 0.84 | 80 | Synthesizing cross-domain knowledge. Seeing the bigger picture. |
| 9 | **Transcendent** | 8,000 | 300 | 0.90 | 0.90 | 120 | Creating new knowledge. Pushing beyond known boundaries. |
| 10 | **God-like** | 15,000 | 500 | 0.95 | 0.95 | 200 | Peak performance. Absolute mastery of self-evolution. |

You can check progress toward the next stage at any time:

```
[You] /evolve
  === Kait Sidekick Evolution Report ===

  Current Stage: 2/10 - Adaptive
    Learning preferences. Adjusting to user patterns.

  --- Progress to Stage 3: Resonant ---
    Interactions:  42/75  (56%)
    Corrections:   8/15   (53%)
    Resonance:     0.2800/0.35  (80%)
    Quality:       0.4600/0.50  (92%)
    Reflections:   2/3    (67%)

    Not yet ready for evolution
```

When all thresholds are met, evolution happens automatically during interaction
processing. The avatar visually transforms and a celebration message appears.

---

## 8. Self-Evolution Process

### 8.1 How the System Learns from Interactions

Every interaction goes through a 14-step pipeline:

1. **Sentiment analysis** -- classify user mood and emotional state
2. **Avatar update** -- set avatar mood based on sentiment
3. **Creativity dispatch** -- generate kait-infused response hints
4. **Tool detection** -- check if the user needs a local tool
5. **Logic dispatch** -- structured reasoning for analytical questions
6. **Context retrieval** -- pull relevant corrections, preferences, and traits
   from the ReasoningBank
7. **Prompt assembly** -- merge agent fragments, tool output, and context into
   the LLM prompt
8. **LLM generation** -- Ollama `/api/chat` with full conversation history
9. **Avatar render** -- display the living avatar alongside the response
10. **Resonance update** -- track sentiment trend and user satisfaction
11. **ReasoningBank save** -- persist the full interaction record
12. **History management** -- maintain a sliding window of conversation context
13. **Evolution metrics** -- record success, resonance, and quality scores
14. **Topic learning** -- detect and track domain frequency and sentiment trends

### 8.2 ReasoningBank Storage

The ReasoningBank (`~/.kait/sidekick.db`) is a SQLite database with seven tables:

| Table | Purpose |
|-------|---------|
| `interactions` | Every user/AI exchange -- input, response, mood, sentiment, session ID |
| `contexts` | Evolving knowledge contexts -- working memory keyed by domain |
| `corrections` | User corrections with original response, correction text, and reason |
| `evolutions` | System evolution events -- the growth timeline |
| `preferences` | User preference signals -- personalization key-value pairs |
| `personality` | AI personality traits -- float values representing trait intensity |
| `behavior_rules` | Learned behavior rules from reflection -- persist across sessions |

You can inspect this database directly:

```bash
sqlite3 ~/.kait/sidekick.db ".tables"
sqlite3 ~/.kait/sidekick.db "SELECT COUNT(*) FROM interactions;"
sqlite3 ~/.kait/sidekick.db "SELECT trait, value_float FROM personality;"
```

### 8.3 Reflection Cycles

Reflection cycles run automatically (every N interactions or after idle
periods) and can be triggered manually with `/reflect`. A reflection cycle:

1. **Gathers data** -- recent interactions, corrections, and evolution history
2. **Analyzes patterns** -- the `ReflectionCycle` class identifies recurring
   themes, sentiment trends, correction domains, and quality drifts
3. **Produces insights** -- actionable observations like "User prefers concise
   answers" or "Corrections cluster around code examples"
4. **Proposes behavior evolution** -- the `BehaviorEvolver` suggests concrete
   parameter changes (trait adjustments, response style shifts)
5. **Applies changes** -- accepted proposals update the ReasoningBank
6. **Refines the system prompt** -- the `PromptRefiner` weaves learnings and
   preferences into the base system prompt
7. **Updates avatar** -- confidence and kait level adjust based on reflection
   quality

The `ReflectionScheduler` manages timing: it balances between interaction
count triggers and time-based triggers to avoid reflecting too frequently or
too infrequently.

### 8.4 Personality Evolution

Personality traits are stored as float values in `[0.0, 1.0]`. The sidekick
starts with default traits and evolves them over time based on:

- Interaction patterns (curious questions increase the "curiosity" trait)
- User feedback (high ratings reinforce current personality direction)
- Corrections (negative corrections cause targeted trait adjustments)
- Reflection insights (self-analysis proposes personality refinements)

View current traits with `/personality`.

### 8.5 Prompt Refinement

The system prompt is not static. The `PromptRefiner` takes the base prompt
template and augments it with:

- Accumulated learnings from corrections
- User preference key-value pairs
- Personality trait summaries
- Domain-specific guidance from context data

This happens on startup (loading from persisted state) and after every
reflection cycle.

---

## 9. Avatar System

### 9.1 Text Mode (default)

Every response includes a text avatar display showing:

- Current evolution stage and mood label
- A descriptive paragraph of the avatar's form and aura
- Energy, warmth, confidence, and kait level bars
- Current visual theme and aura color

### 9.2 ASCII Art

The `/avatar` command shows ASCII art that changes with both **mood** and
**evolution stage**:

- **Stage 1 (Ember)** -- a small flickering point of light
- **Stage 2 (Glow)** -- a warm orb trailing wisps of light
- **Stage 3 (Flame)** -- a radiant sphere with tendrils of energy
- **Stage 4 (Star)** -- a pulsing stellar body with prismatic corona
- **Stage 5 (Cosmos)** -- a swirling galaxy of thought and light

Each mood contributes a unique accent character (`*` for excited, `~` for calm,
`?` for curious, `@` for deep thought, etc.) and varies particle density based
on kait level.

### 9.3 Pygame Graphical Mode

Launch with `--avatar-gui` to open a 400x400 Pygame window that renders in
real time:

- **Central pulsing orb** -- size scales with evolution stage, pulse rate
  tracks energy
- **Aura ring** -- color shifts smoothly between mood palettes
- **Particle field** -- HSV-hued particles whose density, speed, and color
  range are driven by energy and kait level
- **Neural lines** -- radial beams that intensify during high-kait and
  learning states

Pygame is completely optional. If it is not installed, the sidekick falls
back gracefully to text mode with no errors.

### 9.4 Mood Profiles and Transitions

The avatar supports 12 distinct moods, each with unique visual parameters:

| Mood | Theme | Energy | Warmth | Confidence | Kait | Accent |
|------|-------|--------|--------|------------|-------|--------|
| Excited | cosmic_fire | 0.92 | 0.85 | 0.80 | 0.95 | `*` |
| Calm | ocean_calm | 0.30 | 0.60 | 0.65 | 0.25 | `~` |
| Curious | prism_shift | 0.65 | 0.70 | 0.60 | 0.72 | `?` |
| Deep Thought | nebula_dream | 0.40 | 0.45 | 0.75 | 0.55 | `@` |
| Playful | rainbow_burst | 0.80 | 0.88 | 0.70 | 0.85 | `o` |
| Determined | electric_storm | 0.85 | 0.55 | 0.95 | 0.78 | `!` |
| Contemplative | ember_glow | 0.35 | 0.72 | 0.55 | 0.40 | `.` |
| Creative | aurora_weave | 0.75 | 0.78 | 0.68 | 0.92 | `+` |
| Focused | steel_focus | 0.60 | 0.40 | 0.88 | 0.50 | `\|` |
| Serene | moonlit_mist | 0.20 | 0.65 | 0.70 | 0.18 | `-` |
| Bold | solar_flare | 0.90 | 0.60 | 0.92 | 0.88 | `#` |
| Dreamy | twilight_drift | 0.25 | 0.75 | 0.50 | 0.35 | `'` |

Mood transitions are **smooth** -- the avatar interpolates between states
using linear interpolation (15% blend per tick) rather than snapping instantly.

---

## 10. Tools

All tools run locally with no external API calls. The tool system is sandboxed
with path validation, read-only database access, and AST-safe math evaluation.

### 10.1 Built-in Tools

| Tool | Category | Description |
|------|----------|-------------|
| `calculator` | math | Safe math expression evaluator -- supports `+`, `-`, `*`, `/`, `//`, `%`, `**`, `abs()`, `round()`, `min()`, `max()` |
| `file_reader` | file_io | Read local files (path validated against allowed directories: `~/.kait`, `~/Documents`, `~/Desktop`) |
| `file_writer` | file_io | Write files inside the sandbox only (`~/.kait/sidekick_data/`) |
| `file_search` | file_io | Glob-based file search within allowed directories |
| `system_info` | system | CPU, memory, disk, platform, and GPU detection |
| `datetime_tool` | utility | Current time, date parsing, date math (add days/hours/minutes), diff, formatting |
| `json_tool` | utility | Parse, format, query (dot-notation path), and validate JSON data |
| `text_tool` | utility | Word count, character count, keyword extraction, extractive summarization, full stats |
| `data_query` | data_query | Read-only parameterized SQL SELECT queries against SQLite databases |

### 10.2 Usage Examples

```
[You] /tool calculator (2**10 + 42) * 3
  Result: 3198

[You] /tool system_info
  Result: {
    "platform": "macOS-14.5-arm64-arm-64bit",
    "python_version": "3.12.1",
    "cpu_count": 12,
    ...
  }

[You] /tool datetime_tool now
  Result: {
    "local": "2026-02-22T14:30:00",
    "date": "2026-02-22",
    "weekday": "Sunday"
  }

[You] /tool text_tool This is a test of the text analysis tool.
  Result: {"word_count": 9}

[You] /tool json_tool {"users": [{"name": "Alice"}]}
  Result: {"parsed": {"users": [{"name": "Alice"}]}, "type": "dict"}

[You] /tool file_reader ~/.kait/sidekick_evolution.json
  Result: { ... evolution state ... }
```

### 10.3 Security Model

The tool system is sandboxed:

- **File reads** are restricted to allowed root directories (`~/.kait`,
  `~/Documents`, `~/Desktop`). Files outside these paths are rejected.
- **File writes** are restricted to `~/.kait/sidekick_data/` only.
- **Calculator** uses AST parsing -- no `eval()` or `exec()`. Only safe
  arithmetic operators and a whitelist of functions (`abs`, `round`, `min`,
  `max`, `int`, `float`) are permitted. Exponents larger than 10,000 are
  blocked.
- **Database queries** are read-only: only `SELECT` statements are allowed.
  Dangerous SQL keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`,
  `CREATE`, `ATTACH`, etc.) are rejected even inside a SELECT. Connections
  use SQLite's `?mode=ro` URI parameter.
- **Maximum file read size** is 10 MB. Maximum tool result payload is 1 MB.

---

## 11. Configuration

### 11.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAIT_OLLAMA_HOST` | `localhost` | Ollama server hostname |
| `KAIT_OLLAMA_PORT` | `11434` | Ollama server port |
| `KAIT_OLLAMA_MODEL` | *(auto-detect)* | Force a specific model name (overrides auto-detection) |

Example:

```bash
# Use a remote Ollama instance on the LAN
export KAIT_OLLAMA_HOST=192.168.1.100
export KAIT_OLLAMA_PORT=11434

# Force a specific model
export KAIT_OLLAMA_MODEL=llama3.1:70b

python kait_ai_sidekick.py
```

### 11.2 Data Directory

All sidekick data lives under `~/.kait/`:

```
~/.kait/
  sidekick.db                  # ReasoningBank SQLite database (7 tables)
  sidekick_evolution.json      # Evolution engine state
  sidekick.pid                 # PID file (daemon mode only)
  sidekick_data/               # Sandbox for file_writer tool output
  logs/
    sidekick.log               # Application logs
```

This directory is created automatically on first run. To start completely
fresh, delete the `~/.kait/` directory (or use `--reset` for evolution only).

---

## 12. Extending the System

### 12.1 Adding New Tools

Register a new tool in `lib/sidekick/tools.py`:

```python
def _my_custom_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """My custom tool description.

    Args:
        input_text (str): The input to process.
    """
    text = str(args.get("input_text", "")).strip()
    if not text:
        raise ValueError("Missing 'input_text' argument")

    # Your logic here
    result = text.upper()

    return {"result": result}
```

Then register it in `create_default_registry()`:

```python
registry.register(Tool(
    name="my_custom_tool",
    description="Converts text to uppercase.",
    category="utility",
    _execute_fn=_my_custom_tool,
))
```

The tool is now available via `/tool my_custom_tool hello world` and will
also be auto-detected by the Tool agent during normal conversation.

### 12.2 Adding New Agents

Agents live in `lib/sidekick/agents.py`. To add a new agent:

1. Add a new enum value to `AgentType`:

```python
class AgentType(str, Enum):
    REFLECTION = "reflection"
    CREATIVITY = "creativity"
    LOGIC = "logic"
    TOOL = "tool"
    SENTIMENT = "sentiment"
    MY_AGENT = "my_agent"        # new
```

2. Create a class extending the base `Agent` ABC:

```python
class MyAgent(Agent):
    """Description of what your agent does."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.MY_AGENT

    def process(self, context: Dict[str, Any]) -> AgentResult:
        # Your agent logic here
        message = context.get("message", "")
        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=0.8,
            data={"analysis": "..."},
            prompt_fragments=["Consider this perspective: ..."],
        )
```

3. Register it in the `AgentOrchestrator.__init__` method.

Agents do NOT call LLMs directly. They produce structured data and prompt
fragments that the main loop sends to the LLM. This keeps them fast,
deterministic, and testable.

### 12.3 Custom Personality Traits

Personality traits are stored in the ReasoningBank `personality` table as
key-value pairs with a float value in `[0.0, 1.0]`. You can add custom
traits by saving them directly:

```python
from lib.sidekick.reasoning_bank import get_reasoning_bank

bank = get_reasoning_bank()
bank.save_personality_trait("humor", 0.75)
bank.save_personality_trait("formality", 0.30)
bank.save_personality_trait("verbosity", 0.50)
```

These traits are automatically loaded during system prompt refinement and
influence the sidekick's response style.

---

## 13. Troubleshooting

### Ollama Not Running

**Symptom:** "Could not connect to Ollama" error on startup.

**Fix:**

```bash
# Start Ollama
ollama serve

# Verify it is running
curl http://localhost:11434/api/tags
```

If Ollama is running on a non-default host/port, set the environment
variables:

```bash
export KAIT_OLLAMA_HOST=localhost
export KAIT_OLLAMA_PORT=11434
```

### No Models Available

**Symptom:** "No models found" error on startup.

**Fix:**

```bash
# List available models
ollama list

# Pull a model if none are installed
ollama pull llama3.1:8b
```

### GPU Not Detected

**Symptom:** Slow inference. The sidekick reports CPU-only mode.

**NVIDIA GPU (Linux/Windows):**

```bash
# Verify NVIDIA drivers are installed
nvidia-smi

# If nvidia-smi is not found, install drivers:
# Ubuntu: sudo apt install nvidia-driver-535
# Then restart Ollama
```

**Apple Silicon (macOS):**

GPU acceleration via Metal is automatic. If inference is unexpectedly slow,
verify Ollama is using the correct backend:

```bash
ollama ps
```

**AMD GPU (Linux):**

```bash
# Verify ROCm is installed
rocm-smi --showproductname

# Ollama uses ROCm automatically if detected
```

### Performance Tuning

**Reduce memory usage:**

```bash
# Use a smaller model
ollama pull llama3.1:8b
export KAIT_OLLAMA_MODEL=llama3.1:8b
```

**Speed up inference:**

- Use a GPU-accelerated system (NVIDIA CUDA, Apple Metal, AMD ROCm)
- Use a smaller model (8B vs 70B)
- Increase Ollama's thread count: `OLLAMA_NUM_THREAD=8 ollama serve`
- Reduce conversation history window (currently 10 turns in the chat call)

**Reduce disk usage:**

```bash
# Check model sizes
ollama list

# Remove models you don't need
ollama rm mistral

# Clear sidekick data
rm -rf ~/.kait/sidekick_data/*
```

### Sidekick Runs in Offline Mode

**Symptom:** "Running in offline mode (no LLM)" message.

This means the sidekick could not connect to Ollama. It will still function
with agent-only responses, tool execution, and conversation tracking -- but
LLM-generated responses will be unavailable.

**Fix:** Start Ollama (`ollama serve`) and restart the sidekick.

### Pygame Avatar Not Working

**Symptom:** `--avatar-gui` flag is ignored or produces an error.

**Fix:**

```bash
pip install pygame

# On Linux, you may also need:
sudo apt install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
```

If pygame is not installed, the sidekick silently falls back to text-only
avatar mode. This is by design -- pygame is never a hard requirement.

### Quick Diagnostics

Use the built-in health check to diagnose issues without leaving the session:

```
[You] /health
  === Health Check ===
  [OK]   Python version: 3.12.1
  [OK]   Ollama installed: /usr/local/bin/ollama
  [OK]   Ollama server: running (3 model(s) available)
  [OK]   Models available: llama3.1:8b, llama3:latest, mistral
  [OK]   Data directory: /Users/you/.kait
  [OK]   Disk space: 45.2 GB free
  [OK]   GPU acceleration: Apple Silicon (metal)

  All systems nominal.
```

Or from the command line before launching:

```bash
python kait_ai_sidekick.py --check
```

### Logs

Application logs are written to `~/.kait/logs/sidekick.log`. Check this
file for detailed error information:

```bash
tail -f ~/.kait/logs/sidekick.log
```

---

## 14. CLI Reference

| Flag | Description |
|------|-------------|
| `--check` | Run pre-flight diagnostics and exit (exit code 0 = pass, 1 = fail) |
| `--daemon` | Run with auto-reconnect (writes PID to `~/.kait/sidekick.pid`) |
| `--avatar-gui` | Enable the Pygame graphical avatar window |
| `--status` | Show evolution status and ReasoningBank stats, then exit |
| `--reset` | Reset evolution state to Stage 1 (destructive) |
| `--version` | Show version and exit |

### Environment Variables (v1.3)

| Variable | Default | Description |
|----------|---------|-------------|
| `KAIT_OLLAMA_HOST` | `localhost` | Ollama server hostname |
| `KAIT_OLLAMA_PORT` | `11434` | Ollama server port |
| `KAIT_OLLAMA_MODEL` | *(auto-detect)* | Force a specific model name |
| `KAIT_IDLE_REFLECTION_S` | `30.0` | Seconds between idle reflection cycles |
| `KAIT_AVATAR_TICK_S` | `0.5` | Avatar animation tick interval |
| `KAIT_LLM_TEMPERATURE` | `0.7` | LLM temperature for generation |
| `KAIT_LLM_MAX_TOKENS` | `2048` | Maximum tokens per LLM response |
| `KAIT_NO_STREAM` | *(unset)* | Set to `1` or `true` to disable token streaming |
