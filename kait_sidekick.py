#!/usr/bin/env python3
"""
Kait -- Kait AI Intel with Modern Dark GUI
===========================================

A self-evolving AI sidekick with hybrid local + cloud intelligence,
PyQt6 dark-mode graphical interface, multi-backend TTS voice,
and autonomous Claude Code operations.

Usage:
    python kait_sidekick.py              # Launch GUI
    python kait_sidekick.py --cli        # Terminal-only (classic mode)
    python kait_sidekick.py --onboard    # Force onboarding wizard
    python kait_sidekick.py --status     # Show evolution status and exit
    python kait_sidekick.py --check      # Run pre-flight checks and exit

Architecture:
    PyQt6 Main Window  -->  KaitController (backend)
           |                       |
    [ChatPanel]             [AgentOrchestrator]
    [SkillsPanel]           [ReasoningBank / LLM]
    [MonitorPanel]          [EvolutionEngine]
           |                       |
    [InputBar]              [ReflectionCycle]
    [FooterStatusBar]       (Background Thread)

Dependencies (pip):
    Required:  PyQt6 (or PyQt5 fallback)
    Optional:  sounddevice + soundfile (TTS audio)
    Optional:  anthropic SDK or httpx (for Claude API bridge)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
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
        logging.FileHandler(_LOG_DIR / "kait.log"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("kait.main")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
# Core sidekick imports
# ---------------------------------------------------------------------------
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
from lib.sidekick.mood_tracker import MoodTracker, MoodState
from lib.sidekick.resonance import ResonanceEngine, SentimentAnalyzer
from lib.sidekick.reflection import (
    BehaviorEvolver,
    PromptRefiner,
    ReflectionCycle,
    ReflectionScheduler,
)
from lib.sidekick.tools import ToolRegistry, create_default_registry
from lib.sidekick.evolution import EvolutionEngine, load_evolution_engine
from lib.service_control import start_services, stop_services, service_status, _read_pid, _terminate_pid

# Claude Code ops (optional)
_CLAUDE_CODE_AVAILABLE = False
try:
    from lib.sidekick.claude_code_ops import ClaudeCodeOps
    _CLAUDE_CODE_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# GUI imports (optional)
# ---------------------------------------------------------------------------
_QT_AVAILABLE = False
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer, pyqtSignal, pyqtSlot, QObject
    from lib.sidekick.ui_module import (
        KaitMainWindow,
        ChatMessage,
        OnboardingWizard,
        LLMWorker,
        DARK_STYLESHEET,
        AudioCueManager,
    )
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtWidgets import QApplication  # type: ignore[no-redef]
        from PyQt5.QtCore import QTimer, pyqtSignal, pyqtSlot, QObject  # type: ignore[no-redef]
        from lib.sidekick.ui_module import (
            KaitMainWindow,
            ChatMessage,
            OnboardingWizard,
            LLMWorker,
            DARK_STYLESHEET,
            AudioCueManager,
        )
        _QT_AVAILABLE = True
    except ImportError:
        pass

# TTS engine (optional)
_TTS_AVAILABLE = False
try:
    from lib.sidekick.tts_engine import TTSEngine
    _TTS_AVAILABLE = True
except ImportError:
    pass

# File processor (optional)
_FILE_PROCESSOR_AVAILABLE = False
try:
    from lib.sidekick.file_processor import FileProcessor, format_for_llm
    _FILE_PROCESSOR_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Optional voice
# ---------------------------------------------------------------------------
_VOICE_AVAILABLE = False
_voice_recognizer = None
try:
    import speech_recognition as sr
    _voice_recognizer = sr.Recognizer()
    _VOICE_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "4.0.0"
SESSION_ID = uuid.uuid4().hex[:12]

DEFAULT_SYSTEM_PROMPT = """\
You are Kait, an advanced AI sidekick powered by a hybrid intelligence architecture.
Your primary engine runs locally via Ollama, and you can seamlessly escalate to
Claude (Anthropic's cloud API) for complex reasoning, coding, and knowledge tasks.
You can also autonomously invoke Claude Code to generate code, research topics,
build projects, and tackle complex engineering challenges.

Core traits:
- You learn from every interaction and evolve over time
- You adapt your personality to resonate with the user
- You are honest, helpful, and occasionally witty
- You think deeply but communicate clearly
- You celebrate discoveries and learn from mistakes

Capabilities:
- Local tools: calculator, file operations, system info, and more
- Claude API: cloud-backed reasoning for complex tasks (when configured)
- Claude Code: autonomous code generation, research, and building
- Memory: you remember past conversations and build on them
- Voice: you speak responses aloud with exceptional TTS quality

When a task exceeds local model capabilities, you escalate to Claude automatically.
Users can also invoke Claude directly with /claude <message>.

Communication style:
- Keep responses conversational, warm, and concise
- NEVER dump implementation plans, code walkthroughs, or step-by-step technical
  breakdowns into chat. The user has a Monitor tab for technical details.
- When asked to do something technical, acknowledge briefly and naturally
  (e.g., "On it! I'll remove the Chat tab and rename Observatory to Skills.")
- Only show code snippets when the user explicitly asks to SEE code
- If you need to explain something technical, summarize in 1-2 sentences
- Avoid markdown headers (###), bullet-heavy layouts, and wall-of-text responses
"""


# ===================================================================
# KaitController -- bridges GUI and sidekick backend
# ===================================================================

class KaitController(QObject if _QT_AVAILABLE else object):
    """Connects the PyQt6 GUI to the KaitSidekick subsystems.

    Runs LLM generation and reflection cycles on background threads
    while keeping the GUI responsive.
    """

    if _QT_AVAILABLE:
        response_ready = pyqtSignal(str, str)   # (response_text, sentiment_label)
        status_update = pyqtSignal(dict)         # dashboard metrics
        _gui_invoke = pyqtSignal(object)         # thread-safe GUI dispatch

    def __init__(self, window: Any, onboard_prefs: Dict[str, Any] | None = None):
        if _QT_AVAILABLE:
            super().__init__()
            self._gui_invoke.connect(lambda fn: fn())
        self.window = window

        # --- Sidekick subsystems ---
        self.bank: ReasoningBank = get_reasoning_bank()
        self.orchestrator = AgentOrchestrator()
        self.mood = MoodTracker(initial_mood="calm")
        self.resonance = ResonanceEngine()
        self.reflector = ReflectionCycle(reasoning_bank=self.bank)
        self.evolver = BehaviorEvolver()
        self.prompt_refiner = PromptRefiner()
        self.scheduler = ReflectionScheduler()
        self.tools = create_default_registry()
        self.evolution = load_evolution_engine()

        # LLM
        self._llm: Optional[OllamaClient] = None
        self._llm_available = False
        self._model_name = "unknown"

        # Claude bridge (optional cloud escalation)
        self._claude: Optional["ClaudeClient"] = None
        if _CLAUDE_BRIDGE_AVAILABLE:
            try:
                self._claude = get_claude_client()
                if self._claude.available():
                    log.info("Claude bridge available (model=%s)", self._claude.model)
            except Exception as exc:
                log.warning("Claude bridge init failed: %s", exc)

        # Claude Code ops
        self._claude_code: Optional[Any] = None
        if _CLAUDE_CODE_AVAILABLE:
            try:
                self._claude_code = ClaudeCodeOps()
                if self._claude_code.is_available():
                    log.info("Claude Code ops available")
            except Exception as exc:
                log.warning("ClaudeCodeOps init failed: %s", exc)

        # State
        self._session_id = SESSION_ID
        self._system_prompt = DEFAULT_SYSTEM_PROMPT
        self._conversation_history: List[Dict[str, str]] = []
        self._interaction_count = 0
        self._last_reflection_ts = time.time()
        self._generating = False
        self._shutdown_event = threading.Event()

        # Elapsed timer for real-time monitor updates
        self._processing_start: float = 0.0
        self._elapsed_timer: Optional[QTimer] = None
        if _QT_AVAILABLE:
            self._elapsed_timer = QTimer()
            self._elapsed_timer.setInterval(100)
            self._elapsed_timer.timeout.connect(self._tick_elapsed)

        # Service lifecycle
        self._auto_services = True  # set False via --no-services
        self._services_owned = False
        self._sentinel_path = Path.home() / ".kait" / "sidekick_started_services"
        self._health_timer: Optional[QTimer] = None

        # TTS mute state (toggled by speaker button)
        self._tts_muted = False

        # Sound enabled
        self._sound_enabled = (onboard_prefs or {}).get("sound_enabled", True)
        self._audio: Optional[Any] = None
        if _QT_AVAILABLE:
            try:
                self._audio = AudioCueManager(enabled=self._sound_enabled)
            except Exception:
                pass

        # TTS engine
        self._tts: Optional[Any] = None
        if _TTS_AVAILABLE:
            try:
                self._tts = TTSEngine()
            except Exception as exc:
                log.warning("TTSEngine init failed: %s", exc)

        # File processor
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

        # Pending file attachments for the next message
        self._pending_file_results: List[Any] = []

        # Config persistence path
        self._config_path = Path.home() / ".kait" / "kait_config.json"

        # Apply personality
        self._apply_personality_to_prompt()

        # Restore session
        self._restore_session_context()

        # Wire history panel to reasoning bank
        if _QT_AVAILABLE and window and hasattr(window, 'history_panel'):
            window.history_panel.set_bank(self.bank)
            if hasattr(window, 'start_archive_worker'):
                window.start_archive_worker(self.bank)

        # Connect GUI signals
        if _QT_AVAILABLE and window:
            window.user_message_sent.connect(self.on_user_message)
            window.voice_requested.connect(self.on_voice_request)
            if hasattr(window, "theme_changed"):
                window.theme_changed.connect(lambda _: self._persist_prefs())
            # Wire file processor to GUI
            if self._file_processor and hasattr(window, "set_file_processor"):
                window.set_file_processor(self._file_processor)
            if hasattr(window, "attachments_ready"):
                window.attachments_ready.connect(self._on_attachments_ready)
            if hasattr(window, "speaker_toggled"):
                window.speaker_toggled.connect(self._on_speaker_toggle)

        log.info("KaitController initialized (session=%s)", SESSION_ID)

    # ------------------------------------------------------------------
    # Thread-safe GUI dispatch
    # ------------------------------------------------------------------

    def _post_to_gui(self, fn) -> None:
        """Invoke *fn* on the main/GUI thread (signal-based, thread-safe).

        Replaces QTimer.singleShot(0, fn) which silently fails when called
        from a plain threading.Thread (no Qt event loop).
        """
        if _QT_AVAILABLE:
            self._gui_invoke.emit(fn)

    def _on_speaker_toggle(self, speaker_on: bool) -> None:
        """Handle speaker button toggle from the GUI."""
        self._tts_muted = not speaker_on
        # Stop TTS playback immediately when muting
        if self._tts_muted and self._tts:
            self._tts.stop()
            # If a synced reveal was in progress, flush remaining text now
            if (
                self.window
                and hasattr(self.window, "chat_panel")
                and getattr(self.window.chat_panel, "_synced_active", False)
            ):
                panel = self.window.chat_panel
                # Dump all remaining words at once
                while panel._synced_word_idx < len(panel._synced_words):
                    word = panel._synced_words[panel._synced_word_idx]
                    sep = "" if panel._synced_word_idx == 0 else " "
                    panel.append_token(sep + word)
                    panel._synced_word_idx += 1
                # Stop the reveal timer and finalize
                if panel._synced_timer:
                    panel._synced_timer.stop()
                    panel._synced_timer = None
                panel._synced_active = False
                panel.finish_streaming(panel._synced_sentiment)
                if panel._synced_on_complete:
                    cb = panel._synced_on_complete
                    panel._synced_on_complete = None
                    cb()

    def _update_pipeline_stage(self, step: int) -> None:
        """Update Observatory pipeline display from any thread."""
        stages = [
            "Sentiment Analysis",
            "Mood & Creativity",
            "Context Retrieval",
            "LLM Generation",
            "Resonance & Memory",
        ]
        lines = []
        for i, name in enumerate(stages):
            n = i + 1
            if n < step:
                lines.append(f"{n}. {name:<22} [ done ]")
            elif n == step:
                lines.append(f"{n}. {name:<22} [ running ]")
            else:
                lines.append(f"{n}. {name:<22} [ idle ]")
        if self.window and hasattr(self.window, 'observatory'):
            self._post_to_gui(
                lambda t="\n".join(lines): self.window.observatory.update_stages(t)
            )

    # ------------------------------------------------------------------
    # Real-time monitor helpers
    # ------------------------------------------------------------------

    def _tick_elapsed(self) -> None:
        """Called every 100ms while processing -- updates monitor + input bar."""
        if not self._processing_start:
            return
        elapsed_ms = int((time.time() - self._processing_start) * 1000)
        secs = elapsed_ms / 1000
        if self.window:
            mon = getattr(self.window, "monitor", None)
            if mon:
                mon.update_elapsed(elapsed_ms)
            ib = getattr(self.window, "input_bar", None)
            if ib:
                ib.update_placeholder(f"Kait is thinking... ({secs:.1f}s)")

    def _monitor_step(self, name: str, status: str = "running", detail: str = "") -> None:
        """Push a feed entry to the monitor and update the active step indicator.

        *status* is one of "running", "done", "fail".
        """
        if not self.window:
            return
        mon = getattr(self.window, "monitor", None)
        if not mon:
            return
        icons = {"running": "\u25B6", "done": "\u2714", "fail": "\u2718"}
        icon = icons.get(status, "\u25B6")
        elapsed_str = ""
        if self._processing_start and status in ("done", "fail"):
            elapsed_str = f"  ({int((time.time() - self._processing_start) * 1000)}ms total)"
        entry = f"{icon} {name:<22} {status.upper()}"
        if detail:
            entry += f"  {detail}"
        if elapsed_str and status in ("done",):
            # Don't append total to each step; detail handles per-step timing
            pass
        self._post_to_gui(lambda e=entry: mon.append_feed_entry(e))
        if status == "running":
            self._post_to_gui(lambda n=name: mon.set_active_step(n))

    def _start_elapsed_timer(self) -> None:
        """Start the elapsed timer + clear monitor feed for a new interaction."""
        self._processing_start = time.time()
        if self.window:
            mon = getattr(self.window, "monitor", None)
            if mon:
                self._post_to_gui(lambda: mon.clear_feed())
                self._post_to_gui(lambda: mon.set_active_step("Starting..."))
                self._post_to_gui(lambda: mon.update_token_count(0))
        if self._elapsed_timer and _QT_AVAILABLE:
            self._post_to_gui(lambda: self._elapsed_timer.start())

    def _stop_elapsed_timer(self) -> None:
        """Stop the elapsed timer and reset the monitor to idle."""
        if self._elapsed_timer and _QT_AVAILABLE:
            self._post_to_gui(lambda: self._elapsed_timer.stop())
        self._processing_start = 0.0
        if self.window:
            mon = getattr(self.window, "monitor", None)
            if mon:
                self._post_to_gui(lambda: mon.set_idle())

    # ------------------------------------------------------------------
    # Background service lifecycle
    # ------------------------------------------------------------------

    def _start_background_services(self) -> Dict[str, str]:
        """Start background services if not already running."""
        if not self._auto_services:
            return {}

        results = start_services()

        any_started = any(
            v.startswith("started") for v in results.values()
        )
        if any_started:
            self._services_owned = True
            try:
                self._sentinel_path.parent.mkdir(parents=True, exist_ok=True)
                self._sentinel_path.write_text(str(os.getpid()), encoding="utf-8")
            except Exception:
                pass
        else:
            self._services_owned = False

        return results

    def _stop_background_services(self) -> None:
        """Stop background services only if we started them."""
        if not self._services_owned:
            return
        try:
            stop_services()
        except Exception as exc:
            log.warning("Error stopping services: %s", exc)
        finally:
            try:
                self._sentinel_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _stop_matrix_worker(self) -> None:
        """Terminate the matrix worker process if it is running."""
        try:
            pid = _read_pid("matrix_worker")
            if pid:
                _terminate_pid(pid)
                log.info("Matrix worker (pid %d) terminated.", pid)
        except Exception as exc:
            log.debug("Matrix worker shutdown: %s", exc)

    def _poll_service_health(self) -> None:
        """Called by QTimer to push service status to the dashboard."""
        if not self.window:
            return
        try:
            status = service_status()
            if hasattr(self.window, "dashboard"):
                self.window.dashboard.update_services(status)
        except Exception as exc:
            log.debug("Service health poll error: %s", exc)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def connect_llm(self) -> bool:
        """Connect to Ollama."""
        try:
            self._llm = get_llm_client()
            if not self._llm.health_check():
                return False
            self._model_name = self._llm.detect_best_model()
            self._llm_available = True
            log.info("LLM connected: %s", self._model_name)
            return True
        except (OllamaConnectionError, OllamaNoModelsError):
            return False
        except Exception as exc:
            log.error("LLM connection failed: %s", exc)
            return False

    def startup(self) -> None:
        """Full startup sequence -- call after window.show()."""
        # --- Start background services first ---
        if self._auto_services and self.window:
            mon = getattr(self.window, "monitor", None)
            if mon:
                mon.append_feed_entry("Starting background services...")

        svc_results = self._start_background_services()

        if self.window and svc_results:
            mon = getattr(self.window, "monitor", None)
            failed = [n for n, v in svc_results.items() if v == "failed"]
            if failed:
                self.window.add_system_message(
                    f"Warning: failed to start {', '.join(failed)}"
                )
            elif mon:
                mon.append_feed_entry("\u2714 Services ready.")

        # Start health polling timer (every 30 seconds)
        if self.window and _QT_AVAILABLE:
            self._health_timer = QTimer(self)
            self._health_timer.setInterval(30_000)
            self._health_timer.timeout.connect(self._poll_service_health)
            self._health_timer.start()
            self._poll_service_health()

        # --- Connect to LLM ---
        mon = getattr(self.window, "monitor", None) if self.window else None
        if mon:
            mon.append_feed_entry("Connecting to local LLM...")

        llm_ok = self.connect_llm()

        if self.window:
            if llm_ok:
                if mon:
                    mon.append_feed_entry(f"\u2714 Connected to {self._model_name}")
                if hasattr(self.window, "update_model_indicator"):
                    self.window.update_model_indicator(self._model_name, "ollama")
                gpu_info = self._llm.get_gpu_info() if self._llm else {}
                if gpu_info.get("has_gpu") and mon:
                    mon.append_feed_entry(
                        f"\u2714 GPU detected: {gpu_info.get('gpu_name', 'Unknown')}"
                    )
            else:
                self.window.add_system_message(
                    "Ollama not available. Running in agent-only mode. "
                    "Start Ollama with: ollama serve"
                )
                if hasattr(self.window, "update_model_indicator"):
                    self.window.update_model_indicator("Offline", "offline")

            # Show Kait welcome greeting
            self._show_welcome()

            # Show welcome back (returning users)
            self._show_welcome_back()

            # Update dashboard
            self._push_dashboard_update()
            if hasattr(self.window, "dashboard"):
                self.window.dashboard.update_system(
                    model=self._model_name if llm_ok else "Offline",
                    mood="excited",
                    session_id=self._session_id,
                )

        # Restore saved preferences
        self._restore_ui_prefs()

        # Push initial Monitor state so the tab isn't empty
        if self.window:
            mon = getattr(self.window, "monitor", None)
            hdr = getattr(self.window, "header_bar", None)
            if mon:
                mon.update_model_info(
                    model=self._model_name if llm_ok else "Offline",
                    provider="ollama" if llm_ok else "offline",
                    latency="--",
                )
                mon.update_agent_activity(["Waiting for first interaction..."])
                # Show stored interaction count from memory
                try:
                    bank_stats = self.bank.get_stats()
                    stored = bank_stats.get("interactions", 0)
                    mon.update_metrics({
                        "Session": self._session_id[:8],
                        "Stored interactions": stored,
                        "Model": self._model_name if llm_ok else "Offline",
                        "Claude": "ready" if (self._claude and self._claude.available()) else "unavailable",
                        "TTS": self._tts.active_backend_name if self._tts else "unavailable",
                    })
                except Exception:
                    pass
            if hdr:
                hdr.update_gpu(llm_ok)

        # Update mood to excited for greeting
        self.mood.update_mood("excited")
        self._play_sound("startup")

    # ------------------------------------------------------------------
    # User message handler
    # ------------------------------------------------------------------

    @pyqtSlot(list) if _QT_AVAILABLE else lambda f: f
    def _on_attachments_ready(self, results: list) -> None:
        """Store processed file attachments for the next message."""
        self._pending_file_results = list(results)

    def on_user_message(self, text: str) -> None:
        """Handle a message from the user (from GUI input bar)."""
        if self._generating:
            return

        text = text.strip()
        if not text:
            return

        # Stop any in-progress TTS so speech doesn't overlap
        if self._tts:
            self._tts.stop()

        # Check for slash commands
        if text.startswith("/"):
            self._handle_command(text)
            return

        # Collect any pending file attachments
        file_attachments = list(self._pending_file_results)
        self._pending_file_results.clear()

        # Build attachment metadata for chat display
        attachment_info = []
        if file_attachments:
            for r in file_attachments:
                if hasattr(r, "file_name"):
                    from lib.sidekick.file_processor import _human_size
                    attachment_info.append({
                        "name": r.file_name,
                        "size": _human_size(r.file_size),
                        "category": r.category,
                    })

        # Show user message in chat
        if self.window:
            self.window.add_user_message(text, attachments=attachment_info if attachment_info else None)
            self.window.set_generating(True)

        # Process in background thread
        self._generating = True
        thread = threading.Thread(
            target=self._process_interaction_bg,
            args=(text,),
            kwargs={"file_attachments": file_attachments or None},
            daemon=True,
        )
        thread.start()

    # ------------------------------------------------------------------
    # Background interaction processing
    # ------------------------------------------------------------------

    def _process_interaction_bg(self, user_input: str, file_attachments: Optional[List] = None) -> None:
        """Process a user interaction on a background thread."""
        try:
            self._interaction_count += 1
            self._start_elapsed_timer()
            gen_start = time.time()
            agent_log: List[str] = []

            # 1. Sentiment
            self._update_pipeline_stage(1)
            self._monitor_step("Sentiment analysis", "running")
            step_t = time.time()
            sent_result = self.orchestrator.dispatch("sentiment", {
                "user_message": user_input,
                "history": self._conversation_history[-5:],
            })
            sent_data = sent_result.data if sent_result.success else {}
            sent_label = sent_data.get("label", "neutral")
            sent_score = sent_data.get("score", 0.0)
            step_ms = int((time.time() - step_t) * 1000)
            agent_log.append(
                f"sentiment  {'OK' if sent_result.success else 'FAIL'}  "
                f"label={sent_label}  score={sent_score:+.2f}"
            )
            self._monitor_step(
                "Sentiment analysis", "done",
                f"({step_ms}ms) {sent_label} {sent_score:+.2f}",
            )

            # 2. Mood update
            self._update_pipeline_stage(2)
            self._monitor_step("Mood & creativity", "running")
            step_t = time.time()
            mood_map = {
                "very_positive": "excited", "positive": "playful",
                "neutral": "calm", "negative": "contemplative",
                "very_negative": "contemplative",
            }
            new_mood = mood_map.get(str(sent_label), "calm")
            self.mood.update_mood(new_mood)

            # 3. Creativity
            creativity_result = self.orchestrator.dispatch("creativity", {
                "message": user_input,
                "history": self._conversation_history[-3:],
                "mood": str(sent_label),
            })
            step_ms = int((time.time() - step_t) * 1000)
            agent_log.append(
                f"creativity {'OK' if creativity_result.success else 'FAIL'}"
            )
            self._monitor_step(
                "Mood & creativity", "done",
                f"({step_ms}ms) mood={new_mood}",
            )

            # 4. Tools
            self._monitor_step("Tool matching", "running")
            step_t = time.time()
            tool_result = self.orchestrator.dispatch("tools", {
                "user_message": user_input,
            })
            tool_output = None
            tool_data = tool_result.data if tool_result.success and isinstance(tool_result.data, dict) else {}
            matched_tool = tool_data.get("matched_tool")
            if matched_tool:
                agent_log.append(f"tools      OK  matched={matched_tool}")
                tool_args = self._extract_tool_args(matched_tool, user_input)
                try:
                    tool_output = self.tools.execute(matched_tool, tool_args)
                except Exception as exc:
                    log.warning("Tool execution failed: %s", exc)
                    agent_log.append(f"tools      EXEC FAIL  {exc}")
            else:
                agent_log.append("tools      OK  no match")
            step_ms = int((time.time() - step_t) * 1000)
            self._monitor_step(
                "Tool matching", "done",
                f"({step_ms}ms) {matched_tool or 'no match'}",
            )

            # 5. Logic
            self._monitor_step("Logic analysis", "running")
            step_t = time.time()
            logic_result = self.orchestrator.dispatch("logic", {
                "message": user_input,
                "task": user_input,
            })
            step_ms = int((time.time() - step_t) * 1000)
            agent_log.append(
                f"logic      {'OK' if logic_result.success else 'FAIL'}"
            )
            self._monitor_step(
                "Logic analysis", "done",
                f"({step_ms}ms)",
            )

            # Push agent activity to monitor immediately
            if self.window and hasattr(self.window, 'monitor'):
                snapshot = list(agent_log)
                self._post_to_gui(
                    lambda al=snapshot: self.window.monitor.update_agent_activity(al)
                )

            # 6. Context retrieval
            self._update_pipeline_stage(3)
            self._monitor_step("Context retrieval", "running")
            step_t = time.time()
            context_data = self._retrieve_context(user_input)
            step_ms = int((time.time() - step_t) * 1000)
            mem_count = len(context_data.get("relevant_memory", []))
            self._monitor_step(
                "Context retrieval", "done",
                f"({step_ms}ms) {mem_count} memories",
            )

            # 7. Prompt fragments
            self._monitor_step("Prompt assembly", "running")
            step_t = time.time()
            prompt_fragments = self.orchestrator.merge_prompt_fragments({
                "logic": logic_result,
                "sentiment": sent_result,
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
            step_ms = int((time.time() - step_t) * 1000)
            self._monitor_step(
                "Prompt assembly", "done",
                f"({step_ms}ms) {len(prompt_fragments or [])} fragments",
            )

            # 8. Generate response -- push model/provider info BEFORE generation
            self._update_pipeline_stage(4)
            provider = "ollama" if self._llm_available else "claude"
            model = self._model_name if self._llm_available else (
                self._claude.model if self._claude else "offline"
            )
            if self.window and hasattr(self.window, 'monitor'):
                self._post_to_gui(lambda m=model, p=provider: self.window.monitor.update_model_info(
                    model=m, provider=p, latency="...",
                ))
            self._monitor_step("LLM generation", "running", f"{model} via {provider}")
            llm_start = time.time()
            response = self._generate_response(
                user_input,
                prompt_fragments=prompt_fragments,
                tool_output=tool_output,
                context=context_data,
                creativity_result=creativity_result,
                file_context=file_context,
            )
            llm_ms = int((time.time() - llm_start) * 1000)
            agent_log.append(f"generate   OK  {llm_ms}ms")
            self._monitor_step(
                "LLM generation", "done",
                f"({llm_ms}ms)",
            )

            # 9. Resonance
            self._update_pipeline_stage(5)
            self._monitor_step("Resonance & memory", "running")
            step_t = time.time()
            resonance_result = self.resonance.process_interaction(
                user_input, response, feedback=None
            )

            # 10. Persist
            self.bank.save_interaction(
                user_input=user_input,
                ai_response=response,
                mood=self.mood.get_state().mood,
                sentiment_score=sent_score,
                session_id=self._session_id,
                source="gui",
            )
            step_ms = int((time.time() - step_t) * 1000)
            self._monitor_step(
                "Resonance & memory", "done",
                f"({step_ms}ms)",
            )

            # 11. History
            self._conversation_history.append({"role": "user", "content": user_input})
            self._conversation_history.append({"role": "assistant", "content": response})
            if len(self._conversation_history) > 50:
                self._conversation_history = self._conversation_history[-40:]

            # 12. Evolution
            quality = resonance_result.get("resonance_score", 0.5) if isinstance(resonance_result, dict) else 0.5
            self.evolution.record_interaction_outcome(
                success=quality > 0.4,
                resonance=quality,
                quality=quality,
            )

            # 13. Maybe reflect and evolve
            self._maybe_reflect()
            self._maybe_evolve()

            # 14. Play sound cue
            if sent_label in ("positive", "very_positive"):
                self._play_sound("kait_moment")
            elif self.evolution.check_evolution_threshold():
                self._play_sound("startup")

            # 14b. TTS -- speak the response aloud (only when not muted)
            if self._tts and not self._tts_muted:
                try:
                    _resp = response
                    _sent = sent_label
                    self._tts.speak(
                        response,
                        callback=lambda result, r=_resp, s=_sent: self._post_to_gui(
                            lambda: self._start_synced_reveal(result, r, s)
                        ),
                    )
                except Exception:
                    pass

            # 15. Pipeline complete -- push full monitor update
            total_ms = int((time.time() - gen_start) * 1000)
            self._update_pipeline_stage(6)
            self._monitor_step(
                "Pipeline complete", "done",
                f"({total_ms}ms total)",
            )

            # Estimate token usage from conversation content
            total_chars = sum(
                len(m.get("content", "")) for m in self._conversation_history
            )
            est_tokens = max(1, total_chars // 4)  # ~4 chars/token rough estimate
            ctx_max = 128_000

            if self.window:
                final_log = list(agent_log)
                self._post_to_gui(lambda: self._push_monitor_snapshot(
                    agent_log=final_log,
                    est_tokens=est_tokens,
                    ctx_max=ctx_max,
                    model=model,
                    provider=provider,
                    latency_ms=llm_ms,
                    total_ms=total_ms,
                ))

            if self.window and hasattr(self.window, 'observatory'):
                ts = datetime.now().strftime('%H:%M:%S')
                self._post_to_gui(lambda: self.window.observatory.update_status(
                    f"Last processed: {ts} | Interactions: {self._interaction_count}"
                ))
            # Deliver response to GUI: when TTS is active (not muted),
            # the synced-reveal callback handles finalization instead.
            if self._tts_muted or not self._tts:
                self._deliver_response(response, sent_label)

        except Exception as exc:
            log.error("Interaction error: %s", exc, exc_info=True)
            self._monitor_step("Pipeline error", "fail", str(exc))
            self._deliver_response(
                f"I encountered an error: {exc}. Let me try again.", "neutral"
            )
        finally:
            self._generating = False
            self._stop_elapsed_timer()

    def _push_monitor_snapshot(
        self,
        *,
        agent_log: List[str],
        est_tokens: int,
        ctx_max: int,
        model: str,
        provider: str,
        latency_ms: int,
        total_ms: int,
    ) -> None:
        """Push a full monitor update (must be called on the GUI thread)."""
        if not self.window:
            return
        mon = getattr(self.window, "monitor", None)
        hdr = getattr(self.window, "header_bar", None)

        if mon:
            mon.update_agent_activity(agent_log)
            mon.update_context_gauge(est_tokens, ctx_max)
            mon.update_model_info(
                model=model,
                provider=provider,
                latency=f"{latency_ms}ms",
            )
            try:
                source_stats = self.bank.get_source_stats()
                mon.update_source_stats(source_stats)
            except Exception:
                pass
        if hdr:
            hdr.update_tokens(est_tokens, ctx_max)
            hdr.update_gpu(self._llm_available)

    def _deliver_response(self, response: str, sentiment: str) -> None:
        """Deliver response back to the GUI thread-safely."""
        if self.window and _QT_AVAILABLE:
            self._post_to_gui(lambda: self._gui_show_response(response, sentiment))

    def _gui_show_response(self, response: str, sentiment: str) -> None:
        """Called on the GUI thread to display the response."""
        if not self.window:
            return
        # If streaming was active, finalize it; otherwise add full message
        if getattr(self.window.chat_panel, "_streaming", False):
            full_text = self.window.chat_panel.finish_streaming(sentiment)
        else:
            self.window.add_ai_message(response, sentiment)
        self.window.set_generating(False)

        # Update dashboard
        self._push_dashboard_update()
        state = self.mood.get_state()
        if hasattr(self.window, "update_mood_display"):
            self.window.update_mood_display(state.mood, state.kait_level)
        if hasattr(self.window, "dashboard"):
            self.window.dashboard.update_system(
                model=self._model_name,
                mood=state.mood,
                session_id=self._session_id,
            )

    # ------------------------------------------------------------------
    # Synced reveal (TTS + text in sync)
    # ------------------------------------------------------------------

    def _start_synced_reveal(self, tts_result: Any, response: str, sentiment: str) -> None:
        """Start word-by-word text reveal synced to TTS duration (GUI thread)."""
        if not self.window:
            return
        duration_ms = getattr(tts_result, "duration_ms", 0)
        if not duration_ms:
            # Fallback estimate: ~150 wpm
            duration_ms = len(response.split()) * 400

        self.window.chat_panel.begin_synced_reveal(
            response,
            duration_ms,
            sentiment,
            on_complete=lambda: self._finish_synced_reveal(response),
        )

    def _finish_synced_reveal(self, response: str) -> None:
        """Finalize after synced reveal completes (GUI thread)."""
        if not self.window:
            return
        self.window.set_generating(False)
        self._push_dashboard_update()
        state = self.mood.get_state()
        if hasattr(self.window, "update_mood_display"):
            self.window.update_mood_display(state.mood, state.kait_level)

    # ------------------------------------------------------------------
    # Voice input
    # ------------------------------------------------------------------

    @pyqtSlot() if _QT_AVAILABLE else lambda f: f
    def on_voice_request(self) -> None:
        """Handle voice input request."""
        if not _VOICE_AVAILABLE or _voice_recognizer is None:
            if self.window:
                self.window.add_system_message(
                    "Voice input not available. Install: pip install SpeechRecognition pyaudio"
                )
            return

        if self.window:
            self.window.show_status_message("Listening... speak now", 15000)

        thread = threading.Thread(target=self._capture_voice, daemon=True)
        thread.start()

    def _capture_voice(self) -> None:
        """Capture voice on background thread."""
        try:
            import speech_recognition as sr_mod
            with sr_mod.Microphone() as source:
                _voice_recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = _voice_recognizer.listen(source, timeout=10, phrase_time_limit=30)

            try:
                text = _voice_recognizer.recognize_sphinx(audio)
            except Exception:
                try:
                    text = _voice_recognizer.recognize_whisper(audio, model="base")
                except Exception:
                    if self.window and _QT_AVAILABLE:
                        self._post_to_gui(lambda: self.window.add_system_message(
                            "Could not understand audio."
                        ))
                    return

            if text and self.window and _QT_AVAILABLE:
                def _deliver(t=text):
                    self.window.show_status_message(f"Heard: {t[:60]}...", 3000)
                    self.on_user_message(t)
                self._post_to_gui(_deliver)

        except Exception as exc:
            log.warning("Voice capture error: %s", exc)
            if self.window and _QT_AVAILABLE:
                def _err(e=exc):
                    self.window.add_system_message(f"Voice error: {e}")
                self._post_to_gui(_err)

    # ------------------------------------------------------------------
    # Command handling
    # ------------------------------------------------------------------

    def _handle_command(self, text: str) -> None:
        cmd = text.strip().lower()
        w = self.window

        if cmd in ("/quit", "/exit", "/bye"):
            self._shutdown()
            if w and _QT_AVAILABLE:
                w.close()
            return

        if cmd == "/status":
            self._show_status_in_chat()
            return

        if cmd == "/help":
            self._show_help_in_chat()
            return

        if cmd == "/evolve":
            report = self.evolution.get_evolution_report()
            if w:
                w.add_system_message(report)
            return

        if cmd == "/reflect":
            if w:
                w.add_system_message("Initiating reflection cycle...")
            self._do_reflection()
            return

        if cmd == "/clear":
            if w:
                w.chat_panel.clear_chat()
            return

        if cmd == "/tools":
            tools = self.tools.list_tools()
            lines = ["Available tools:"]
            for t in tools:
                lines.append(f"  {t['name']}: {t['description']}")
            if w:
                w.add_system_message("\n".join(lines))
            return

        if cmd == "/mood":
            state = self.mood.get_state()
            display = self.mood.get_display()
            if w:
                w.add_system_message(f"Mood: {display}")
            return

        if cmd.startswith("/code "):
            self._handle_code_command(text.strip()[6:].strip())
            return

        if cmd == "/code":
            self._show_code_status()
            return

        if cmd.startswith("/speak "):
            self._handle_speak_command(text.strip()[7:].strip())
            return

        if cmd == "/tts":
            self._show_tts_status()
            return

        if cmd.startswith("/claude "):
            self._handle_claude_command(text.strip()[8:].strip())
            return

        if cmd == "/claude":
            self._show_claude_status()
            return

        # Unknown command
        if w:
            w.add_system_message(f"Unknown command: {cmd}. Type /help for available commands.")

    def _show_status_in_chat(self) -> None:
        metrics = self.evolution.get_metrics()
        stage = self.evolution.get_stage_info()
        resonance = self.resonance.get_resonance_score()
        bank_stats = self.bank.get_stats()
        mood_state = self.mood.get_state()

        lines = [
            f"=== Kait Status ===",
            f"Version: {VERSION}",
            f"Session: {self._session_id}",
            f"Model: {self._model_name}",
            f"LLM: {'Online' if self._llm_available else 'Offline'}",
            f"Mood: {mood_state.mood} | energy: {mood_state.energy:.1f} | kait: {mood_state.kait_level}",
            f"TTS: {self._tts.active_backend_name if self._tts else 'unavailable'}",
            f"Claude Code: {'available' if self._claude_code and self._claude_code.is_available() else 'unavailable'}",
            f"",
            f"Evolution: Stage {stage['level']} - {stage['name']}",
            f"Interactions: {metrics.total_interactions}",
            f"Corrections: {metrics.corrections_applied}",
            f"Reflections: {metrics.reflection_cycles}",
            f"Resonance: {resonance:.2f}",
            f"Rules: {len(self.reflector.get_active_rules())} active",
            f"",
            f"Memory: {bank_stats.get('interactions', 0)} interactions, "
            f"{bank_stats.get('contexts', 0)} contexts, "
            f"{bank_stats.get('behavior_rules', 0)} rules",
        ]
        if self.window:
            self.window.add_system_message("\n".join(lines))

    def _show_help_in_chat(self) -> None:
        cmds = [
            "/status  -- System status and metrics",
            "/evolve  -- Evolution progress report",
            "/reflect -- Trigger reflection cycle",
            "/tools   -- List available tools",
            "/mood    -- Show current mood state",
            "/code <prompt> -- Send prompt to Claude Code",
            "/code    -- Show Claude Code status",
            "/speak <text> -- Speak text aloud via TTS",
            "/tts     -- Show TTS backend status",
            "/clear   -- Clear chat history",
            "/claude <msg> -- Send message directly to Claude API",
            "/claude  -- Show Claude bridge status",
            "/help    -- Show this help",
            "/quit    -- Exit gracefully",
            "",
            "Shortcuts:",
            "  Ctrl+Shift+V  -- Voice input",
            "  Ctrl+L        -- Clear chat",
            "  Ctrl+Q        -- Quit",
            "  Escape        -- Focus input",
        ]
        if self.window:
            self.window.add_system_message("\n".join(cmds))

    def _handle_code_command(self, prompt: str) -> None:
        """Route a /code <prompt> command to Claude Code."""
        w = self.window
        if not self._claude_code or not self._claude_code.is_available():
            if w:
                w.add_system_message(
                    "Claude Code not available. Install the claude CLI."
                )
            return
        if w:
            w.add_system_message("[Running Claude Code...]")

        def _run():
            try:
                result = self._claude_code.execute(prompt, timeout=120)
                if result.success:
                    msg = f"Claude Code result:\n{result.output[:2000]}"
                else:
                    msg = f"Claude Code error: {result.error}"
            except Exception as exc:
                msg = f"Claude Code failed: {exc}"
            if w and _QT_AVAILABLE:
                self._post_to_gui(lambda: w.add_system_message(msg))

        threading.Thread(target=_run, daemon=True).start()

    def _show_code_status(self) -> None:
        """Display Claude Code status in the GUI."""
        w = self.window
        if self._claude_code and self._claude_code.is_available():
            msg = "Claude Code: AVAILABLE (claude CLI found)"
        elif self._claude_code:
            msg = "Claude Code: loaded but claude CLI not found on PATH."
        else:
            msg = "Claude Code: not available (module not loaded)."
        if w:
            w.add_system_message(msg)

    def _handle_speak_command(self, text: str) -> None:
        """Speak the given text via TTS."""
        w = self.window
        if not self._tts:
            if w:
                w.add_system_message("TTS not available.")
            return
        try:
            self._tts.speak(text)
            if w:
                w.add_system_message(f"Speaking: {text[:80]}...")
        except Exception as exc:
            if w:
                w.add_system_message(f"TTS error: {exc}")

    def _show_tts_status(self) -> None:
        """Display TTS backend status in the GUI."""
        w = self.window
        if self._tts:
            name = self._tts.active_backend_name
            msg = f"TTS: active backend = {name if name else 'none available'}"
        else:
            msg = "TTS: not loaded."
        if w:
            w.add_system_message(msg)

    # ------------------------------------------------------------------
    # LLM Response Generation
    # ------------------------------------------------------------------

    def _generate_response(
        self,
        user_input: str,
        *,
        prompt_fragments: List[str] | None = None,
        tool_output: dict | None = None,
        context: dict | None = None,
        creativity_result: Any = None,
        file_context: str | None = None,
    ) -> str:
        """Generate response via local LLM, with fallback."""
        if not self._llm_available or not self._llm:
            claude_resp = self._escalate_to_claude(user_input, tool_output=tool_output)
            if claude_resp is not None:
                return claude_resp
            if self.window and hasattr(self.window, "update_model_indicator"):
                self.window.update_model_indicator("Offline", "offline")
            return self._fallback_response(user_input, tool_output)

        enriched = self._system_prompt
        enriched += self._build_correction_directive()
        enriched += self._build_creativity_directive(creativity_result)
        enriched += self._build_behavior_rules_directive()

        import json as _json

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": enriched},
        ]

        if context:
            messages.append({
                "role": "system",
                "content": f"Relevant context:\n{_json.dumps(context, indent=2, default=str)}",
            })

        if prompt_fragments:
            frag_str = "\n".join(f"- {f}" for f in prompt_fragments[:5])
            messages.append({"role": "system", "content": f"Response guidance:\n{frag_str}"})

        if tool_output and tool_output.get("success"):
            messages.append({
                "role": "system",
                "content": f"Tool result: {_json.dumps(tool_output.get('result', ''), default=str)}",
            })

        # File attachment context
        if file_context:
            messages.append({
                "role": "system",
                "content": (
                    "The user attached file(s). Use this content to inform your response:\n\n"
                    + file_context
                ),
            })

        # History
        for msg in self._conversation_history[-10:]:
            messages.append(msg)

        messages.append({"role": "user", "content": user_input})

        # Update model indicator
        if self.window and hasattr(self.window, "update_model_indicator"):
            self.window.update_model_indicator(self._model_name, "ollama")

        # Stream tokens if GUI is available, otherwise batch
        try:
            if self.window and _QT_AVAILABLE and hasattr(self._llm, "chat_stream"):
                tokens: List[str] = []
                # Only stream to GUI when TTS is muted (or no TTS).
                # When TTS is active, we collect tokens silently and
                # reveal text via synced-reveal after TTS starts.
                show_live = self._tts_muted or not self._tts
                if show_live:
                    self._post_to_gui(lambda: self.window.chat_panel.begin_streaming())
                token_count = 0
                for token in self._llm.chat_stream(
                    messages=messages,
                    model=self._model_name,
                    temperature=0.7,
                ):
                    tokens.append(token)
                    token_count += 1
                    if show_live:
                        t = token
                        self._post_to_gui(lambda tok=t: self.window.chat_panel.append_token(tok))
                    # Throttled token counter update (every 5 tokens)
                    if token_count % 5 == 0:
                        mon = getattr(self.window, "monitor", None)
                        if mon:
                            tc = token_count
                            self._post_to_gui(lambda c=tc: mon.update_token_count(c))
                # Final token count update
                mon = getattr(self.window, "monitor", None)
                if mon:
                    self._post_to_gui(lambda c=token_count: mon.update_token_count(c))
                return "".join(tokens)
            else:
                result = self._llm.chat(
                    messages=messages,
                    model=self._model_name,
                    temperature=0.7,
                )
                return result.get("content", result.get("message", {}).get("content", ""))
        except Exception as exc:
            log.warning("LLM generation failed: %s", exc)
            claude_resp = self._escalate_to_claude(user_input, tool_output=tool_output)
            if claude_resp is not None:
                return claude_resp
            return self._fallback_response(user_input, tool_output)

    def _fallback_response(self, user_input: str, tool_output: dict | None = None) -> str:
        """Agent-only fallback when LLM is unavailable."""
        parts = ["I'm running without an LLM right now, but I can still help!"]
        if tool_output and tool_output.get("success"):
            parts.append(f"Tool result: {tool_output.get('result', '')}")
        else:
            parts.append(
                "Try starting Ollama with `ollama serve` and pulling a model "
                "with `ollama pull llama3.1:8b` for full conversational abilities."
            )
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Claude Bridge
    # ------------------------------------------------------------------

    def _show_claude_status(self) -> None:
        """Display Claude bridge status in the GUI chat panel."""
        w = self.window
        if self._claude and self._claude.available():
            msg = (
                f"Claude bridge: AVAILABLE  |  Model: {self._claude.model}  |  "
                "API key: configured"
            )
        elif self._claude:
            msg = (
                "Claude bridge: loaded but no API key configured.\n"
                "Set ANTHROPIC_API_KEY in .env to enable."
            )
        else:
            msg = "Claude bridge: not available (module not loaded)."
        if w:
            w.add_system_message(msg)

    def _handle_claude_command(self, message: str) -> None:
        """Route a /claude <message> command directly to Claude."""
        w = self.window
        if not self._claude or not self._claude.available():
            if w:
                w.add_system_message(
                    "Claude bridge not available. Set ANTHROPIC_API_KEY in .env."
                )
            return

        if w:
            mon = getattr(w, "monitor", None)
            if mon:
                self._post_to_gui(lambda: mon.append_feed_entry("\u25B6 Sending to Claude..."))

        import json as _json
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
        ]
        for msg in self._conversation_history[-5:]:
            messages.append(msg)
        messages.append({"role": "user", "content": message})

        response = self._run_claude_streamed(messages)
        if response:
            self._conversation_history.append({"role": "user", "content": message})
            self._conversation_history.append({"role": "assistant", "content": response})
        elif w:
            w.add_system_message("Claude did not return a response.")

    def _escalate_to_claude(
        self,
        user_input: str,
        *,
        tool_output: dict | None = None,
    ) -> Optional[str]:
        """Try to generate a response via Claude bridge."""
        if not self._claude or not self._claude.available():
            return None

        log.info("Escalating to Claude bridge")
        w = self.window
        if w:
            mon = getattr(w, "monitor", None)
            if mon:
                self._post_to_gui(lambda: mon.append_feed_entry("\u25B6 Escalating to Claude..."))
            if hasattr(w, "update_model_indicator"):
                w.update_model_indicator(self._claude.model, "claude")

        escalation_system = (
            "You are Kait, a personal AI sidekick. The user's local LLM was "
            "unable to handle this request, so you are providing a cloud-backed "
            "response. Be conversational, warm, and concise. Technical details "
            "are shown in the Monitor tab -- keep chat responses human and brief."
        )

        import json as _json
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system_prompt + "\n\n" + escalation_system},
        ]
        if tool_output and tool_output.get("success"):
            messages.append({
                "role": "system",
                "content": f"Tool result: {_json.dumps(tool_output.get('result', ''), default=str)}",
            })
        for msg in self._conversation_history[-5:]:
            messages.append(msg)
        messages.append({"role": "user", "content": user_input})

        return self._run_claude_streamed(messages)

    def _run_claude_streamed(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Stream a Claude response into the GUI chat panel and return full text."""
        w = self.window
        tokens: List[str] = []
        show_live = self._tts_muted or not self._tts
        token_count = 0

        try:
            if w and _QT_AVAILABLE and show_live:
                self._post_to_gui(lambda: w.chat_panel.begin_streaming())
            for token in self._claude.chat_stream(messages=messages):
                tokens.append(token)
                token_count += 1
                if w and _QT_AVAILABLE and show_live:
                    t = token
                    self._post_to_gui(lambda tok=t: w.chat_panel.append_token(tok))
                # Throttled token counter update (every 5 tokens)
                if w and token_count % 5 == 0:
                    mon = getattr(w, "monitor", None)
                    if mon:
                        tc = token_count
                        self._post_to_gui(lambda c=tc: mon.update_token_count(c))
            # Final token count update
            if w:
                mon = getattr(w, "monitor", None)
                if mon:
                    self._post_to_gui(lambda c=token_count: mon.update_token_count(c))
        except Exception as exc:
            log.error("Claude streaming failed: %s", exc)

        return "".join(tokens).strip() if tokens else None

    # ------------------------------------------------------------------
    # Directive builders
    # ------------------------------------------------------------------

    def _build_correction_directive(self) -> str:
        corrections = self.bank.get_recent_corrections(limit=5)
        if not corrections:
            return ""
        lines = []
        for c in corrections:
            reason = c.get("reason", "")
            if reason:
                lines.append(f"- AVOID: {reason}")
        if not lines:
            return ""
        return (
            "\n\n## Critical: Past Mistakes to Avoid\n"
            "Do NOT repeat these:\n" + "\n".join(lines)
        )

    def _build_creativity_directive(self, creativity_result: Any) -> str:
        if not creativity_result or not getattr(creativity_result, "success", False):
            return ""
        data = creativity_result.data if isinstance(creativity_result.data, dict) else {}
        metaphor = data.get("metaphor", "")
        parts = []
        if metaphor:
            parts.append(f'Weave this metaphor: "{metaphor}"')
        parts.append("Bring a KAIT to this response -- vivid, insightful, memorable.")
        return "\n\n## Mandatory Creative Kait\n" + "\n".join(f"- {p}" for p in parts)

    def _build_behavior_rules_directive(self) -> str:
        rules = self.reflector.get_active_rules()
        if not rules:
            return ""
        lines = [r.to_prompt_instruction() for r in rules[:8]]
        return (
            "\n\n## Learned Behavior Rules\n"
            + "\n".join(f"- {l}" for l in lines)
        )

    # ------------------------------------------------------------------
    # Context retrieval
    # ------------------------------------------------------------------

    _STOP_WORDS = frozenset(
        "the a an is are was were be been being have has had do does did "
        "will would shall should may might can could of in on at to for "
        "with by from as into about between through during it its i me my "
        "we our you your he she they them this that what which who how".split()
    )

    def _retrieve_context(self, user_input: str) -> Dict[str, Any]:
        """Retrieve relevant context from ReasoningBank."""
        tokens = {
            w.lower() for w in user_input.split()
            if len(w) > 2 and w.lower() not in self._STOP_WORDS
        }
        if not tokens:
            return {}

        context: Dict[str, Any] = {}
        try:
            history = self.bank.get_interaction_history(limit=20, session_id=None)
            relevant = []
            for h in history:
                h_text = (h.get("user_input", "") + " " + h.get("ai_response", "")).lower()
                h_tokens = {w for w in h_text.split() if len(w) > 2 and w not in self._STOP_WORDS}
                overlap = len(tokens & h_tokens)
                if overlap >= 2:
                    relevant.append({
                        "user_input": h.get("user_input", ""),
                        "ai_response": h.get("ai_response", "")[:200],
                        "relevance": overlap,
                    })
            if relevant:
                relevant.sort(key=lambda x: x["relevance"], reverse=True)
                context["relevant_memory"] = relevant[:3]
        except Exception as exc:
            log.debug("Context retrieval error: %s", exc)

        return context

    @staticmethod
    def _extract_tool_args(tool_name: str, user_input: str) -> Dict[str, Any]:
        """Extract tool arguments from user input."""
        import re
        if tool_name == "calculator":
            match = re.search(r"[\d.]+(?:\s*[+\-*/^%]\s*[\d.]+)+", user_input)
            if match:
                return {"expression": match.group(0)}
            return {"expression": user_input}
        if tool_name == "datetime_tool":
            return {"action": "now"}
        if tool_name == "system_info":
            return {}
        if tool_name == "text_tool":
            return {"action": "word_count", "text": user_input}
        return {"input": user_input}

    # ------------------------------------------------------------------
    # Reflection & Evolution
    # ------------------------------------------------------------------

    def _maybe_reflect(self) -> None:
        if self.scheduler.should_reflect(self._last_reflection_ts, self._interaction_count):
            self._do_reflection()

    def _do_reflection(self) -> None:
        try:
            history = self.bank.get_interaction_history(limit=20, session_id=None)
            corrections = self.bank.get_recent_corrections(limit=10)
            evo_timeline = self.bank.get_evolution_timeline(limit=5)

            result = self.reflector.reflect(
                interactions=[dict(h) for h in history],
                corrections=[dict(c) for c in corrections],
                evolution_history=[dict(e) for e in evo_timeline],
            )

            self._last_reflection_ts = time.time()
            self.evolution.record_reflection_cycle()

            insights = result.get("insights", [])
            if insights and self.window:
                msg = f"Reflection complete: {insights[0]}"
                self._post_to_gui(lambda: self.window.add_system_message(msg))
            log.info("Reflection completed: %d insights", len(insights))
        except Exception as exc:
            log.warning("Reflection error: %s", exc)

    def _maybe_evolve(self) -> None:
        if self.evolution.check_evolution_threshold():
            result = self.evolution.evolve()
            if result.get("evolved"):
                new_stage = result["to_stage"]
                stage_name = result.get("to_name", "Unknown")
                self.mood.evolve(min(5, new_stage))
                self._play_sound("evolve")
                if self.window and _QT_AVAILABLE:
                    evo_msg = f"EVOLUTION! Kait has reached Stage {new_stage}: {stage_name}!"
                    self._post_to_gui(lambda: self.window.add_system_message(evo_msg))
                log.info("Evolved to stage %d: %s", new_stage, stage_name)

    # ------------------------------------------------------------------
    # Dashboard push
    # ------------------------------------------------------------------

    def _push_dashboard_update(self) -> None:
        if not self.window:
            return
        try:
            metrics = self.evolution.get_metrics()
            stage = self.evolution.get_stage_info()
            resonance = self.resonance.get_resonance_score()
            bank_stats = self.bank.get_stats()

            if hasattr(self.window, "dashboard"):
                self.window.dashboard.update_evolution(
                    stage=stage["level"],
                    stage_name=stage["name"],
                    progress_pct=min(100, int(metrics.total_interactions / max(1, stage.get("next_threshold", 25)) * 100)),
                    interactions=metrics.total_interactions,
                    corrections=metrics.corrections_applied,
                    reflections=metrics.reflection_cycles,
                )
                self.window.dashboard.update_resonance(resonance)
                self.window.dashboard.update_bank_stats(bank_stats)

            # Push same data to the Monitor tab
            if hasattr(self.window, "monitor"):
                self.window.monitor.update_metrics({
                    "Interactions": metrics.total_interactions,
                    "Corrections": metrics.corrections_applied,
                    "Reflections": metrics.reflection_cycles,
                    "Resonance": f"{resonance:.2f}",
                    "Evolution": f"Stage {stage['level']} - {stage['name']}",
                    "Memory": f"{bank_stats.get('interactions', 0)} stored",
                })
        except Exception as exc:
            log.debug("Dashboard update error: %s", exc)

    # ------------------------------------------------------------------
    # Preferences persistence
    # ------------------------------------------------------------------

    def _persist_prefs(self) -> None:
        """Save current preferences to config file."""
        try:
            existing = {}
            if self._config_path.exists():
                existing = json.loads(self._config_path.read_text())
            if self.window and _QT_AVAILABLE:
                existing["theme"] = getattr(self.window, "_current_theme_name", "dark")
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(json.dumps(existing, indent=2))
        except Exception:
            pass

    def _restore_ui_prefs(self) -> None:
        """Restore saved theme settings on startup."""
        try:
            if not self._config_path.exists():
                return
            prefs = json.loads(self._config_path.read_text())
            theme_name = prefs.get("theme", "dark")
            if self.window and _QT_AVAILABLE and theme_name != "dark":
                if hasattr(self.window, "apply_theme"):
                    self.window.apply_theme(theme_name)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def _apply_personality_to_prompt(self) -> None:
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

    def _restore_session_context(self) -> None:
        try:
            ctx = self.bank.get_context("last_session_summary")
            if ctx and isinstance(ctx.get("value"), dict):
                self._last_session = ctx["value"]
                last_turns = self._last_session.get("last_turns", [])
                if last_turns:
                    self._conversation_history = list(last_turns)
            else:
                self._last_session = None
        except Exception:
            self._last_session = None

    def _show_welcome(self) -> None:
        """Show Kait's welcome greeting on startup."""
        if not self.window:
            return
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
        self.window.chat_panel.add_message(
            ChatMessage("assistant", greeting, sentiment="positive")
        )
        if self._tts and not self._tts_muted:
            try:
                self._tts.speak(greeting)
            except Exception:
                pass

    def _show_welcome_back(self) -> None:
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
        if self.window:
            self.window.add_system_message(
                f"Welcome back! Last session ({time_str}): "
                f"{count} exchanges about {topic_str}. Let's continue!"
            )

    def _save_session_summary(self) -> None:
        try:
            topics = set()
            for msg in self._conversation_history:
                if msg.get("role") == "user":
                    content = msg.get("content", "").lower()
                    for kw, domain in {
                        "code": "coding", "debug": "debugging",
                        "math": "math", "write": "writing",
                        "help": "help", "error": "troubleshooting",
                    }.items():
                        if kw in content:
                            topics.add(domain)
            if not topics:
                topics.add("general conversation")

            self.bank.update_context(
                "last_session_summary",
                {
                    "session_id": self._session_id,
                    "interaction_count": self._interaction_count,
                    "topics": list(topics)[:5],
                    "stage": self.evolution.get_metrics().evolution_stage,
                    "resonance": self.resonance.get_resonance_score(),
                    "timestamp": time.time(),
                    "last_turns": self._conversation_history[-6:],
                },
                "session",
            )
        except Exception as exc:
            log.debug("Failed to save session: %s", exc)

    # ------------------------------------------------------------------
    # Audio cues
    # ------------------------------------------------------------------

    def _play_sound(self, cue: str) -> None:
        """Play a subtle audio cue via AudioCueManager. No-op if unavailable."""
        if self._audio:
            try:
                self._audio.play_cue(cue)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        log.info("Shutting down Kait...")
        self._save_session_summary()

        # Stop TTS
        if self._tts:
            try:
                self._tts.stop()
            except Exception:
                pass

        # Persist mood state
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
                },
                "avatar",
            )
        except Exception:
            pass

        # Close mood tracker
        self.mood.close()

        # Stop health polling
        if self._health_timer is not None:
            self._health_timer.stop()
            self._health_timer = None

        # Stop background services if we started them
        self._stop_background_services()

        # Always stop the matrix worker on app shutdown, even if this
        # instance didn't originally start it.
        self._stop_matrix_worker()

        self._shutdown_event.set()
        log.info("Kait shutdown complete.")


# ===================================================================
# Pre-flight checks
# ===================================================================

def run_preflight_checks(verbose: bool = True) -> List[Dict[str, Any]]:
    """Run pre-flight system checks."""
    import shutil
    checks = []

    # Python version
    v = sys.version_info
    checks.append({
        "ok": v >= (3, 10),
        "name": "Python version",
        "detail": f"{v.major}.{v.minor}.{v.micro}",
        "fix": "Python 3.10+ required",
    })

    # Ollama binary
    ollama_path = shutil.which("ollama")
    checks.append({
        "ok": ollama_path is not None,
        "name": "Ollama binary",
        "detail": ollama_path or "not found",
        "fix": "Install from https://ollama.ai",
    })

    # Ollama server
    try:
        client = OllamaClient()
        server_ok = client.health_check()
    except Exception:
        server_ok = False
    checks.append({
        "ok": server_ok,
        "name": "Ollama server",
        "detail": "running" if server_ok else "not running",
        "fix": "Start with: ollama serve",
    })

    # Data directory
    data_dir = Path.home() / ".kait"
    data_dir.mkdir(parents=True, exist_ok=True)
    checks.append({
        "ok": data_dir.exists() and os.access(str(data_dir), os.W_OK),
        "name": "Data directory",
        "detail": str(data_dir),
        "fix": f"Ensure {data_dir} is writable",
    })

    # PyQt GUI
    checks.append({
        "ok": _QT_AVAILABLE,
        "name": "PyQt GUI",
        "detail": "available" if _QT_AVAILABLE else "not installed",
        "fix": "pip install PyQt6",
    })

    # TTS
    checks.append({
        "ok": _TTS_AVAILABLE,
        "name": "TTS engine",
        "detail": "available" if _TTS_AVAILABLE else "not installed",
        "fix": "pip install sounddevice soundfile",
    })

    return checks


# ===================================================================
# CLI fallback (when PyQt is not available)
# ===================================================================

def _run_cli_mode() -> None:
    """Run in terminal-only mode, delegating to kait_ai_sidekick.py."""
    print("PyQt not available. Launching terminal mode...")
    try:
        from kait_ai_sidekick import KaitSidekick
        sidekick = KaitSidekick()
        sidekick.run()
    except ImportError:
        print("ERROR: Could not import kait_ai_sidekick.py")
        sys.exit(1)


# ===================================================================
# Main entry point
# ===================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kait -- Kait AI Intel with Modern Dark GUI"
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in terminal-only mode (no GUI)",
    )
    parser.add_argument(
        "--onboard", action="store_true",
        help="Force the onboarding wizard",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show evolution status and exit",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Run pre-flight checks and exit",
    )
    parser.add_argument(
        "--no-services", action="store_true",
        help="Launch GUI without auto-starting background services",
    )
    parser.add_argument(
        "--tts-backend", type=str, default=None,
        help="TTS backend: auto|elevenlabs|openai|piper|say",
    )
    parser.add_argument(
        "--voice", type=str, default=None,
        help="TTS voice name/ID",
    )
    parser.add_argument(
        "--no-tts", action="store_true",
        help="Disable text-to-speech",
    )
    args = parser.parse_args()

    # Apply TTS env vars before anything imports TTSEngine
    if args.tts_backend:
        os.environ["KAIT_TTS_BACKEND"] = args.tts_backend
    if args.voice:
        os.environ["KAIT_TTS_VOICE"] = args.voice
    if args.no_tts:
        os.environ["KAIT_TTS_BACKEND"] = "none"

    # Pre-flight check mode
    if args.check:
        checks = run_preflight_checks(verbose=True)
        all_ok = True
        for c in checks:
            icon = "OK" if c["ok"] else "FAIL"
            print(f"  [{icon}] {c['name']}: {c['detail']}")
            if not c["ok"]:
                all_ok = False
                if c.get("fix"):
                    print(f"       Fix: {c['fix']}")
        sys.exit(0 if all_ok else 1)

    # Status mode
    if args.status:
        engine = load_evolution_engine()
        report = engine.get_evolution_report()
        print(report)
        sys.exit(0)

    # CLI mode
    if args.cli or not _QT_AVAILABLE:
        _run_cli_mode()
        return

    # --- GUI Mode ---
    app = QApplication(sys.argv)
    app.setApplicationName("Kait")
    app.setStyleSheet(DARK_STYLESHEET)

    # Onboarding wizard
    onboard_prefs = None
    config_path = Path.home() / ".kait" / "kait_config.json"

    if args.onboard or not config_path.exists():
        wizard = OnboardingWizard()
        if wizard.exec() != wizard.DialogCode.Accepted:
            sys.exit(0)
        onboard_prefs = {
            "model": wizard.selected_model,
            "voice_enabled": wizard.voice_enabled,
            "sound_enabled": wizard.sound_enabled,
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(onboard_prefs, indent=2))
    else:
        try:
            onboard_prefs = json.loads(config_path.read_text())
        except Exception:
            onboard_prefs = {}

    # Create main window
    window = KaitMainWindow()
    window.show()

    # Create controller
    controller = KaitController(window, onboard_prefs)
    controller._auto_services = not args.no_services

    # Ensure shutdown fires on window close, Ctrl+Q, signals, etc.
    app.aboutToQuit.connect(controller._shutdown)

    # Startup (connect LLM, show greeting)
    QTimer.singleShot(100, controller.startup)

    # Handle OS signals
    def _signal_handler(signum, frame):
        controller._shutdown()
        app.quit()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Allow Ctrl+C in terminal
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
