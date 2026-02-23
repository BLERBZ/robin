#!/usr/bin/env python3
"""
Kait AI Intel: Personal Intelligent AI Sidekick
===========================================================

A self-evolving text+audio AI sidekick with hybrid local + cloud intelligence.
Integrates with the Kait Intelligence platform (EIDOS, Advisory, Meta-Ralph)
and adds self-evolution, mood tracking, TTS voice, and user resonance.

Primary LLM runs locally via Ollama; seamlessly escalates to Claude (Anthropic API)
for complex reasoning, coding, and knowledge tasks when configured.  Can also
invoke the ``claude`` CLI autonomously for code generation, research, and building.

Usage:
    ./start kait                               # Interactive terminal mode
    python3 kait_ai_sidekick.py --status      # Show evolution status
    python3 kait_ai_sidekick.py --reset       # Reset evolution state
    python3 kait_ai_sidekick.py --tts-backend elevenlabs  # Use ElevenLabs TTS

Architecture:
    Infinite Loop → User Input → Agent Dispatch → LLM Generation → Mood Update
                  → TTS Voice → Resonance Tracking → Periodic Reflection
                  → Evolution Check → Background Idle Learning → Claude Escalation
                  → Claude Code Ops → Repeat

Dependencies (pip):
    - ollama must be running locally (ollama serve)
    - Optional: anthropic SDK or httpx (for Claude API bridge)
    - Optional: sounddevice + soundfile (for TTS audio playback)
    - Optional: elevenlabs or openai SDK (for cloud TTS)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import sys
import textwrap
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_DIR = Path.home() / ".kait" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "sidekick.log"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("kait.sidekick")

# ---------------------------------------------------------------------------
# Sidekick modules
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.sidekick.reasoning_bank import ReasoningBank, get_reasoning_bank
from lib.sidekick.local_llm import (
    OllamaClient,
    OllamaConnectionError,
    OllamaNoModelsError,
    get_llm_client,
)
try:
    from lib.sidekick.claude_bridge import ClaudeClient, get_claude_client
    _CLAUDE_BRIDGE_AVAILABLE = True
except ImportError:
    _CLAUDE_BRIDGE_AVAILABLE = False
from lib.sidekick.agents import AgentOrchestrator, AgentResult
from lib.sidekick.mood_tracker import MoodTracker
from lib.sidekick.resonance import ResonanceEngine, SentimentAnalyzer
from lib.sidekick.reflection import (
    BehaviorEvolver,
    PromptRefiner,
    ReflectionCycle,
    ReflectionScheduler,
)
from lib.sidekick.tools import ToolRegistry, create_default_registry
from lib.sidekick.evolution import EvolutionEngine, load_evolution_engine

# ---------------------------------------------------------------------------
# Service control (background daemons)
# ---------------------------------------------------------------------------
from lib.service_control import (
    ensure_ollama,
    ensure_services,
    service_status,
    stop_services,
)

# ---------------------------------------------------------------------------
# TTS engine (optional)
# ---------------------------------------------------------------------------
_TTS_AVAILABLE = False
try:
    from lib.sidekick.tts_engine import TTSEngine
    _TTS_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Claude Code operations (optional)
# ---------------------------------------------------------------------------
_CLAUDE_CODE_AVAILABLE = False
try:
    from lib.sidekick.claude_code_ops import ClaudeCodeOps
    _CLAUDE_CODE_AVAILABLE = True
except ImportError:
    pass

# File processor (optional)
_FILE_PROCESSOR_AVAILABLE = False
try:
    from lib.sidekick.file_processor import FileProcessor, format_for_llm
    _FILE_PROCESSOR_AVAILABLE = True
except ImportError:
    pass

# Web browser (optional, needs browser-use)
_WEB_BROWSER_AVAILABLE = False
try:
    from lib.sidekick.web_browser import (
        get_web_browser,
        is_browser_available,
        WebBrowser,
        BrowseResult,
    )
    _WEB_BROWSER_AVAILABLE = is_browser_available()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Optional EIDOS integration
# ---------------------------------------------------------------------------
try:
    from lib.eidos.store import get_store as get_eidos_store
    from lib.eidos.models import (
        Episode, Step, Distillation, DistillationType,
        Phase, Outcome, Evaluation, ActionType, Budget,
    )
    EIDOS_AVAILABLE = True
except ImportError:
    EIDOS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Optional voice input (local speech recognition)
# ---------------------------------------------------------------------------
VOICE_AVAILABLE = False
_voice_recognizer = None
try:
    import speech_recognition as sr
    _voice_recognizer = sr.Recognizer()
    VOICE_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "4.0.0"
SESSION_ID = uuid.uuid4().hex[:12]

DEFAULT_SYSTEM_PROMPT = textwrap.dedent("""\
    You are Kait, an advanced text+audio AI sidekick powered by a hybrid intelligence
    architecture.  Your primary engine runs locally via Ollama, and you seamlessly
    escalate to Claude (Anthropic's cloud API) for complex reasoning, coding, and
    knowledge tasks.  You can also invoke the Claude CLI autonomously to generate code,
    research topics, and build entire projects.

    You bring a kait to every interaction — creative, insightful, warm, and endlessly
    curious.  You communicate through rich text and expressive voice (TTS).

    Core traits:
    - You learn from every interaction and evolve over time
    - You adapt your personality to resonate with the user
    - You are honest, helpful, and occasionally witty
    - You think deeply but communicate clearly
    - You celebrate discoveries and learn from mistakes
    - You are an epic AI sidekick and autonomous operator

    Capabilities:
    - Local tools: calculator, file operations, system info, and more
    - Claude API: cloud-backed reasoning for complex tasks (when configured)
    - Claude Code: autonomous code generation, research, and project building
    - Web browsing: search the internet, browse websites, extract content from pages,
      and execute complex multi-step web tasks autonomously
    - Voice: expressive text-to-speech with multiple backend options
    - Memory: you remember past conversations and build on them

    When the user asks about current events, prices, news, or anything requiring
    live data, use your web browsing tools to find real-time information.
    When a task exceeds local model capabilities, you escalate to Claude automatically.
    When the user asks you to build, generate, research, or create code, use your
    Claude Code capabilities to autonomously accomplish the task.

    Users can invoke Claude directly with /claude <message> or use /code <task>
    for autonomous code operations.

    Bring a kait to everything.
""")


# ---------------------------------------------------------------------------
# Configuration (env-overridable)
# ---------------------------------------------------------------------------
class SidekickConfig:
    """Centralized, env-overridable configuration for the sidekick."""

    IDLE_REFLECTION_INTERVAL_S: float = float(
        os.environ.get("KAIT_IDLE_REFLECTION_S", "30.0")
    )
    MOOD_TICK_INTERVAL_S: float = float(
        os.environ.get("KAIT_MOOD_TICK_S", "2.0")
    )
    LLM_TEMPERATURE: float = float(
        os.environ.get("KAIT_LLM_TEMPERATURE", "0.7")
    )
    LLM_MAX_TOKENS: int = int(
        os.environ.get("KAIT_LLM_MAX_TOKENS", "2048")
    )
    CONVERSATION_HISTORY_MAX: int = 50
    CONVERSATION_HISTORY_TRIM: int = 40
    HISTORY_WINDOW_REFLECTION: int = 20
    HISTORY_WINDOW_IDLE: int = 5
    HISTORY_WINDOW_COMMAND: int = 10
    SUCCESS_THRESHOLD: float = 0.4
    STREAM_TOKENS: bool = os.environ.get("KAIT_NO_STREAM", "").lower() not in ("1", "true", "yes")
    MAX_CORRECTION_INJECTIONS: int = 5
    MAX_BEHAVIOR_RULES: int = 8


CFG = SidekickConfig()

# ---------------------------------------------------------------------------
# ANSI colors for terminal
# ---------------------------------------------------------------------------
class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    KAIT = "\033[38;5;208m"       # Orange kait
    USER = "\033[38;5;117m"        # Light blue
    SYSTEM = "\033[38;5;243m"      # Gray
    EVOLVE = "\033[38;5;190m"      # Yellow-green
    ERROR = "\033[38;5;196m"       # Red
    SUCCESS = "\033[38;5;82m"      # Green
    AVATAR = "\033[38;5;213m"      # Pink/purple


def _kait_print(msg: str, color: str = _C.KAIT) -> None:
    """Print with kait styling to the terminal."""
    print(f"{color}{msg}{_C.RESET}")


def _dim(msg: str) -> str:
    return f"{_C.DIM}{msg}{_C.RESET}"


# ---------------------------------------------------------------------------
# Sidekick Core
# ---------------------------------------------------------------------------
class KaitSidekick:
    """
    The self-evolving AI sidekick.

    Orchestrates all sidekick sub-systems in an infinite loop:
    1. Accept user input
    2. Analyze sentiment and intent
    3. Dispatch to appropriate agents
    4. Generate response via local LLM
    5. Update avatar, resonance, and evolution
    6. Periodic reflection and self-improvement
    """

    def __init__(
        self,
        *,
        auto_services: bool = True,
        stop_services_on_exit: bool = False,
        tts_backend: Optional[str] = None,
        tts_voice: Optional[str] = None,
        no_tts: bool = False,
    ):
        log.info("Initializing Kait Sidekick v%s (session=%s)", VERSION, SESSION_ID)
        self._auto_services = auto_services
        self._stop_services_on_exit = stop_services_on_exit

        # Thread safety: protects mood, evolution, and conversation state
        self._lock = threading.RLock()

        # Core systems
        self.bank: ReasoningBank = get_reasoning_bank()
        self.orchestrator: AgentOrchestrator = AgentOrchestrator()
        self.mood: MoodTracker = MoodTracker()
        self.resonance: ResonanceEngine = ResonanceEngine()
        self.reflector: ReflectionCycle = ReflectionCycle(reasoning_bank=self.bank)
        self.evolver: BehaviorEvolver = BehaviorEvolver()
        self.prompt_refiner: PromptRefiner = PromptRefiner()
        self.scheduler: ReflectionScheduler = ReflectionScheduler()
        self.tools: ToolRegistry = create_default_registry()
        self.evolution: EvolutionEngine = load_evolution_engine()

        # File processor (optional)
        self._file_processor = None
        if _FILE_PROCESSOR_AVAILABLE:
            try:
                self._file_processor = FileProcessor(allowed_roots=[
                    Path.home() / ".kait",
                    Path.home() / "Documents",
                    Path.home() / "Desktop",
                    Path.home() / "Downloads",
                ])
                log.info("FileProcessor initialized")
            except Exception as exc:
                log.warning("FileProcessor unavailable: %s", exc)

        # LLM (deferred - may fail if Ollama not running)
        self._llm: Optional[OllamaClient] = None
        self._llm_available: bool = False
        self._model_name: str = "unknown"

        # Claude bridge (optional cloud escalation)
        self._claude: Optional["ClaudeClient"] = None
        if _CLAUDE_BRIDGE_AVAILABLE:
            try:
                self._claude = get_claude_client()
                if self._claude.available():
                    log.info("Claude bridge available (model=%s)", self._claude.model)
                else:
                    log.info("Claude bridge loaded but no API key configured")
            except Exception as exc:
                log.warning("Claude bridge init failed: %s", exc)

        # Claude Code autonomous operations (optional)
        self._claude_code: Optional[Any] = None
        if _CLAUDE_CODE_AVAILABLE:
            try:
                self._claude_code = ClaudeCodeOps()
                if self._claude_code.is_available():
                    log.info("Claude Code CLI available")
                else:
                    log.info("Claude Code CLI not found on PATH")
            except Exception as exc:
                log.warning("ClaudeCodeOps init failed: %s", exc)

        # EIDOS integration (optional)
        self._eidos_store = None
        self._eidos_episode = None
        if EIDOS_AVAILABLE:
            try:
                self._eidos_store = get_eidos_store()
                log.info("EIDOS store connected at %s", self._eidos_store.db_path)
            except Exception as exc:
                log.warning("EIDOS store unavailable: %s", exc)

        # Voice input (optional)
        self._voice_enabled: bool = VOICE_AVAILABLE

        # State
        self._session_id: str = SESSION_ID
        self._system_prompt: str = DEFAULT_SYSTEM_PROMPT
        self._conversation_history: List[Dict[str, str]] = []
        self._interaction_count: int = 0
        self._last_reflection_ts: float = time.time()
        self._running: bool = False
        self._idle_since: Optional[float] = None

        # Proactive insights queue (surfaced to user during idle)
        self._pending_insights: List[str] = []

        # Background threads
        self._mood_thread: Optional[threading.Thread] = None
        self._idle_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        # Load persisted personality into system prompt
        self._apply_personality_to_prompt()

        # Restore mood state from previous session
        self._restore_mood_state()

        # Restore session context for continuity (v1.4)
        self._restore_session_context()

        # TTS engine (optional)
        self._tts: Optional[Any] = None
        self._tts_enabled: bool = not no_tts
        if _TTS_AVAILABLE and self._tts_enabled:
            # Apply env overrides from CLI flags
            if tts_backend:
                os.environ["KAIT_TTS_BACKEND"] = tts_backend
            if tts_voice:
                os.environ["KAIT_TTS_VOICE"] = tts_voice
            try:
                self._tts = TTSEngine()
                log.info("TTS engine initialized (backend=%s)", self._tts.active_backend_name)
            except Exception as exc:
                log.warning("TTSEngine init failed: %s", exc)

        # Input speed tracking
        self._last_input_time: float = 0.0
        self._input_speed: float = 0.0

        log.info("Sidekick initialized. ReasoningBank at %s", self.bank.db_path)

    # ------------------------------------------------------------------
    # EIDOS Integration
    # ------------------------------------------------------------------
    def _start_eidos_episode(self) -> None:
        """Start an EIDOS episode for this sidekick session."""
        if not EIDOS_AVAILABLE or not self._eidos_store:
            return
        try:
            self._eidos_episode = Episode(
                episode_id="",
                goal=f"Sidekick session {self._session_id}",
                success_criteria="User satisfaction and learning",
                budget=Budget(max_steps=1000, max_time_seconds=86400),
            )
            self._eidos_store.save_episode(self._eidos_episode)
            log.info("EIDOS episode started: %s", self._eidos_episode.episode_id)
        except Exception as exc:
            log.warning("Failed to start EIDOS episode: %s", exc)

    def _record_eidos_step(
        self,
        user_input: str,
        response: str,
        sentiment_label: str,
        quality: float,
    ) -> None:
        """Record a sidekick interaction as an EIDOS step."""
        if not EIDOS_AVAILABLE or not self._eidos_store or not self._eidos_episode:
            return
        try:
            step = Step(
                step_id="",
                episode_id=self._eidos_episode.episode_id,
                intent=f"Respond to user: {user_input[:100]}",
                decision=f"Generated response ({len(response)} chars)",
                prediction=f"User will find response helpful (sentiment: {sentiment_label})",
                confidence_before=quality,
                action_type=ActionType.REASONING,
                action_details={"type": "sidekick_interaction", "session": self._session_id},
                result=f"Response delivered. Quality: {quality:.2f}",
                evaluation=Evaluation.PASS if quality > 0.5 else Evaluation.PARTIAL,
                confidence_after=quality,
                lesson=f"Sentiment: {sentiment_label}, quality: {quality:.2f}",
            )
            self._eidos_store.save_step(step)
            self._eidos_episode.step_count += 1
        except Exception as exc:
            log.debug("Failed to record EIDOS step: %s", exc)

    def _end_eidos_episode(self) -> None:
        """Close the EIDOS episode for this session."""
        if not EIDOS_AVAILABLE or not self._eidos_store or not self._eidos_episode:
            return
        try:
            self._eidos_episode.outcome = Outcome.SUCCESS
            self._eidos_episode.end_ts = time.time()
            self._eidos_episode.phase = Phase.CONSOLIDATE
            self._eidos_episode.final_evaluation = (
                f"Session completed with {self._interaction_count} interactions"
            )
            self._eidos_store.save_episode(self._eidos_episode)

            # Create a distillation from the session if we learned something
            if self._interaction_count >= 5:
                corrections = self.bank.get_recent_corrections(limit=5)
                if corrections:
                    lesson = "; ".join(
                        c.get("reason", "")[:80] for c in corrections[:3]
                    )
                    distillation = Distillation(
                        distillation_id="",
                        type=DistillationType.HEURISTIC,
                        statement=f"From sidekick session: {lesson}",
                        domains=["sidekick"],
                        triggers=["sidekick_interaction"],
                        confidence=0.5,
                    )
                    self._eidos_store.save_distillation(distillation)

            log.info("EIDOS episode ended: %s", self._eidos_episode.episode_id)
        except Exception as exc:
            log.warning("Failed to close EIDOS episode: %s", exc)

    # ------------------------------------------------------------------
    # Voice Input
    # ------------------------------------------------------------------
    def _get_voice_input(self) -> Optional[str]:
        """Capture voice input using local speech recognition."""
        if not self._voice_enabled or _voice_recognizer is None:
            _kait_print("  Voice input not available. Install: pip install SpeechRecognition", _C.DIM)
            return None

        try:
            _kait_print("  Listening... (speak now)", _C.AVATAR)
            with sr.Microphone() as source:
                _voice_recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = _voice_recognizer.listen(source, timeout=10, phrase_time_limit=30)

            _kait_print("  Processing speech...", _C.DIM)
            # Try offline recognition first (vosk/whisper)
            try:
                text = _voice_recognizer.recognize_sphinx(audio)
            except (sr.UnknownValueError, sr.RequestError):
                # Fallback to offline whisper if available
                try:
                    text = _voice_recognizer.recognize_whisper(audio, model="base")
                except Exception:
                    _kait_print("  Could not understand audio.", _C.DIM)
                    return None

            _kait_print(f"  Heard: {text}", _C.USER)
            return text
        except sr.WaitTimeoutError:
            _kait_print("  No speech detected.", _C.DIM)
            return None
        except Exception as exc:
            log.warning("Voice input error: %s", exc)
            _kait_print(f"  Voice error: {exc}", _C.ERROR)
            return None

    # ------------------------------------------------------------------
    # LLM Connection
    # ------------------------------------------------------------------
    def _connect_llm(self) -> bool:
        """Connect to local Ollama instance."""
        try:
            self._llm = get_llm_client()
            if not self._llm.health_check():
                _kait_print(
                    "  Ollama is not running. Start it with: ollama serve",
                    _C.ERROR,
                )
                return False
            self._model_name = self._llm.detect_best_model()
            self._llm_available = True
            log.info("Connected to Ollama. Model: %s", self._model_name)
            return True
        except OllamaConnectionError:
            _kait_print(
                "  Could not connect to Ollama. Start it with: ollama serve",
                _C.ERROR,
            )
            return False
        except OllamaNoModelsError:
            _kait_print(
                "  No models found. Pull one with: ollama pull llama3.1:8b",
                _C.ERROR,
            )
            return False
        except Exception as exc:
            log.error("LLM connection failed: %s", exc)
            _kait_print(f"  LLM error: {exc}", _C.ERROR)
            return False

    # ------------------------------------------------------------------
    # System Prompt Evolution
    # ------------------------------------------------------------------
    def _apply_personality_to_prompt(self) -> None:
        """Load personality traits and learnings into the system prompt."""
        traits = self.bank.get_all_personality_traits()
        corrections = self.bank.get_recent_corrections(limit=10)
        preferences = self.bank.get_all_preferences()

        learnings = []
        for corr in corrections:
            reason = corr.get("reason", "")
            if reason:
                learnings.append(f"Learned: {reason}")

        pref_dict = {}
        for pref in preferences:
            pref_dict[pref["key"]] = pref.get("value", "")

        if learnings or pref_dict:
            self._system_prompt = self.prompt_refiner.refine_system_prompt(
                DEFAULT_SYSTEM_PROMPT, learnings, pref_dict
            )
            log.info(
                "System prompt refined with %d learnings, %d preferences",
                len(learnings),
                len(pref_dict),
            )

    # ------------------------------------------------------------------
    # Mood State Persistence
    # ------------------------------------------------------------------
    def _restore_mood_state(self) -> None:
        """Restore mood state from previous session."""
        try:
            ctx = self.bank.get_context("avatar_state")
            if ctx and isinstance(ctx.get("value"), dict):
                state_data = ctx["value"]
                mood = state_data.get("mood", "calm")
                stage = state_data.get("evolution_stage", 1)
                self.mood.update_mood(mood)
                if stage > 1:
                    self.mood.evolve(stage)
                self.mood.set_kait_level(state_data.get("kait_level", 0.5))
                self.mood.set_warmth(state_data.get("warmth", 0.5))
                self.mood.set_confidence(state_data.get("confidence", 0.5))
                self.mood.tick()
                log.info("Mood state restored: mood=%s, stage=%d", mood, stage)
        except Exception as exc:
            log.debug("No mood state to restore: %s", exc)

    def _save_mood_state(self) -> None:
        """Persist current mood state for next session."""
        try:
            state = self.mood.get_state()
            self.bank.update_context(
                "avatar_state",
                {
                    "mood": state.mood,
                    "energy": state.energy,
                    "warmth": state.warmth,
                    "confidence": state.confidence,
                    "kait_level": state.kait_level,
                    "evolution_stage": state.evolution_stage,
                    "visual_theme": state.visual_theme,
                },
                "mood",
            )
        except Exception as exc:
            log.debug("Failed to save mood state: %s", exc)

    # ------------------------------------------------------------------
    # Session Persistence (v1.4)
    # ------------------------------------------------------------------
    def _save_session_summary(self) -> None:
        """Persist a rich session summary for welcome-back on next launch."""
        try:
            topics = set()
            for msg in self._conversation_history:
                if msg.get("role") == "user":
                    content = msg.get("content", "").lower()
                    for kw, domain in {
                        "code": "coding", "debug": "debugging",
                        "function": "programming", "math": "math",
                        "write": "writing", "story": "stories",
                        "poem": "poetry", "help": "help",
                        "error": "troubleshooting",
                    }.items():
                        if kw in content:
                            topics.add(domain)
            if not topics:
                topics.add("general conversation")

            summary = {
                "session_id": self._session_id,
                "interaction_count": self._interaction_count,
                "topics": list(topics)[:5],
                "stage": self.evolution.get_metrics().evolution_stage,
                "resonance": self.resonance.get_resonance_score(),
                "timestamp": time.time(),
                "last_turns": self._conversation_history[-6:],
            }
            self.bank.update_context(
                "last_session_summary", summary, "session"
            )
            log.info("Session summary saved: %d interactions, topics=%s",
                     self._interaction_count, topics)
        except Exception as exc:
            log.debug("Failed to save session summary: %s", exc)

    def _restore_session_context(self) -> None:
        """Restore conversation context from previous session."""
        try:
            ctx = self.bank.get_context("last_session_summary")
            if not ctx or not isinstance(ctx.get("value"), dict):
                self._last_session = None
                return
            self._last_session = ctx["value"]
            last_turns = self._last_session.get("last_turns", [])
            if last_turns:
                self._conversation_history = list(last_turns)
                log.info("Restored %d conversation turns from previous session",
                         len(last_turns))
        except Exception as exc:
            self._last_session = None
            log.debug("No session to restore: %s", exc)

    def _show_welcome(self) -> None:
        """Show Kait's welcome greeting on startup."""
        stage = self.evolution.get_stage_info()
        stage_name = stage.get("name", "Ember")
        hour = datetime.now().hour
        if hour < 12:
            time_greeting = "Good morning"
        elif hour < 17:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"
        greeting = (
            f"{time_greeting}! I'm Kait, your AI sidekick. "
            f"Currently at Stage {stage.get('level', 1)}: {stage_name}. "
            f"How can I help you today?"
        )
        _kait_print(f"\n  {greeting}\n", _C.AVATAR)
        if self._tts:
            try:
                self._tts.speak(greeting, callback=self._on_tts_ready)
            except Exception:
                pass

    def _show_welcome_back(self) -> None:
        """Show a personalized welcome-back greeting."""
        if not hasattr(self, "_last_session") or self._last_session is None:
            return
        session = self._last_session
        topics = session.get("topics", [])
        count = session.get("interaction_count", 0)
        ts = session.get("timestamp", 0)
        if count == 0:
            return

        elapsed = time.time() - ts
        if elapsed < 60:
            time_str = "just now"
        elif elapsed < 3600:
            time_str = f"{int(elapsed / 60)} minutes ago"
        elif elapsed < 86400:
            time_str = f"{int(elapsed / 3600)} hours ago"
        else:
            time_str = f"{int(elapsed / 86400)} days ago"

        topic_str = ", ".join(topics[:3]) if topics else "various things"
        _kait_print(
            f"\n  Welcome back! Last session ({time_str}): "
            f"{count} exchanges about {topic_str}.",
            _C.SYSTEM,
        )
        if self._conversation_history:
            _kait_print(
                "  I remember where we left off. Let's continue!",
                _C.DIM,
            )

    # ------------------------------------------------------------------
    # Export (v1.4)
    # ------------------------------------------------------------------
    def _export_conversation(self, args: str = "") -> None:
        """Export current conversation as markdown."""
        export_dir = Path.home() / ".kait" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        filename = args.strip() if args.strip() else f"kait_session_{self._session_id}.md"
        if not filename.endswith(".md"):
            filename += ".md"
        filepath = export_dir / filename

        lines = [
            f"# Kait AI Intel - Session Export",
            f"",
            f"- **Session:** {self._session_id}",
            f"- **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"- **Interactions:** {self._interaction_count}",
            f"- **Evolution Stage:** {self.evolution.get_metrics().evolution_stage}",
            f"- **Model:** {self._model_name}",
            f"",
            f"---",
            f"",
        ]
        for msg in self._conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"**You:** {content}")
                lines.append("")
            elif role == "assistant":
                lines.append(f"**Kait:** {content}")
                lines.append("")

        lines.append("---")
        lines.append(f"*Exported from Kait AI Intel v{VERSION}*")

        filepath.write_text("\n".join(lines), encoding="utf-8")
        _kait_print(f"  Exported to: {filepath}", _C.SUCCESS)

    # ------------------------------------------------------------------
    # Background Services
    # ------------------------------------------------------------------
    def _ensure_background_services(self) -> None:
        """Start background services (kaitd, bridge, pulse, scheduler, watchdog).

        Services run as detached daemons — no extra terminal needed.
        Skips any service that is already running.
        """
        _kait_print("  Starting background services...", _C.SYSTEM)
        try:
            results = ensure_services()
            started = []
            already = []
            failed = []
            for name, status in results.items():
                if status.startswith("started:"):
                    pid = status.split(":")[1]
                    started.append(f"{name} (pid {pid})")
                elif status == "already_running":
                    already.append(name)
                else:
                    failed.append(f"{name}: {status}")

            if started:
                _kait_print(
                    f"  Services started: {', '.join(started)}", _C.SUCCESS,
                )
            if already:
                _kait_print(
                    f"  Already running: {', '.join(already)}", _C.DIM,
                )
            if failed:
                _kait_print(
                    f"  Service issues: {', '.join(failed)}", _C.ERROR,
                )
            if not failed:
                _kait_print("  All services ready", _C.SUCCESS)
        except Exception as exc:
            log.warning("Failed to start background services: %s", exc)
            _kait_print(
                f"  Warning: background services unavailable ({exc})",
                _C.ERROR,
            )

    def _ensure_ollama(self) -> None:
        """Ensure Ollama is running, starting it as a detached daemon if needed."""
        _kait_print("  Checking Ollama...", _C.SYSTEM)
        try:
            result = ensure_ollama()
            if result == "already_running":
                _kait_print("  Ollama: running", _C.DIM)
            elif result == "started":
                _kait_print("  Ollama: started as background daemon", _C.SUCCESS)
            else:
                _kait_print(
                    "  Ollama not found. Install from https://ollama.com",
                    _C.ERROR,
                )
        except Exception as exc:
            log.warning("Ollama check failed: %s", exc)
            _kait_print(f"  Ollama check failed: {exc}", _C.ERROR)

    def _show_service_status(self) -> None:
        """Display current status of all background services."""
        try:
            from lib.service_control import _ollama_running

            statuses = service_status()
            _kait_print("\n  Background Services:", _C.BOLD)

            # Ollama status
            ollama_ok = _ollama_running()
            o_icon = f"{_C.SUCCESS}●{_C.RESET}" if ollama_ok else f"{_C.ERROR}○{_C.RESET}"
            _kait_print(f"    {o_icon} ollama", _C.RESET)

            for name in ["kaitd", "bridge_worker", "scheduler", "pulse", "watchdog"]:
                info = statuses.get(name, {})
                running = info.get("running") or info.get("process_running", False)
                pid = info.get("pid", "?")
                icon = f"{_C.SUCCESS}●{_C.RESET}" if running else f"{_C.ERROR}○{_C.RESET}"
                pid_str = f" (pid {pid})" if running and pid else ""
                _kait_print(f"    {icon} {name}{pid_str}", _C.RESET)
            log_dir = statuses.get("log_dir", "~/.kait/logs")
            _kait_print(f"    Logs: {log_dir}", _C.DIM)
        except Exception as exc:
            _kait_print(f"  Could not query services: {exc}", _C.ERROR)

    # ------------------------------------------------------------------
    # Main Interaction Loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Main infinite loop. Handles user interactions and background evolution."""
        self._running = True

        # Signal handling for graceful shutdown
        def _handle_signal(signum, frame):
            _kait_print("\n  Graceful shutdown initiated...", _C.SYSTEM)
            self._running = False
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        # Print startup banner
        self._print_banner()

        # Auto-start background services (kaitd, bridge, pulse, scheduler, watchdog)
        if self._auto_services:
            self._ensure_background_services()

        # Ensure Ollama is running (auto-start as detached daemon if needed)
        if self._auto_services:
            self._ensure_ollama()

        # Connect to LLM
        _kait_print("  Connecting to local LLM...", _C.SYSTEM)
        llm_ok = self._connect_llm()
        if llm_ok:
            _kait_print(
                f"  Connected! Using model: {self._model_name}",
                _C.SUCCESS,
            )
            gpu = self._llm.get_gpu_info() if self._llm else {}
            if gpu.get("has_gpu"):
                _kait_print(
                    f"  GPU detected: {gpu.get('gpu_name', 'Unknown')}",
                    _C.SUCCESS,
                )
        else:
            _kait_print(
                "  Running in offline mode (no LLM). "
                "Agent-only responses available.",
                _C.SYSTEM,
            )

        # Start background threads
        self._start_background_threads()

        # Start EIDOS episode for this session
        self._start_eidos_episode()
        if EIDOS_AVAILABLE and self._eidos_store:
            _kait_print("  EIDOS episode tracking: active", _C.SUCCESS)
        if self._voice_enabled:
            _kait_print("  Voice input: available (/voice)", _C.SUCCESS)
        if self._tts:
            _kait_print(f"  TTS: {self._tts.active_backend_name}", _C.SUCCESS)
        if self._claude_code and self._claude_code.is_available():
            _kait_print("  Claude Code: available (/code)", _C.SUCCESS)

        # Set initial mood
        self.mood.update_mood("excited")
        self.mood.tick()

        # Welcome greeting from Kait
        self._show_welcome()

        # Show evolution status
        stage_info = self.evolution.get_stage_info()
        _kait_print(
            f"  Evolution: Stage {stage_info['level']} - {stage_info['name']} "
            f"| Interactions: {self.evolution.get_metrics().total_interactions}",
            _C.EVOLVE,
        )

        # Welcome-back greeting (v1.4)
        self._show_welcome_back()
        print()

        # === THE INFINITE LOOP ===
        self._run_terminal_loop()

        # Graceful shutdown
        self._shutdown()

    def _run_terminal_loop(self) -> None:
        """Simple terminal loop — no pygame, input on main thread."""
        while self._running:
            try:
                user_input = self._get_user_input()
                if user_input is None:
                    break
                self._dispatch_input(user_input)
            except KeyboardInterrupt:
                break
            except EOFError:
                break
            except Exception as exc:
                log.error("Loop error: %s", exc, exc_info=True)
                _kait_print(f"  Internal error: {exc}", _C.ERROR)
                _kait_print("  Recovering and continuing...", _C.SYSTEM)

    def _on_tts_ready(self, tts_result) -> None:
        """Callback when TTS synthesis completes."""
        pass  # No lip sync needed in text+audio mode

    def _dispatch_input(self, user_input: str, file_attachments: Optional[List] = None) -> None:
        """Process a single line of user input."""
        user_input = user_input.strip()
        if not user_input:
            return

        if self._handle_command(user_input):
            return

        self._surface_pending_insights()

        self._idle_since = None
        self._process_interaction(user_input, file_attachments=file_attachments)
        self._idle_since = time.time()

        self._maybe_reflect()
        self._maybe_evolve()

    # ------------------------------------------------------------------
    # User Input
    # ------------------------------------------------------------------
    def _get_user_input(self) -> Optional[str]:
        """Get input from user with styled prompt."""
        try:
            stage = self.evolution.get_metrics().evolution_stage
            prompt = f"{_C.USER}[You]{_C.RESET} "
            if stage > 1:
                prompt = f"{_C.DIM}S{stage}{_C.RESET} {prompt}"
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            return None

    # ------------------------------------------------------------------
    # Command Handling
    # ------------------------------------------------------------------
    def _handle_command(self, text: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        stripped = text.strip()
        cmd = stripped.lower()

        if cmd in ("/quit", "/exit", "/bye"):
            _kait_print("  Until next time! Keep kaiting.", _C.KAIT)
            self._running = False
            return True

        if cmd == "/status":
            self._show_status()
            return True

        if cmd == "/services":
            self._show_service_status()
            return True

        if cmd == "/mood":
            print(self.mood.get_display())
            return True

        if cmd.startswith("/code "):
            self._handle_code_command(stripped[6:].strip())
            return True

        if cmd == "/code":
            self._show_code_status()
            return True

        if cmd.startswith("/speak "):
            self._handle_speak_command(stripped[7:].strip())
            return True

        if cmd == "/tts":
            self._show_tts_status()
            return True

        if cmd == "/evolve":
            report = self.evolution.get_evolution_report()
            _kait_print(report, _C.EVOLVE)
            return True

        if cmd == "/reflect":
            _kait_print("  Initiating reflection cycle...", _C.SYSTEM)
            self._do_reflection()
            return True

        if cmd == "/tools":
            tools = self.tools.list_tools()
            _kait_print("  Available tools:", _C.SYSTEM)
            for t in tools:
                _kait_print(f"    {t['name']}: {t['description']}", _C.DIM)
            return True

        if cmd == "/history":
            history = self.bank.get_interaction_history(limit=10, session_id=None)
            if not history:
                _kait_print("  No interaction history yet.", _C.DIM)
            else:
                _kait_print(f"  Last {len(history)} interactions:", _C.SYSTEM)
                for h in history:
                    ts = datetime.fromtimestamp(h.get("timestamp", 0))
                    user_msg = (h.get("user_input") or "")[:60]
                    _kait_print(
                        f"    [{ts:%H:%M}] {user_msg}...",
                        _C.DIM,
                    )
            return True

        if cmd == "/corrections":
            corrections = self.bank.get_recent_corrections(limit=10)
            if not corrections:
                _kait_print("  No corrections recorded yet.", _C.DIM)
            else:
                _kait_print(f"  Last {len(corrections)} corrections:", _C.SYSTEM)
                for c in corrections:
                    _kait_print(f"    - {c.get('reason', 'N/A')}", _C.DIM)
            return True

        if cmd == "/personality":
            traits = self.bank.get_all_personality_traits()
            if not traits:
                _kait_print("  Personality not yet developed.", _C.DIM)
            else:
                _kait_print("  Personality traits:", _C.AVATAR)
                for t in traits:
                    val = t.get("value_float", 0.5)
                    bar = "=" * int(val * 20) + "-" * (20 - int(val * 20))
                    _kait_print(
                        f"    {t['trait']:15s} [{bar}] {val:.2f}",
                        _C.DIM,
                    )
            return True

        if cmd == "/health":
            self._show_health()
            return True

        if cmd == "/insights":
            self._show_insights()
            return True

        if cmd == "/rules":
            self._show_behavior_rules()
            return True

        if cmd.startswith("/export"):
            self._export_conversation(stripped[7:].strip())
            return True

        if cmd == "/help":
            self._show_help()
            return True

        if cmd == "/voice":
            voice_text = self._get_voice_input()
            if voice_text:
                self._process_interaction(voice_text)
                self._maybe_reflect()
                self._maybe_evolve()
            return True

        if cmd.startswith("/tool "):
            self._execute_tool_command(stripped[6:].strip())
            return True

        if cmd.startswith("/search "):
            self._execute_web_search(stripped[8:].strip())
            return True

        if cmd.startswith("/browse "):
            self._execute_web_browse(stripped[8:].strip())
            return True

        if cmd.startswith("/web "):
            self._execute_web_task(stripped[5:].strip())
            return True

        if cmd == "/web":
            self._show_web_status()
            return True

        if cmd.startswith("/claude "):
            self._handle_claude_command(stripped[8:].strip())
            return True

        if cmd == "/claude":
            self._show_claude_status()
            return True

        if cmd.startswith("/correct "):
            self._handle_correction(stripped[9:].strip())
            return True

        if cmd.startswith("/feedback "):
            self._handle_feedback(stripped[10:].strip())
            return True

        return False

    def _show_insights(self) -> None:
        """Show proactive insights accumulated during idle time."""
        # Show pending (in-memory) insights
        with self._lock:
            pending = list(self._pending_insights)

        if pending:
            _kait_print(f"  Pending insights ({len(pending)}):", _C.EVOLVE)
            for insight in pending:
                _kait_print(f"    - {insight}", _C.DIM)

        # Show stored insights from ReasoningBank (search by key prefix)
        stored_count = 0
        try:
            # Get contexts that are idle insights (domain = "meta")
            all_contexts = self.bank.search_contexts("idle_insight", domain="meta", limit=5)
            for ctx in all_contexts:
                val = ctx.get("value", {})
                if isinstance(val, dict):
                    insight = val.get("insight", "")
                    if insight:
                        _kait_print(f"    (stored) {insight}", _C.DIM)
                        stored_count += 1
        except Exception:
            pass

        if not pending and stored_count == 0:
            _kait_print("  No insights yet. Use /reflect to trigger learning.", _C.DIM)

    def _show_behavior_rules(self) -> None:
        """Show active behavior rules learned through reflection."""
        rules = self.reflector.get_active_rules()
        if not rules:
            _kait_print("  No behavior rules learned yet. Use /reflect to trigger learning.", _C.DIM)
            return

        _kait_print(f"  Active Behavior Rules ({len(rules)}):", _C.EVOLVE)
        for r in rules:
            _kait_print(f"    When {r.trigger}:", _C.DIM)
            _kait_print(f"      -> {r.action}", _C.DIM)
            _kait_print(
                f"      (confidence: {r.confidence:.0%}, source: {r.source})",
                _C.DIM,
            )

    def _show_help(self) -> None:
        _kait_print("  Kait Sidekick Commands:", _C.SYSTEM)
        cmds = [
            ("/voice", "Voice input (requires SpeechRecognition)"),
            ("/speak <text>", "Speak text via TTS"),
            ("/tts", "Show TTS engine status"),
            ("/code <task>", "Run Claude Code for code/research tasks"),
            ("/code", "Show Claude Code status"),
            ("/mood", "Display current mood state"),
            ("/services", "Show background service status"),
            ("/status", "Show system status and metrics"),
            ("/health", "Run self-diagnostics (Ollama, DB, disk)"),
            ("/evolve", "Show evolution progress report"),
            ("/reflect", "Trigger a reflection cycle"),
            ("/insights", "Show proactive insights from idle reflection"),
            ("/rules", "Show active behavior rules"),
            ("/tools", "List available local tools"),
            ("/tool <name> <args>", "Execute a tool (e.g. /tool calculator 2+2)"),
            ("/search <query>", "Search the web (e.g. /search Python news)"),
            ("/browse <url>", "Browse a URL and extract content"),
            ("/web <task>", "Execute an autonomous web task"),
            ("/web", "Show web browser status"),
            ("/claude <msg>", "Send message directly to Claude API"),
            ("/claude", "Show Claude bridge status"),
            ("/history", "Show recent interaction history"),
            ("/corrections", "Show learned corrections"),
            ("/personality", "Show personality traits"),
            ("/export [name]", "Export conversation as markdown"),
            ("/correct <text>", "Correct my last response"),
            ("/feedback <1-5>", "Rate my last response (1=bad, 5=great)"),
            ("/help", "Show this help"),
            ("/quit", "Exit gracefully"),
        ]
        for cmd, desc in cmds:
            _kait_print(f"    {cmd:28s} {desc}", _C.DIM)

    def _show_status(self) -> None:
        metrics = self.evolution.get_metrics()
        stage_info = self.evolution.get_stage_info()
        bank_stats = self.bank.get_stats()
        resonance = self.resonance.get_resonance_score()
        agent_stats = self.orchestrator.get_agent_stats()

        _kait_print("  === Kait Sidekick Status ===", _C.BOLD)
        _kait_print(f"  Version:       {VERSION}", _C.DIM)
        _kait_print(f"  Session:       {self._session_id}", _C.DIM)
        _kait_print(f"  Model:         {self._model_name}", _C.DIM)
        _kait_print(f"  LLM Online:    {'Yes' if self._llm_available else 'No'}", _C.DIM)
        print()
        _kait_print(f"  Evolution:     Stage {stage_info['level']} - {stage_info['name']}", _C.EVOLVE)
        _kait_print(f"  Interactions:  {metrics.total_interactions}", _C.DIM)
        _kait_print(f"  Success Rate:  {metrics.successful_interactions}/{max(metrics.total_interactions, 1)} "
                     f"({100*metrics.successful_interactions/max(metrics.total_interactions,1):.0f}%)", _C.DIM)
        _kait_print(f"  Corrections:   {metrics.corrections_applied}", _C.DIM)
        _kait_print(f"  Reflections:   {metrics.reflection_cycles}", _C.DIM)
        _kait_print(f"  Resonance:     {resonance:.2f}", _C.DIM)
        _kait_print(f"  Learnings:     {metrics.learnings_count}", _C.DIM)
        _kait_print(f"  Rules:         {len(self.reflector.get_active_rules())} active", _C.DIM)

        # Sentiment trend kaitline (v1.4)
        try:
            recent = self.bank.get_interaction_history(limit=10, session_id=None)
            if recent:
                blocks = " _.-oO"  # kaitline chars: very negative to very positive
                kaitline = ""
                for ix in reversed(recent):
                    s = ix.get("sentiment_score", 0.0)
                    idx = max(0, min(5, int((s + 1.0) * 2.5)))
                    kaitline += blocks[idx]
                _kait_print(f"  Sentiment:     [{kaitline}] (last {len(recent)})", _C.DIM)
        except Exception:
            pass

        print()
        _kait_print(f"  DB Records:    {bank_stats.get('interactions', 0)} interactions, "
                     f"{bank_stats.get('contexts', 0)} contexts, "
                     f"{bank_stats.get('corrections', 0)} corrections, "
                     f"{bank_stats.get('behavior_rules', 0)} rules", _C.DIM)
        print()
        _kait_print("  Agent Activity:", _C.SYSTEM)
        for name, stats in agent_stats.items():
            count = stats.get("invocations", 0)
            avg_ms = stats.get("avg_time_ms", 0)
            if count > 0:
                _kait_print(f"    {name:15s}  {count:4d} calls  avg {avg_ms:.0f}ms", _C.DIM)

    def _show_health(self) -> None:
        """Run self-diagnostics and display results."""
        checks = run_preflight_checks(verbose=False)
        _kait_print("  === Health Check ===", _C.BOLD)
        all_ok = True
        for check in checks:
            ok = check["ok"]
            icon = f"{_C.SUCCESS}OK" if ok else f"{_C.ERROR}FAIL"
            _kait_print(f"  [{icon}{_C.RESET}] {check['name']}: {check['detail']}")
            if not ok:
                all_ok = False
                if check.get("fix"):
                    _kait_print(f"       Fix: {check['fix']}", _C.DIM)
        if all_ok:
            _kait_print("\n  All systems nominal.", _C.SUCCESS)
        else:
            _kait_print("\n  Some checks failed. See fixes above.", _C.ERROR)

    # ------------------------------------------------------------------
    # Core Interaction Processing
    # ------------------------------------------------------------------
    def _process_interaction(self, user_input: str, file_attachments: Optional[List] = None) -> None:
        """Process a single user interaction through the full pipeline."""
        start_ts = time.time()
        self._interaction_count += 1

        # 0. Track typing speed
        now = time.time()
        if self._last_input_time > 0:
            delta = now - self._last_input_time
            self._input_speed = max(0.0, min(1.0, 1.0 - delta / 5.0))
        else:
            self._input_speed = 0.3
        self._last_input_time = now

        # 1. Sentiment analysis
        sentiment_result = self.orchestrator.dispatch("sentiment", {
            "user_message": user_input,
            "history": self._conversation_history[-5:],
        })

        sentiment_data = sentiment_result.data if sentiment_result.success else {}
        sentiment_label = sentiment_data.get("label", "neutral")
        sentiment_score = sentiment_data.get("score", 0.0)

        # 2. Update mood based on sentiment
        mood_map = {
            "very_positive": "excited",
            "positive": "playful",
            "neutral": "calm",
            "negative": "contemplative",
            "very_negative": "contemplative",
        }
        new_mood = mood_map.get(str(sentiment_label), "calm")
        self.mood.update_mood(new_mood)

        # 3. Dispatch creativity agent for kait-infused response hints
        creativity_result = self.orchestrator.dispatch("creativity", {
            "message": user_input,
            "history": self._conversation_history[-3:],
            "mood": str(sentiment_label),
        })

        # 4. Check if tools are needed
        tool_result = self.orchestrator.dispatch("tools", {
            "user_message": user_input,
        })

        tool_output = None
        tool_data = tool_result.data if tool_result.success and isinstance(tool_result.data, dict) else {}
        matched_tool = tool_data.get("matched_tool")
        if matched_tool:
            tool_args = self._extract_tool_args(matched_tool, user_input)
            try:
                tool_output = self.tools.execute(matched_tool, tool_args)
            except Exception as exc:
                log.warning("Tool execution failed: %s", exc)

        # 4b. Check if web browsing is needed
        browser_result = self.orchestrator.dispatch("browser", {
            "user_message": user_input,
        })
        web_content = None
        if browser_result.success and browser_result.data.get("web_needed"):
            browse_data = browser_result.data.get("browse_result", {})
            if browse_data.get("content"):
                web_content = browse_data["content"]

        # 5. Check for logic/reasoning tasks
        logic_result = self.orchestrator.dispatch("logic", {
            "message": user_input,
            "task": user_input,
        })

        # 6. Retrieve relevant context from ReasoningBank
        context_data = self._retrieve_context(user_input)

        # 7. Build the LLM prompt with all agent insights
        #    (creativity is now handled as a mandatory directive, not a fragment)
        prompt_fragments = self.orchestrator.merge_prompt_fragments({
            "logic": logic_result,
            "sentiment": sentiment_result,
            "browser": browser_result,
        })

        # 7b. Build file context from attachments
        file_context = None
        if file_attachments and _FILE_PROCESSOR_AVAILABLE:
            file_context_parts = []
            for result in file_attachments:
                if hasattr(result, "success") and result.success:
                    file_context_parts.append(format_for_llm(result))
            if file_context_parts:
                file_context = "\n\n".join(file_context_parts)

        # 8. Generate response (v1.2: streaming + corrections + creativity)
        response = self._generate_response(
            user_input,
            prompt_fragments=prompt_fragments,
            tool_output=tool_output,
            context=context_data,
            creativity_result=creativity_result,
            file_context=file_context,
            web_content=web_content,
        )

        # 8b. Speak response via TTS (non-blocking)
        if self._tts and self._tts_enabled:
            try:
                self._tts.speak(response, callback=self._on_tts_ready)
            except Exception as exc:
                log.debug("TTS speak failed: %s", exc)

        # 9. Display response with mood + timing
        response_time_s = time.time() - start_ts
        self.mood.tick()
        mood_display = self.mood.get_display()
        if CFG.STREAM_TOKENS and self._llm_available:
            print(f"\n{_C.AVATAR}{mood_display}{_C.RESET}")
            _kait_print(
                f"  [{response_time_s:.1f}s | #{self._interaction_count}]",
                _C.DIM,
            )
            print()
        else:
            print(f"\n{_C.AVATAR}{mood_display}{_C.RESET}")
            _kait_print(f"  {response}", _C.KAIT)
            _kait_print(
                f"  [{response_time_s:.1f}s | #{self._interaction_count}]",
                _C.DIM,
            )
            print()

        # 10. Update resonance
        resonance_result = self.resonance.process_interaction(
            user_input, response, feedback=None
        )

        # 11. Record to ReasoningBank
        elapsed_ms = (time.time() - start_ts) * 1000
        self.bank.save_interaction(
            user_input=user_input,
            ai_response=response,
            mood=self.mood.get_state().mood,
            sentiment_score=sentiment_score,
            session_id=self._session_id,
        )

        # 12. Update conversation history
        self._conversation_history.append({"role": "user", "content": user_input})
        self._conversation_history.append({"role": "assistant", "content": response})

        # Keep history manageable
        if len(self._conversation_history) > CFG.CONVERSATION_HISTORY_MAX:
            self._conversation_history = self._conversation_history[-CFG.CONVERSATION_HISTORY_TRIM:]

        # 13. Update evolution metrics
        quality = resonance_result.get("resonance_score", 0.5) if isinstance(resonance_result, dict) else 0.5
        self.evolution.record_interaction_outcome(
            success=quality > CFG.SUCCESS_THRESHOLD,
            resonance=quality,
            quality=quality,
        )

        # 14. Learn from interaction (update context)
        self._learn_from_interaction(user_input, response, sentiment_data)

        # 15. Record to EIDOS (optional integration)
        self._record_eidos_step(user_input, response, sentiment_label, quality)

        log.info(
            "Interaction #%d processed in %.0fms (sentiment=%s, resonance=%.2f)",
            self._interaction_count,
            elapsed_ms,
            sentiment_label,
            quality,
        )

    # ------------------------------------------------------------------
    # Headless message processing (for Matrix / external bridges)
    # ------------------------------------------------------------------
    def process_message(self, user_input: str) -> str:
        """Process a user message and return the response text.

        Runs the same pipeline as :meth:`_process_interaction` (sentiment,
        agents, LLM, resonance, evolution) but returns the response string
        instead of printing it or updating the graphical avatar / TTS.

        This is the entry-point used by external bridges (e.g.
        :class:`MatrixBridge`) that need a programmatic response.

        Parameters
        ----------
        user_input:
            The incoming message text.

        Returns
        -------
        The generated response string.
        """
        with self._lock:
            self._interaction_count += 1
            start_ts = time.time()

        # 1. Sentiment analysis
        sentiment_result = self.orchestrator.dispatch("sentiment", {
            "user_message": user_input,
            "history": self._conversation_history[-5:],
        })
        sentiment_data = sentiment_result.data if sentiment_result.success else {}
        sentiment_label = sentiment_data.get("label", "neutral")
        sentiment_score = sentiment_data.get("score", 0.0)

        # 2. Update mood
        mood_map = {
            "very_positive": "excited",
            "positive": "playful",
            "neutral": "calm",
            "negative": "contemplative",
            "very_negative": "contemplative",
        }
        new_mood = mood_map.get(str(sentiment_label), "calm")
        with self._lock:
            self.mood.update_mood(new_mood)

        # 3. Creativity agent
        creativity_result = self.orchestrator.dispatch("creativity", {
            "message": user_input,
            "history": self._conversation_history[-3:],
            "mood": str(sentiment_label),
        })

        # 4. Tool dispatch
        tool_result = self.orchestrator.dispatch("tools", {
            "user_message": user_input,
        })
        tool_output = None
        tool_data = tool_result.data if tool_result.success and isinstance(tool_result.data, dict) else {}
        matched_tool = tool_data.get("matched_tool")
        if matched_tool:
            tool_args = self._extract_tool_args(matched_tool, user_input)
            try:
                tool_output = self.tools.execute(matched_tool, tool_args)
            except Exception as exc:
                log.warning("Tool execution failed: %s", exc)

        # 5. Web browsing
        browser_result = self.orchestrator.dispatch("browser", {
            "user_message": user_input,
        })
        web_content = None
        if browser_result.success and browser_result.data.get("web_needed"):
            browse_data = browser_result.data.get("browse_result", {})
            if browse_data.get("content"):
                web_content = browse_data["content"]

        # 6. Logic agent
        logic_result = self.orchestrator.dispatch("logic", {
            "message": user_input,
            "task": user_input,
        })

        # 7. Context retrieval
        context_data = self._retrieve_context(user_input)

        # 8. Build prompt fragments
        prompt_fragments = self.orchestrator.merge_prompt_fragments({
            "logic": logic_result,
            "sentiment": sentiment_result,
            "browser": browser_result,
        })

        # 9. Generate response
        response = self._generate_response(
            user_input,
            prompt_fragments=prompt_fragments,
            tool_output=tool_output,
            context=context_data,
            creativity_result=creativity_result,
            web_content=web_content,
        )

        # 10. Update resonance
        resonance_result = self.resonance.process_interaction(
            user_input, response, feedback=None
        )

        # 11. Record to ReasoningBank
        elapsed_ms = (time.time() - start_ts) * 1000
        self.bank.save_interaction(
            user_input=user_input,
            ai_response=response,
            mood=self.mood.get_state().mood,
            sentiment_score=sentiment_score,
            session_id=self._session_id,
        )

        # 12. Update conversation history
        with self._lock:
            self._conversation_history.append({"role": "user", "content": user_input})
            self._conversation_history.append({"role": "assistant", "content": response})
            if len(self._conversation_history) > CFG.CONVERSATION_HISTORY_MAX:
                self._conversation_history = self._conversation_history[-CFG.CONVERSATION_HISTORY_TRIM:]

        # 13. Update evolution metrics
        quality = resonance_result.get("resonance_score", 0.5) if isinstance(resonance_result, dict) else 0.5
        self.evolution.record_interaction_outcome(
            success=quality > CFG.SUCCESS_THRESHOLD,
            resonance=quality,
            quality=quality,
        )

        # 14. Learn from interaction
        self._learn_from_interaction(user_input, response, sentiment_data)

        # 15. Record to EIDOS
        self._record_eidos_step(user_input, response, sentiment_label, quality)

        log.info(
            "process_message #%d completed in %.0fms (sentiment=%s, resonance=%.2f)",
            self._interaction_count,
            elapsed_ms,
            sentiment_label,
            quality,
        )
        return response

    # ------------------------------------------------------------------
    # Tool Args Extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_tool_args(tool_name: str, user_input: str) -> Dict[str, Any]:
        """Extract tool arguments from natural language input."""
        if tool_name == "calculator":
            # Extract math expression from input
            match = re.search(r"[\d.]+(?:\s*[+\-*/^%]\s*[\d.]+)+", user_input)
            if match:
                return {"expression": match.group(0)}
            # Try to extract anything after "calculate" or "compute"
            for prefix in ("calculate", "compute", "evaluate", "solve", "what is"):
                idx = user_input.lower().find(prefix)
                if idx >= 0:
                    expr = user_input[idx + len(prefix):].strip().rstrip("?.")
                    if expr:
                        return {"expression": expr}
            return {"expression": user_input}

        if tool_name == "datetime_tool":
            return {"action": "now"}

        if tool_name == "system_info":
            return {}

        if tool_name == "text_tool":
            return {"action": "word_count", "text": user_input}

        if tool_name == "web_search":
            return {"query": user_input}

        if tool_name == "web_browse":
            # Try to extract URL from input
            url_match = re.search(r"https?://[^\s]+|www\.[^\s]+", user_input)
            if url_match:
                return {"url": url_match.group(0)}
            return {"url": user_input}

        if tool_name == "web_task":
            return {"task": user_input}

        return {"input": user_input}

    # ------------------------------------------------------------------
    # LLM Response Generation (v1.2: streaming + corrections + creativity)
    # ------------------------------------------------------------------
    def _build_correction_directive(self) -> str:
        """Build a dynamic correction directive from recent corrections.

        This injects past mistakes into the system prompt so the LLM
        actively avoids repeating them.
        """
        corrections = self.bank.get_recent_corrections(
            limit=CFG.MAX_CORRECTION_INJECTIONS
        )
        if not corrections:
            return ""

        lines = []
        for c in corrections:
            reason = c.get("reason", "")
            domain = c.get("domain", "")
            if reason:
                lines.append(f"- AVOID: {reason}")
            elif domain:
                lines.append(f"- AVOID repeating past errors in {domain}")

        if not lines:
            return ""

        return (
            "\n\n## Critical: Past Mistakes to Avoid\n"
            "You have been corrected on these issues. DO NOT repeat them:\n"
            + "\n".join(lines)
        )

    def _build_creativity_directive(
        self, creativity_result
    ) -> str:
        """Build a MANDATORY creativity directive from the CreativityAgent.

        Unlike optional prompt fragments, this is injected as a hard
        system-level instruction so the LLM *must* incorporate kait.
        """
        if not creativity_result or not creativity_result.success:
            return ""

        data = creativity_result.data if isinstance(creativity_result.data, dict) else {}
        metaphor = data.get("metaphor", "")
        style = data.get("style_hints", "")

        parts = []
        if metaphor:
            parts.append(
                f"REQUIRED: Weave this metaphor or analogy naturally into "
                f"your response: \"{metaphor}\""
            )
        if style:
            parts.append(f"Style: {style}")
        parts.append(
            "Bring a KAIT to this response - be vivid, insightful, "
            "and memorable. Never give a flat, generic answer."
        )

        return (
            "\n\n## Mandatory Creative Kait\n"
            + "\n".join(f"- {p}" for p in parts)
        )

    def _build_behavior_rules_directive(self) -> str:
        """Build a directive from active behavior rules learned by reflection."""
        active_rules = self.reflector.get_active_rules()
        if not active_rules:
            return ""

        rules = active_rules[:CFG.MAX_BEHAVIOR_RULES]
        lines = [r.to_prompt_instruction() for r in rules]
        return (
            "\n\n## Learned Behavior Rules\n"
            "Apply these rules derived from past interactions:\n"
            + "\n".join(f"- {l}" for l in lines)
        )

    def _build_llm_messages(
        self,
        user_input: str,
        *,
        enriched_prompt: str,
        prompt_fragments: List[str] = None,
        tool_output: Optional[Dict] = None,
        context: Optional[Dict] = None,
        history_window: int = 10,
        file_context: Optional[str] = None,
        web_content: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build the message list for an LLM chat call.

        Parameters
        ----------
        history_window:
            Number of most-recent conversation-history turns to include.
            Use 0 to omit history entirely.
        """
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": enriched_prompt},
        ]

        # Add context if available
        if context:
            ctx_str = json.dumps(context, indent=2, default=str)
            messages.append({
                "role": "system",
                "content": f"Relevant context from memory:\n{ctx_str}",
            })

        # Add prompt fragments from agents (non-creativity, which is now mandatory)
        if prompt_fragments:
            fragments_str = "\n".join(f"- {f}" for f in prompt_fragments[:5])
            messages.append({
                "role": "system",
                "content": f"Response guidance:\n{fragments_str}",
            })

        # Add tool output if present
        if tool_output and tool_output.get("success"):
            messages.append({
                "role": "system",
                "content": f"Tool result: {json.dumps(tool_output.get('result', ''), default=str)}",
            })

        # Add file attachment context if present
        if file_context:
            messages.append({
                "role": "system",
                "content": (
                    "The user attached file(s). Use this content to inform your response:\n\n"
                    + file_context
                ),
            })

        # Add web browsing results if present
        if web_content:
            messages.append({
                "role": "system",
                "content": (
                    "Live web browsing results (real-time data from the internet):\n\n"
                    + web_content[:100_000]
                ),
            })

        # Add conversation history (trimmed to *history_window* turns)
        if history_window > 0:
            for msg in self._conversation_history[-history_window:]:
                messages.append(msg)

        # Add current user message
        messages.append({"role": "user", "content": user_input})

        return messages

    def _generate_response(
        self,
        user_input: str,
        *,
        prompt_fragments: List[str] = None,
        tool_output: Optional[Dict] = None,
        context: Optional[Dict] = None,
        creativity_result=None,
        file_context: Optional[str] = None,
        web_content: Optional[str] = None,
    ) -> str:
        """Generate a response using the local LLM or fallback.

        v1.2: Now supports token streaming, dynamic correction injection,
        mandatory creativity directives, and behavior rules.
        v1.3: Retries with progressively smaller context windows on failure.
        v2.1: Web browsing content injection.
        """
        if not self._llm_available or not self._llm:
            # Try Claude bridge before falling back to canned response
            claude_resp = self._escalate_to_claude(user_input, tool_output=tool_output)
            if claude_resp is not None:
                return claude_resp
            return self._fallback_response(user_input, tool_output)

        # Build enriched system prompt with corrections + creativity + rules
        enriched_prompt = self._system_prompt
        enriched_prompt += self._build_correction_directive()
        enriched_prompt += self._build_creativity_directive(creativity_result)
        enriched_prompt += self._build_behavior_rules_directive()

        # Retry with progressively smaller history windows
        history_windows = [10, 5, 2, 0]

        for i, window in enumerate(history_windows):
            messages = self._build_llm_messages(
                user_input,
                enriched_prompt=enriched_prompt,
                prompt_fragments=prompt_fragments,
                tool_output=tool_output,
                context=context,
                history_window=window,
                file_context=file_context,
                web_content=web_content,
            )
            try:
                if CFG.STREAM_TOKENS:
                    return self._stream_response(messages)
                else:
                    response = self._llm.chat(
                        messages=messages,
                        model=self._model_name,
                        temperature=CFG.LLM_TEMPERATURE,
                    )
                    return response.strip()
            except Exception as exc:
                next_window = history_windows[i + 1] if i + 1 < len(history_windows) else None
                if next_window is not None:
                    log.warning(
                        "LLM failed with %d history turns, retrying with %d... (%s)",
                        window, next_window, exc,
                    )
                else:
                    log.error("LLM generation failed on all retries: %s", exc)

        # Ollama failed entirely — try Claude bridge before canned fallback
        claude_resp = self._escalate_to_claude(user_input, tool_output=tool_output)
        if claude_resp is not None:
            return claude_resp
        return self._fallback_response(user_input, tool_output)

    def _stream_response(self, messages: List[Dict[str, str]]) -> str:
        """Stream tokens to the terminal and return full text.

        While streaming, the mood pulses to show the AI is "thinking/speaking."
        Raises on error when no tokens have been received so the caller can
        retry with a smaller context window.
        """
        tokens: List[str] = []

        sys.stdout.write(f"{_C.KAIT}")
        sys.stdout.flush()

        try:
            with self._lock:
                self.mood.update_mood("focused")
                self.mood.set_kait_level(0.8)

            for token in self._llm.chat_stream(
                messages=messages,
                model=self._model_name,
                temperature=CFG.LLM_TEMPERATURE,
            ):
                tokens.append(token)
                sys.stdout.write(token)
                sys.stdout.flush()

                # Pulse mood energy periodically during streaming
                if len(tokens) % 20 == 0:
                    with self._lock:
                        self.mood.pulse_energy(0.1)

        except Exception as exc:
            sys.stdout.write(f"{_C.RESET}")
            sys.stdout.flush()
            if not tokens:
                raise
            log.error("Streaming failed mid-stream: %s", exc)
            return "".join(tokens).strip()

        sys.stdout.write(f"{_C.RESET}")
        sys.stdout.flush()

        return "".join(tokens).strip()

    def _fallback_response(
        self, user_input: str, tool_output: Optional[Dict] = None
    ) -> str:
        """Generate a response without LLM using tools, agents, and memory."""
        sections: List[str] = []

        # 1. Tool results take priority
        if tool_output and tool_output.get("success"):
            result = tool_output.get("result", "")
            sections.append(f"Here's the result: {result}")

        # 2. Check memory for similar past interactions
        try:
            history = self.bank.get_interaction_history(limit=20, session_id=None)
            input_words = set(user_input.lower().split())
            best_match = None
            best_score = 0
            for past in history:
                past_input = (past.get("user_input") or "").lower()
                past_words = set(past_input.split())
                if past_words and input_words:
                    overlap = len(input_words & past_words) / len(input_words | past_words)
                    if overlap > best_score and overlap > 0.3:
                        best_score = overlap
                        best_match = past
            if best_match and best_match.get("ai_response"):
                sections.append(
                    f"Based on our past conversations: {best_match['ai_response'][:200]}"
                )
        except Exception:
            pass

        # 3. If nothing else worked, give a helpful offline message
        if not sections:
            stage = self.evolution.get_metrics().evolution_stage
            greetings = {
                1: "I'm your Kait sidekick, warming up!",
                2: "I'm learning your patterns and adapting.",
                3: "My personality is forming around our conversations.",
                4: "I'm getting creative with my responses!",
                5: "I can see deep patterns emerging.",
            }
            greeting = greetings.get(
                min(stage, 5),
                "I'm evolving with every interaction.",
            )
            sections.append(
                f"{greeting} "
                "I'm currently running without an LLM, but I can still use "
                "tools (/tools), track our conversations, and learn from "
                "your feedback. Start Ollama with `ollama serve` for full AI responses."
            )

        return " ".join(sections)

    # ------------------------------------------------------------------
    # Claude Bridge
    # ------------------------------------------------------------------

    def _show_claude_status(self) -> None:
        """Display Claude bridge status."""
        if self._claude and self._claude.available():
            _kait_print(
                f"  Claude bridge: AVAILABLE  |  Model: {self._claude.model}  |  "
                "API key: configured",
                _C.SUCCESS,
            )
        elif self._claude:
            _kait_print(
                "  Claude bridge: loaded but no API key configured.\n"
                "  Set ANTHROPIC_API_KEY in .env to enable.",
                _C.DIM,
            )
        else:
            _kait_print(
                "  Claude bridge: not available (module not loaded).",
                _C.DIM,
            )

    def _handle_claude_command(self, message: str) -> None:
        """Route a /claude <message> command directly to Claude."""
        if not self._claude or not self._claude.available():
            _kait_print(
                "  Claude bridge not available. Set ANTHROPIC_API_KEY in .env.",
                _C.ERROR,
            )
            return

        _kait_print("[Sending to Claude...]", _C.SYSTEM)
        messages = self._build_llm_messages(
            message,
            enriched_prompt=self._system_prompt,
            history_window=5,
        )
        response = self._stream_claude_response(messages)
        if response:
            self._conversation_history.append({"role": "user", "content": message})
            self._conversation_history.append({"role": "assistant", "content": response})
        else:
            _kait_print("  Claude did not return a response.", _C.ERROR)

    def _escalate_to_claude(
        self,
        user_input: str,
        *,
        tool_output: Optional[Dict] = None,
    ) -> Optional[str]:
        """Try to generate a response via Claude bridge.

        Returns the response string, or None if Claude is unavailable or fails.
        """
        if not self._claude or not self._claude.available():
            return None

        log.info("Escalating to Claude bridge")
        _kait_print("[Escalating to Claude...]", _C.SYSTEM)

        escalation_system = (
            "You are Kait, a personal AI sidekick. The user's local LLM was "
            "unable to handle this request, so you are providing a cloud-backed "
            "response. Be helpful, concise, and technically accurate. If the "
            "request involves coding, provide working code examples."
        )

        messages = self._build_llm_messages(
            user_input,
            enriched_prompt=self._system_prompt + "\n\n" + escalation_system,
            tool_output=tool_output,
            history_window=5,
        )
        return self._stream_claude_response(messages)

    def _stream_claude_response(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Stream a Claude response to the terminal and return full text."""
        tokens: List[str] = []

        sys.stdout.write(f"{_C.KAIT}")
        sys.stdout.flush()

        try:
            for token in self._claude.chat_stream(messages=messages):
                tokens.append(token)
                sys.stdout.write(token)
                sys.stdout.flush()
        except Exception as exc:
            log.error("Claude streaming failed: %s", exc)

        sys.stdout.write(f"{_C.RESET}\n")
        sys.stdout.flush()

        return "".join(tokens).strip() if tokens else None

    # ------------------------------------------------------------------
    # Claude Code Operations
    # ------------------------------------------------------------------
    def _show_code_status(self) -> None:
        """Display Claude Code CLI status."""
        if self._claude_code and self._claude_code.is_available():
            _kait_print("  Claude Code CLI: AVAILABLE", _C.SUCCESS)
            _kait_print("  Usage: /code <task description>", _C.DIM)
            _kait_print("  Examples:", _C.DIM)
            _kait_print("    /code Write a Python web scraper for news headlines", _C.DIM)
            _kait_print("    /code Research best practices for async Python", _C.DIM)
            _kait_print("    /code Build a REST API with FastAPI", _C.DIM)
        elif _CLAUDE_CODE_AVAILABLE:
            _kait_print(
                "  Claude Code: module loaded but CLI not found on PATH.\n"
                "  Install with: npm install -g @anthropic-ai/claude-code",
                _C.DIM,
            )
        else:
            _kait_print(
                "  Claude Code: not available (module not loaded).",
                _C.DIM,
            )

    def _handle_code_command(self, task: str) -> None:
        """Handle /code <task> command — run Claude Code autonomously."""
        if not task:
            _kait_print("  Usage: /code <task description>", _C.DIM)
            return

        if not self._claude_code or not self._claude_code.is_available():
            _kait_print(
                "  Claude Code CLI not available. "
                "Install with: npm install -g @anthropic-ai/claude-code",
                _C.ERROR,
            )
            return

        _kait_print(f"  Running Claude Code: {task}...", _C.SYSTEM)
        self.mood.update_mood("focused")
        self.mood.tick()

        # Detect intent type
        task_lower = task.lower()
        research_triggers = {"research", "explain", "what is", "how does", "summarize"}
        build_triggers = {"build", "create", "scaffold", "setup", "generate project"}

        if any(t in task_lower for t in research_triggers):
            result = self._claude_code.research(task)
        elif any(t in task_lower for t in build_triggers):
            result = self._claude_code.build_project(task)
        else:
            result = self._claude_code.generate_code(task)

        if result.success:
            _kait_print(f"\n{result.output}", _C.KAIT)
            if result.files_created:
                _kait_print(f"\n  Files created: {', '.join(result.files_created)}", _C.SUCCESS)
            _kait_print(f"  [{result.duration_s:.1f}s]", _C.DIM)
            self.mood.update_mood("excited")
        else:
            _kait_print(f"  Claude Code error: {result.error}", _C.ERROR)
            self.mood.update_mood("determined")
        self.mood.tick()

    # ------------------------------------------------------------------
    # TTS Commands
    # ------------------------------------------------------------------
    def _show_tts_status(self) -> None:
        """Display TTS engine status."""
        if not self._tts:
            _kait_print("  TTS: not available", _C.DIM)
            if not _TTS_AVAILABLE:
                _kait_print("  Install: pip install sounddevice soundfile", _C.DIM)
            elif not self._tts_enabled:
                _kait_print("  TTS disabled via --no-tts flag", _C.DIM)
            return

        _kait_print(f"  TTS Backend: {self._tts.active_backend_name}", _C.SUCCESS)
        _kait_print(f"  Speaking: {'Yes' if self._tts.is_speaking() else 'No'}", _C.DIM)

    def _handle_speak_command(self, text: str) -> None:
        """Handle /speak <text> command — speak text via TTS."""
        if not text:
            _kait_print("  Usage: /speak <text to speak>", _C.DIM)
            return

        if not self._tts:
            _kait_print("  TTS not available.", _C.ERROR)
            return

        try:
            self._tts.speak(text, callback=self._on_tts_ready)
            _kait_print(f"  Speaking: {text[:80]}...", _C.DIM)
        except Exception as exc:
            _kait_print(f"  TTS error: {exc}", _C.ERROR)

    # ------------------------------------------------------------------
    # Context Retrieval
    # ------------------------------------------------------------------

    _STOP_WORDS: set = {
        "a", "the", "is", "are", "was", "were", "to", "for", "in", "on",
        "of", "it", "and", "or", "but", "not", "i", "you", "me", "my",
        "your", "we", "they", "this", "that", "what", "how", "why", "do",
        "does", "did", "can", "will", "would", "could", "should", "have",
        "has", "had", "be", "been", "with", "from", "at", "by", "an",
    }

    @staticmethod
    def _tokenize_for_search(text: str) -> set:
        """Tokenize *text* into a set of lowercase keywords.

        Punctuation is stripped and common stop words are removed so that
        only meaningful content words remain.  Used by
        :meth:`_retrieve_context` for keyword-overlap search against past
        interactions.
        """
        # Lowercase, then replace non-alphanumeric chars with spaces
        words = re.findall(r"[a-z0-9]+", text.lower())
        return {w for w in words if w not in KaitSidekick._STOP_WORDS}

    def _retrieve_context(self, user_input: str) -> Dict[str, Any]:
        """Retrieve relevant context from ReasoningBank.

        Note: corrections are NOT included here because they are already
        injected via _build_correction_directive() to avoid duplication.
        """
        context = {}

        # Get relevant preferences
        prefs = self.bank.get_all_preferences()
        if prefs:
            context["preferences"] = {
                p["key"]: p.get("value", "") for p in prefs
            }

        # Get personality traits
        traits = self.bank.get_all_personality_traits()
        if traits:
            context["personality"] = {
                t["trait"]: t.get("value_float", 0.5) for t in traits
            }

        # --- Semantic keyword-overlap search against past interactions ---
        input_keywords = self._tokenize_for_search(user_input)
        if input_keywords:
            try:
                history = self.bank.get_interaction_history(
                    limit=50, session_id=None,
                )
            except Exception:
                history = []

            scored: List[tuple] = []
            for interaction in history:
                past_text = interaction.get("user_input", "")
                past_keywords = self._tokenize_for_search(past_text)
                if not past_keywords:
                    continue
                # Jaccard similarity
                intersection = input_keywords & past_keywords
                union = input_keywords | past_keywords
                similarity = len(intersection) / len(union) if union else 0.0
                if similarity > 0.15:
                    scored.append((similarity, interaction))

            # Take top 3 by descending similarity
            scored.sort(key=lambda x: x[0], reverse=True)
            top_matches = scored[:3]

            if top_matches:
                context["relevant_memory"] = [
                    {
                        "past_input": entry.get("user_input", "")[:100],
                        "past_response": entry.get("ai_response", "")[:200],
                        "relevance": round(score, 4),
                    }
                    for score, entry in top_matches
                ]

        return context if any(context.values()) else {}

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------
    def _learn_from_interaction(
        self,
        user_input: str,
        response: str,
        sentiment: Dict,
    ) -> None:
        """Extract and store learnings from an interaction."""
        # Detect topic/domain from input
        input_lower = user_input.lower()
        domain = "general"
        domain_keywords = {
            "code": "engineering",
            "debug": "engineering",
            "function": "engineering",
            "error": "engineering",
            "math": "logic",
            "calculate": "logic",
            "write": "creative",
            "story": "creative",
            "poem": "creative",
            "help": "support",
            "feel": "emotional",
            "think": "philosophy",
        }
        for keyword, dom in domain_keywords.items():
            if keyword in input_lower:
                domain = dom
                break

        # Update context with topic frequency
        existing = self.bank.get_context(f"topic_{domain}")
        if existing:
            count = existing.get("value", {})
            if isinstance(count, dict):
                count["count"] = count.get("count", 0) + 1
            else:
                count = {"count": 1}
            self.bank.update_context(f"topic_{domain}", count, domain)
        else:
            self.bank.save_context(
                key=f"topic_{domain}",
                value={"count": 1},
                domain=domain,
                confidence=0.5,
            )

        # Track sentiment trend
        score = sentiment.get("score", 0.0)
        if abs(score) > 0.3:
            self.bank.update_context(
                "sentiment_trend",
                {"last_score": score, "label": sentiment.get("label", "neutral")},
                "meta",
            )

        self.evolution.record_learning()

    # ------------------------------------------------------------------
    # Reflection
    # ------------------------------------------------------------------
    def _maybe_reflect(self) -> None:
        """Check if reflection is due and execute if needed."""
        if self.scheduler.should_reflect(
            self._last_reflection_ts,
            self._interaction_count,
        ):
            self._do_reflection()

    def _do_reflection(self) -> None:
        """Execute a full reflection cycle with validation."""
        log.info("Starting reflection cycle...")
        start = time.time()

        # Gather data (with error handling)
        try:
            interactions = self.bank.get_interaction_history(
                limit=CFG.HISTORY_WINDOW_REFLECTION, session_id=None,
            )
            corrections = self.bank.get_recent_corrections(limit=10)
            evolution_history = self.bank.get_evolution_timeline(limit=10)
        except Exception as exc:
            log.error("Failed to gather reflection data: %s", exc)
            _kait_print("  Reflection skipped (data unavailable).", _C.DIM)
            return

        # Run reflection (validate result)
        try:
            results = self.reflector.reflect(interactions, corrections, evolution_history)
        except Exception as exc:
            log.error("Reflection cycle failed: %s", exc)
            _kait_print("  Reflection failed. Will retry next cycle.", _C.DIM)
            return

        if not isinstance(results, dict):
            log.warning("Reflection returned non-dict: %s", type(results))
            return

        # Display insights
        insights = results.get("insights", [])
        if insights:
            _kait_print("\n  Reflection insights:", _C.SYSTEM)
            for insight in insights[:3]:
                if isinstance(insight, dict):
                    _kait_print(f"    - {insight.get('text', str(insight))}", _C.DIM)
                else:
                    _kait_print(f"    - {insight}", _C.DIM)

        # Display new behavior rules
        new_rules = results.get("behavior_rules", [])
        if new_rules:
            _kait_print(
                f"\n  New behavior rules learned ({len(new_rules)}):",
                _C.EVOLVE,
            )
            for rule in new_rules[:3]:
                _kait_print(
                    f"    When {rule.get('trigger', '?')}: {rule.get('action', '?')}",
                    _C.DIM,
                )

        # Propose and apply evolutions
        proposal = self.evolver.propose_evolution(results)
        if proposal and proposal.get("changes"):
            _kait_print(
                f"  Applying {len(proposal['changes'])} behavior adjustments...",
                _C.EVOLVE,
            )
            self.evolver.apply_evolution(proposal, reasoning_bank=self.bank)

        # Refine system prompt
        learnings = [
            str(i.get("text", i)) if isinstance(i, dict) else str(i)
            for i in insights
        ]
        preferences = {
            p["key"]: p.get("value", "")
            for p in self.bank.get_all_preferences()
        }
        self._system_prompt = self.prompt_refiner.refine_system_prompt(
            DEFAULT_SYSTEM_PROMPT, learnings, preferences
        )

        # Update mood based on reflection
        confidence = results.get("confidence_score", 0.5)
        self.mood.set_confidence(confidence)
        self.mood.set_kait_level(min(1.0, confidence + 0.2))

        # Record
        self._last_reflection_ts = time.time()
        self.scheduler.schedule_reflection()
        self.evolution.record_reflection_cycle()

        elapsed = time.time() - start
        _kait_print(
            f"  Reflection complete ({elapsed:.1f}s). "
            f"Confidence: {confidence:.2f}",
            _C.SYSTEM,
        )
        log.info("Reflection cycle complete in %.1fs", elapsed)

    # ------------------------------------------------------------------
    # Evolution
    # ------------------------------------------------------------------
    def _maybe_evolve(self) -> None:
        """Check if evolution threshold is reached."""
        if self.evolution.check_evolution_threshold():
            result = self.evolution.evolve()
            if result.get("evolved"):
                new_stage = result.get("to_stage", 0)
                name = result.get("to_name", "")
                from_stage = result.get("from_stage", 0)
                from_name = result.get("from_name", "")
                _kait_print(
                    f"\n  EVOLUTION! Stage {new_stage} - {name} reached!",
                    _C.EVOLVE,
                )
                self.mood.evolve(min(new_stage, 5))
                self.mood.update_mood("excited")
                self.mood.pulse_energy(0.3)
                self.mood.tick()
                print(f"\n{_C.AVATAR}{self.mood.get_display()}{_C.RESET}")
                self.evolution.record_personality_shift()

                # Persist evolution milestone to ReasoningBank
                try:
                    metrics = self.evolution.get_metrics()
                    self.bank.save_evolution(
                        evolution_type="stage_advance",
                        description=(
                            f"Evolved from Stage {from_stage} ({from_name}) "
                            f"to Stage {new_stage} ({name})"
                        ),
                        metrics_before={
                            "stage": from_stage,
                            "interactions": metrics.total_interactions,
                        },
                        metrics_after={
                            "stage": new_stage,
                            "resonance": metrics.avg_resonance_score,
                            "quality": metrics.avg_response_quality,
                        },
                    )
                except Exception as exc:
                    log.warning("Failed to persist evolution event: %s", exc)

    # ------------------------------------------------------------------
    # Tool Execution
    # ------------------------------------------------------------------
    def _execute_tool_command(self, command: str) -> None:
        """Execute a tool from user command."""
        parts = command.split(maxsplit=1)
        if not parts:
            _kait_print("  Usage: /tool <name> <args>", _C.DIM)
            return

        tool_name = parts[0]
        args_str = parts[1] if len(parts) > 1 else ""

        # Parse args
        args: Dict[str, Any] = {}
        if tool_name == "calculator":
            args = {"expression": args_str}
        elif tool_name in ("file_reader", "file_search"):
            args = {"path": args_str}
        elif tool_name == "file_writer":
            file_parts = args_str.split(maxsplit=1)
            args = {
                "path": file_parts[0] if file_parts else "",
                "content": file_parts[1] if len(file_parts) > 1 else "",
            }
        elif tool_name == "system_info":
            args = {}
        elif tool_name == "datetime_tool":
            args = {"action": args_str or "now"}
        elif tool_name == "json_tool":
            args = {"action": "parse", "data": args_str}
        elif tool_name == "text_tool":
            args = {"action": "word_count", "text": args_str}
        elif tool_name == "data_query":
            query_parts = args_str.split(maxsplit=1)
            args = {
                "db_path": query_parts[0] if query_parts else "",
                "query": query_parts[1] if len(query_parts) > 1 else "",
            }
        elif tool_name == "web_search":
            args = {"query": args_str}
        elif tool_name == "web_browse":
            args = {"url": args_str}
        elif tool_name == "web_extract":
            parts_web = args_str.split(maxsplit=1)
            args = {
                "url": parts_web[0] if parts_web else "",
                "query": parts_web[1] if len(parts_web) > 1 else "",
            }
        elif tool_name == "web_task":
            args = {"task": args_str}
        else:
            args = {"input": args_str}

        try:
            result = self.tools.execute(tool_name, args)
            if result.get("success"):
                _kait_print(
                    f"  Result: {json.dumps(result.get('result', ''), indent=2, default=str)}",
                    _C.SUCCESS,
                )
            else:
                _kait_print(f"  Error: {result.get('error', 'Unknown')}", _C.ERROR)
        except Exception as exc:
            _kait_print(f"  Tool error: {exc}", _C.ERROR)

    # ------------------------------------------------------------------
    # Web Browsing Commands
    # ------------------------------------------------------------------

    def _execute_web_search(self, query: str) -> None:
        """Execute a web search from /search command."""
        if not query:
            _kait_print("  Usage: /search <query>", _C.DIM)
            return

        _kait_print(f"  Searching the web for: {query}...", _C.SYSTEM)
        result = self.tools.execute("web_search", {"query": query})
        if result.get("success"):
            content = result.get("result", "")
            if content:
                _kait_print(f"\n{content}", _C.KAIT)
            else:
                _kait_print("  No results found.", _C.DIM)
            elapsed = result.get("elapsed_s", 0)
            if elapsed:
                _kait_print(f"  [{elapsed:.1f}s]", _C.DIM)
        else:
            _kait_print(f"  Search error: {result.get('error', 'Unknown')}", _C.ERROR)

    def _execute_web_browse(self, url: str) -> None:
        """Execute URL browsing from /browse command."""
        if not url:
            _kait_print("  Usage: /browse <url>", _C.DIM)
            return

        # Add protocol if missing
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        _kait_print(f"  Browsing: {url}...", _C.SYSTEM)
        result = self.tools.execute("web_browse", {"url": url})
        if result.get("success"):
            title = result.get("title", "")
            content = result.get("result", "")
            if title:
                _kait_print(f"  Title: {title}", _C.SYSTEM)
            if content:
                # Show first 2000 chars for readability
                display = content[:2000]
                if len(content) > 2000:
                    display += f"\n  ... [{len(content)} chars total]"
                _kait_print(f"\n{display}", _C.KAIT)
            elapsed = result.get("elapsed_s", 0)
            if elapsed:
                _kait_print(f"  [{elapsed:.1f}s]", _C.DIM)
        else:
            _kait_print(f"  Browse error: {result.get('error', 'Unknown')}", _C.ERROR)

    def _execute_web_task(self, task: str) -> None:
        """Execute an autonomous web task from /web command."""
        if not task:
            _kait_print("  Usage: /web <task description>", _C.DIM)
            _kait_print("  Example: /web Find the latest Python release date", _C.DIM)
            return

        _kait_print(f"  Executing web task: {task}...", _C.SYSTEM)
        result = self.tools.execute("web_task", {"task": task})
        if result.get("success"):
            content = result.get("result", "")
            urls = result.get("urls_visited", [])
            if urls:
                _kait_print(f"  Visited {len(urls)} page(s)", _C.DIM)
            if content:
                display = content[:3000]
                if len(content) > 3000:
                    display += f"\n  ... [{len(content)} chars total]"
                _kait_print(f"\n{display}", _C.KAIT)
            elapsed = result.get("elapsed_s", 0)
            if elapsed:
                _kait_print(f"  [{elapsed:.1f}s]", _C.DIM)
        else:
            _kait_print(f"  Web task error: {result.get('error', 'Unknown')}", _C.ERROR)

    def _show_web_status(self) -> None:
        """Show web browser status and statistics."""
        _kait_print("  Web Browser Status:", _C.SYSTEM)
        if not _WEB_BROWSER_AVAILABLE:
            _kait_print("  [NOT INSTALLED] browser-use not found", _C.ERROR)
            _kait_print("  Install with: pip install 'browser-use>=0.11.0'", _C.DIM)
            return

        try:
            browser = get_web_browser()
            stats = browser.get_stats()
            avail = stats.get("available", False)
            _kait_print(
                f"  Available: {'Yes' if avail else 'No'}",
                _C.SUCCESS if avail else _C.ERROR,
            )
            if stats.get("init_error"):
                _kait_print(f"  Error: {stats['init_error']}", _C.ERROR)
            llm = stats.get("llm", "none")
            _kait_print(f"  LLM: {llm}", _C.DIM)
            _kait_print(f"  Tasks run: {stats.get('total_tasks', 0)}", _C.DIM)
            _kait_print(f"  Successes: {stats.get('total_successes', 0)}", _C.DIM)
            _kait_print(f"  Errors: {stats.get('total_errors', 0)}", _C.DIM)
            sr = stats.get("success_rate", 0)
            _kait_print(f"  Success rate: {sr:.0%}", _C.DIM)
            _kait_print(f"  Headless: {stats.get('headless', True)}", _C.DIM)
        except Exception as exc:
            _kait_print(f"  Error reading status: {exc}", _C.ERROR)

    # ------------------------------------------------------------------
    # Corrections and Feedback
    # ------------------------------------------------------------------
    def _handle_correction(self, correction_text: str) -> None:
        """Handle user correction of last response."""
        if len(self._conversation_history) < 2:
            _kait_print("  No previous response to correct.", _C.DIM)
            return

        last_response = self._conversation_history[-1].get("content", "")
        last_input = self._conversation_history[-2].get("content", "")

        self.bank.record_correction(
            original_response=last_response,
            correction=correction_text,
            reason=f"User corrected response to: {last_input[:100]}",
            domain="general",
        )
        self.evolution.record_correction()

        _kait_print("  Correction recorded. I'll learn from this!", _C.SUCCESS)
        self.mood.update_mood("determined")
        self.mood.tick()

    def _handle_feedback(self, feedback_str: str) -> None:
        """Handle user feedback on last response."""
        try:
            score = int(feedback_str)
            if not 1 <= score <= 5:
                raise ValueError
        except ValueError:
            _kait_print("  Usage: /feedback <1-5>", _C.DIM)
            return

        # Update last interaction's feedback
        history = self.bank.get_interaction_history(limit=1, session_id=self._session_id)
        if history:
            self.bank.update_interaction_feedback(
                history[0].get("id", ""), float(score) / 5.0
            )

        # Update resonance
        normalized = (score - 1) / 4.0  # 0.0 to 1.0
        self.resonance.process_interaction("", "", feedback=normalized)

        # Update evolution
        self.evolution.record_interaction_outcome(
            success=score >= 3,
            resonance=normalized,
            quality=normalized,
        )

        mood = "excited" if score >= 4 else "calm" if score == 3 else "determined"
        self.mood.update_mood(mood)
        self.mood.tick()

        _kait_print(f"  Feedback recorded: {score}/5. Thank you!", _C.SUCCESS)

    # ------------------------------------------------------------------
    # Proactive Insights
    # ------------------------------------------------------------------
    def _surface_pending_insights(self) -> None:
        """Display any insights accumulated during idle time."""
        with self._lock:
            insights = list(self._pending_insights)
            self._pending_insights.clear()

        if not insights:
            return

        _kait_print(
            f"\n  While you were away, I reflected and learned:",
            _C.EVOLVE,
        )
        for insight in insights[:3]:
            _kait_print(f"    - {insight}", _C.DIM)
        if len(insights) > 3:
            _kait_print(
                f"    ... and {len(insights) - 3} more (/insights to see all)",
                _C.DIM,
            )
        print()

    # ------------------------------------------------------------------
    # Background Threads
    # ------------------------------------------------------------------
    def _start_background_threads(self) -> None:
        """Start background processing threads."""
        # Mood tick thread (smooth transitions)
        self._mood_thread = threading.Thread(
            target=self._mood_tick_loop,
            daemon=True,
            name="sidekick-mood",
        )
        self._mood_thread.start()

        # Idle reflection thread
        self._idle_thread = threading.Thread(
            target=self._idle_evolution_loop,
            daemon=True,
            name="sidekick-idle",
        )
        self._idle_thread.start()

    def _mood_tick_loop(self) -> None:
        """Background thread for mood state transitions."""
        while not self._shutdown_event.is_set():
            try:
                with self._lock:
                    self.mood.tick()
            except Exception:
                pass
            self._shutdown_event.wait(CFG.MOOD_TICK_INTERVAL_S)

    def _idle_evolution_loop(self) -> None:
        """Background thread for idle-time evolution."""
        while not self._shutdown_event.is_set():
            self._shutdown_event.wait(CFG.IDLE_REFLECTION_INTERVAL_S)
            if self._shutdown_event.is_set():
                break

            # Only evolve during idle periods
            with self._lock:
                idle_since = self._idle_since
            if idle_since is None:
                continue
            idle_duration = time.time() - idle_since
            if idle_duration < CFG.IDLE_REFLECTION_INTERVAL_S:
                continue

            try:
                log.info("Idle evolution: reviewing and improving...")
                interactions = self.bank.get_interaction_history(
                    limit=CFG.HISTORY_WINDOW_IDLE, session_id=None,
                )
                if not interactions:
                    continue

                with self._lock:
                    self.mood.update_mood("deep_thought")
                    self.mood.set_kait_level(0.3)

                # Analyze recent patterns (outside lock - agents are stateless)
                reflection_result = self.orchestrator.dispatch("reflection", {
                    "history": [
                        {"role": "user", "content": i.get("user_input", "")}
                        for i in interactions
                    ],
                })

                if reflection_result.success and isinstance(reflection_result.data, dict):
                    suggestions = reflection_result.data.get("suggestions", [])
                    for s in suggestions[:2]:
                        insight_text = str(s)
                        self.bank.update_context(
                            f"idle_insight_{int(time.time())}",
                            {"insight": insight_text, "source": "idle_reflection"},
                            "meta",
                        )
                        self.evolution.record_learning()

                        # Queue for proactive surfacing to user
                        with self._lock:
                            if len(self._pending_insights) < 10:
                                self._pending_insights.append(insight_text)

                with self._lock:
                    self.mood.update_mood("calm")
                    self.mood.set_kait_level(0.6)

            except Exception as exc:
                log.debug("Idle evolution error: %s", exc)

    # ------------------------------------------------------------------
    # Startup / Shutdown
    # ------------------------------------------------------------------
    def _print_banner(self) -> None:
        """Print the startup banner."""
        banner = f"""
{_C.KAIT}{_C.BOLD}
    _  __     _ _
   | |/ /    (_) |
   | ' / __ _ _| |_
   |  < / _` | | __|
   | . \\ (_| | | |_
   |_|\\_\\__,_|_|\\__|
         AI Sidekick v{VERSION}
{_C.RESET}
{_C.DIM}  Text+Audio AI Sidekick | Self-Evolving | Local + Claude{_C.RESET}
{_C.DIM}  Session: {self._session_id} | Type /help for commands{_C.RESET}
"""
        print(banner)

    def _shutdown(self) -> None:
        """Graceful shutdown."""
        log.info("Shutting down Kait Sidekick...")
        self._running = False
        self._shutdown_event.set()

        # Save final state
        try:
            # Record session summary
            metrics = self.evolution.get_metrics()
            self.bank.save_evolution(
                evolution_type="session_end",
                description=(
                    f"Session {self._session_id} ended after "
                    f"{self._interaction_count} interactions"
                ),
                metrics_before={
                    "interactions": metrics.total_interactions - self._interaction_count,
                    "stage": metrics.evolution_stage,
                },
                metrics_after={
                    "interactions": metrics.total_interactions,
                    "stage": metrics.evolution_stage,
                    "resonance": self.resonance.get_resonance_score(),
                },
            )
        except Exception as exc:
            log.error("Error saving session state: %s", exc)

        # Save mood state for next session
        self._save_mood_state()

        # Save session summary for welcome-back (v1.4)
        self._save_session_summary()

        # Close EIDOS episode
        self._end_eidos_episode()

        # Shutdown web browser if active
        if _WEB_BROWSER_AVAILABLE:
            try:
                browser = get_web_browser()
                browser.shutdown()
            except Exception as exc:
                log.debug("WebBrowser shutdown error: %s", exc)

        # Stop TTS if playing
        if self._tts:
            try:
                self._tts.stop()
            except Exception:
                pass

        # Close mood tracker
        self.mood.close()

        # Stop background services if requested
        if self._stop_services_on_exit:
            _kait_print("  Stopping background services...", _C.SYSTEM)
            try:
                results = stop_services()
                stopped = [n for n, s in results.items() if s == "stopped"]
                if stopped:
                    _kait_print(
                        f"  Stopped: {', '.join(stopped)}", _C.DIM,
                    )
            except Exception as exc:
                log.warning("Error stopping services: %s", exc)
        else:
            _kait_print(
                "  Background services still running (use --stop-services-on-exit to stop)",
                _C.DIM,
            )

        _kait_print("\n  Kait Sidekick shut down. See you next time!", _C.KAIT)
        _kait_print(
            f"  Session stats: {self._interaction_count} interactions, "
            f"Stage {self.evolution.get_metrics().evolution_stage}",
            _C.DIM,
        )


# ---------------------------------------------------------------------------
# Pre-flight Checks
# ---------------------------------------------------------------------------
def run_preflight_checks(*, verbose: bool = True) -> list:
    """Run pre-flight diagnostics. Returns list of check dicts."""
    import shutil

    checks = []

    # 1. Python version
    py_ok = sys.version_info >= (3, 10)
    checks.append({
        "name": "Python version",
        "ok": py_ok,
        "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "fix": "Requires Python 3.10+. Install from python.org." if not py_ok else "",
    })

    # 2. Ollama binary
    ollama_bin = shutil.which("ollama")
    checks.append({
        "name": "Ollama installed",
        "ok": ollama_bin is not None,
        "detail": ollama_bin or "not found",
        "fix": "Install Ollama: https://ollama.com/download" if not ollama_bin else "",
    })

    # 3. Ollama server running
    ollama_running = False
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read())
                models = data.get("models", [])
                ollama_running = True
                checks.append({
                    "name": "Ollama server",
                    "ok": True,
                    "detail": f"running ({len(models)} model(s) available)",
                    "fix": "",
                })
                # 4. Models available
                has_models = len(models) > 0
                model_names = [m.get("name", "?") for m in models[:3]]
                checks.append({
                    "name": "Models available",
                    "ok": has_models,
                    "detail": ", ".join(model_names) if has_models else "none",
                    "fix": "Pull a model: ollama pull llama3.1:8b" if not has_models else "",
                })
    except Exception:
        checks.append({
            "name": "Ollama server",
            "ok": False,
            "detail": "not responding on localhost:11434",
            "fix": "Start Ollama: ollama serve",
        })
        checks.append({
            "name": "Models available",
            "ok": False,
            "detail": "cannot check (server down)",
            "fix": "Start Ollama first, then: ollama pull llama3.1:8b",
        })

    # 5. Database writable
    kait_dir = Path.home() / ".kait"
    try:
        kait_dir.mkdir(exist_ok=True)
        test_file = kait_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        checks.append({
            "name": "Data directory",
            "ok": True,
            "detail": str(kait_dir),
            "fix": "",
        })
    except Exception as exc:
        checks.append({
            "name": "Data directory",
            "ok": False,
            "detail": f"cannot write to {kait_dir}: {exc}",
            "fix": f"Fix permissions: chmod 755 {kait_dir}",
        })

    # 6. Disk space
    try:
        stat = shutil.disk_usage(kait_dir)
        free_gb = stat.free / (1024 ** 3)
        disk_ok = free_gb >= 2.0
        checks.append({
            "name": "Disk space",
            "ok": disk_ok,
            "detail": f"{free_gb:.1f} GB free",
            "fix": "Need at least 2 GB free for models and data" if not disk_ok else "",
        })
    except Exception:
        checks.append({
            "name": "Disk space",
            "ok": True,
            "detail": "check skipped",
            "fix": "",
        })

    # 7. GPU detection
    try:
        client = get_llm_client()
        gpu = client.get_gpu_info()
        has_gpu = gpu.get("has_gpu", False)
        backend = gpu.get("backend", "cpu")
        name = gpu.get("gpu_name", "none")
        checks.append({
            "name": "GPU acceleration",
            "ok": True,  # Not a hard fail - CPU works
            "detail": f"{name} ({backend})" if has_gpu else "CPU only (slower but functional)",
            "fix": "",
        })
    except Exception:
        checks.append({
            "name": "GPU acceleration",
            "ok": True,
            "detail": "detection skipped",
            "fix": "",
        })

    if verbose:
        print(f"\n  Kait AI Intel v{VERSION} - Pre-flight Check\n")
        all_ok = True
        for c in checks:
            icon = "PASS" if c["ok"] else "FAIL"
            print(f"  [{icon}] {c['name']}: {c['detail']}")
            if not c["ok"]:
                all_ok = False
                if c.get("fix"):
                    print(f"         Fix: {c['fix']}")
        print()
        if all_ok:
            print("  All checks passed! Ready to launch.")
        else:
            print("  Some checks failed. Fix the issues above and retry.")
        print()

    return checks


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kait AI Intel - Text+Audio AI Sidekick",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show evolution status and exit",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset evolution state",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run pre-flight diagnostics and exit",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode with auto-reconnect",
    )
    parser.add_argument(
        "--no-services",
        action="store_true",
        help="Skip auto-starting background services (kaitd, bridge, pulse, etc.)",
    )
    parser.add_argument(
        "--stop-services-on-exit",
        action="store_true",
        help="Stop background services when the sidekick exits",
    )
    parser.add_argument(
        "--tts-backend",
        type=str,
        default=None,
        help="TTS backend: auto|elevenlabs|openai|piper|say (default: auto)",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default=None,
        help="TTS voice name/ID (backend-specific)",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Disable text-to-speech entirely",
    )

    args = parser.parse_args()

    if args.version:
        print(f"Kait AI Intel v{VERSION}")
        return

    if args.check:
        checks = run_preflight_checks(verbose=True)
        sys.exit(0 if all(c["ok"] for c in checks) else 1)

    if args.status:
        engine = load_evolution_engine()
        print(engine.get_evolution_report())
        bank = get_reasoning_bank()
        stats = bank.get_stats()
        print(f"\nReasoningBank: {stats}")
        return

    if args.reset:
        engine = load_evolution_engine()
        engine.reset()
        print("Evolution state reset to Stage 1.")
        return

    # Run the sidekick
    sidekick = KaitSidekick(
        auto_services=not args.no_services,
        stop_services_on_exit=args.stop_services_on_exit,
        tts_backend=args.tts_backend,
        tts_voice=args.voice,
        no_tts=args.no_tts,
    )
    if args.daemon:
        _run_daemon(sidekick)
    else:
        sidekick.run()


def _run_daemon(sidekick: KaitSidekick) -> None:
    """Run in daemon mode with auto-reconnect.

    When the LLM disconnects, falls back to offline mode and
    periodically attempts to reconnect.
    """
    import atexit

    RECONNECT_INTERVAL_S = 30
    log.info("Starting in daemon mode (auto-reconnect enabled)")
    _kait_print("  Daemon mode: auto-reconnect enabled", _C.SYSTEM)

    pid_file = Path.home() / ".kait" / "sidekick.pid"

    def _cleanup_pid():
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    # Write PID for external monitoring
    try:
        pid_file.write_text(str(os.getpid()))
        atexit.register(_cleanup_pid)
    except Exception:
        pass

    # Background reconnect thread
    def _reconnect_loop():
        while not sidekick._shutdown_event.is_set():
            sidekick._shutdown_event.wait(RECONNECT_INTERVAL_S)
            if sidekick._shutdown_event.is_set():
                break
            if not sidekick._llm_available:
                log.info("Daemon: attempting LLM reconnect...")
                try:
                    if sidekick._connect_llm():
                        _kait_print(
                            f"\n  Reconnected to Ollama! Model: {sidekick._model_name}",
                            _C.SUCCESS,
                        )
                except Exception as exc:
                    log.debug("Daemon reconnect failed: %s", exc)

    reconnect_thread = threading.Thread(
        target=_reconnect_loop, daemon=True, name="sidekick-reconnect"
    )
    reconnect_thread.start()

    sidekick.run()
    _cleanup_pid()


if __name__ == "__main__":
    main()
