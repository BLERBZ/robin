"""
Multi-Agent Architecture for Kait AI Intel.

Each agent is a specialized sub-processor that the orchestrator dispatches to.
Agents do NOT call LLMs directly -- they prepare structured prompts/contexts
that the main loop sends to the LLM.  This keeps them fast, deterministic,
and testable without network calls.

Agent roster:
- ReflectionAgent: Analyzes past interactions, identifies patterns, suggests improvements
- CreativityAgent: Generates kait-infused creative enhancements (humor, metaphors, mood)
- LogicAgent: Structured reasoning, math scaffolding, deduction chains
- ToolAgent: Local tool dispatch (file I/O, math, system queries)
- SentimentAgent: User sentiment analysis, emotional pattern tracking

Orchestrator:
- AgentOrchestrator: Routes tasks to agents, supports multi-dispatch, tracks stats
"""

from __future__ import annotations

import logging
import math
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("kait.sidekick.agents")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentType(str, Enum):
    """Canonical agent identifiers used for dispatch routing."""
    REFLECTION = "reflection"
    CREATIVITY = "creativity"
    LOGIC = "logic"
    TOOL = "tool"
    SENTIMENT = "sentiment"
    BROWSER = "browser"
    CLAUDE_CODE = "claude_code"


class SentimentLabel(str, Enum):
    """Discrete sentiment categories."""
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class SidekickMood(str, Enum):
    """Suggested sidekick mood states the creativity agent can emit."""
    EXCITED = "excited"
    CALM = "calm"
    CURIOUS = "curious"
    PLAYFUL = "playful"
    FOCUSED = "focused"
    EMPATHETIC = "empathetic"
    PROUD = "proud"


# Backward-compatible alias
AvatarMood = SidekickMood


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Structured return value from every agent invocation.

    Attributes:
        agent: Which agent produced this result.
        success: Whether the agent completed without critical errors.
        confidence: 0.0-1.0 self-assessed confidence in the result quality.
        data: Arbitrary payload (prompt fragments, analyses, tool outputs, etc.)
        errors: Non-fatal issues encountered during processing.
        processing_time_ms: Wall-clock time spent in the agent.
        prompt_fragments: Ordered list of text snippets intended to be injected
            into the final LLM prompt.  The main loop concatenates these.
    """
    agent: str
    success: bool = True
    confidence: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    prompt_fragments: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "success": self.success,
            "confidence": round(self.confidence, 4),
            "data": self.data,
            "errors": self.errors,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "prompt_fragments": self.prompt_fragments,
        }


# ---------------------------------------------------------------------------
# Agent performance tracker
# ---------------------------------------------------------------------------

@dataclass
class _AgentStats:
    """Internal bookkeeping for a single agent's performance."""
    invocations: int = 0
    total_time_ms: float = 0.0
    error_count: int = 0
    last_invoked: float = 0.0

    @property
    def avg_time_ms(self) -> float:
        if self.invocations == 0:
            return 0.0
        return self.total_time_ms / self.invocations

    def record(self, elapsed_ms: float, had_error: bool) -> None:
        self.invocations += 1
        self.total_time_ms += elapsed_ms
        self.last_invoked = time.time()
        if had_error:
            self.error_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invocations": self.invocations,
            "avg_time_ms": round(self.avg_time_ms, 2),
            "total_time_ms": round(self.total_time_ms, 2),
            "error_count": self.error_count,
            "last_invoked": self.last_invoked,
        }


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class SidekickAgent(ABC):
    """Abstract base for all sidekick sub-agents.

    Sub-classes must implement ``process(context)`` which receives the full
    task context dict and returns an ``AgentResult``.

    The base class handles:
    - Wall-clock timing and stats tracking
    - Graceful error wrapping (partial results on exception)
    - Structured logging
    """

    def __init__(self, agent_type: AgentType) -> None:
        self.agent_type = agent_type
        self._stats = _AgentStats()

    # -- public entry point --------------------------------------------------

    def run(self, context: Dict[str, Any]) -> AgentResult:
        """Execute the agent with timing, error handling, and logging.

        Callers should use ``run()`` rather than ``process()`` directly.
        """
        start = time.monotonic()
        try:
            result = self.process(context)
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000.0
            log.warning(
                "Agent %s raised %s: %s",
                self.agent_type.value, type(exc).__name__, exc,
            )
            result = AgentResult(
                agent=self.agent_type.value,
                success=False,
                confidence=0.0,
                errors=[f"{type(exc).__name__}: {exc}"],
                processing_time_ms=elapsed,
            )
        else:
            elapsed = (time.monotonic() - start) * 1000.0
            result.processing_time_ms = elapsed

        self._stats.record(elapsed, had_error=not result.success)
        log.debug(
            "Agent %s finished in %.1f ms (ok=%s, confidence=%.2f)",
            self.agent_type.value,
            result.processing_time_ms,
            result.success,
            result.confidence,
        )
        return result

    @abstractmethod
    def process(self, context: Dict[str, Any]) -> AgentResult:
        """Produce an ``AgentResult`` for the given *context*.

        Implementations must NOT call LLMs.  They prepare prompt fragments
        and structured data that the main loop will forward to the model.
        """
        ...

    @property
    def stats(self) -> Dict[str, Any]:
        return self._stats.to_dict()


# ---------------------------------------------------------------------------
# ReflectionAgent
# ---------------------------------------------------------------------------

class ReflectionAgent(SidekickAgent):
    """Analyzes past interactions and behaviors to identify patterns and
    generate self-improvement suggestions.

    Looks at the ReasoningBank history (if available) and the current
    conversation context to surface:
    - Recurring user frustration signals
    - Patterns in successful vs. failed exchanges
    - Concrete suggestions for behavior adjustments
    """

    # Lightweight keyword signals (no NLP dependency).
    _FRUSTRATION_SIGNALS: Tuple[str, ...] = (
        "frustrated", "annoyed", "confused", "wrong", "not what i",
        "try again", "that's incorrect", "you keep", "stop",
    )
    _SUCCESS_SIGNALS: Tuple[str, ...] = (
        "perfect", "great", "thanks", "exactly", "nice", "love it",
        "well done", "awesome", "works",
    )

    def __init__(self) -> None:
        super().__init__(AgentType.REFLECTION)

    def process(self, context: Dict[str, Any]) -> AgentResult:
        history: List[Dict[str, Any]] = context.get("history", [])
        corrections: List[Dict[str, Any]] = context.get("corrections", [])
        current_message: str = context.get("user_message", "")

        patterns = self._detect_patterns(history)
        suggestions = self._generate_suggestions(patterns, corrections)
        frustration_score = self._assess_frustration(history, current_message)

        fragments: List[str] = []
        if suggestions:
            joined = "; ".join(suggestions[:3])
            fragments.append(
                f"[Reflection] Self-improvement notes: {joined}"
            )
        if frustration_score > 0.6:
            fragments.append(
                "[Reflection] User frustration detected -- simplify, "
                "acknowledge the difficulty, and ask a clarifying question."
            )

        confidence = min(1.0, 0.3 + 0.1 * len(history))

        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=confidence,
            data={
                "patterns": patterns,
                "suggestions": suggestions,
                "frustration_score": round(frustration_score, 3),
                "history_depth": len(history),
            },
            prompt_fragments=fragments,
        )

    # -- internals -----------------------------------------------------------

    def _detect_patterns(
        self, history: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """Scan history for repeated themes."""
        patterns: List[Dict[str, str]] = []
        topic_counts: Dict[str, int] = {}

        for entry in history:
            topic = str(entry.get("topic", "")).strip().lower()
            if topic:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

        for topic, count in topic_counts.items():
            if count >= 2:
                patterns.append({
                    "type": "recurring_topic",
                    "topic": topic,
                    "occurrences": str(count),
                })

        return patterns

    def _generate_suggestions(
        self,
        patterns: List[Dict[str, str]],
        corrections: List[Dict[str, Any]],
    ) -> List[str]:
        suggestions: List[str] = []

        for pat in patterns:
            if pat["type"] == "recurring_topic":
                suggestions.append(
                    f"Topic '{pat['topic']}' recurs ({pat['occurrences']}x) "
                    f"-- consider proactively addressing it."
                )

        if len(corrections) >= 3:
            suggestions.append(
                "Multiple corrections detected -- slow down and confirm "
                "understanding before acting."
            )

        if not suggestions:
            suggestions.append(
                "No strong patterns yet -- continue gathering data."
            )

        return suggestions

    def _assess_frustration(
        self, history: List[Dict[str, Any]], current: str,
    ) -> float:
        """Return 0.0-1.0 frustration estimate from recent history."""
        score = 0.0
        texts = [current.lower()] + [
            str(h.get("text", "")).lower() for h in history[-5:]
        ]
        for text in texts:
            for signal in self._FRUSTRATION_SIGNALS:
                if signal in text:
                    score += 0.15
            for signal in self._SUCCESS_SIGNALS:
                if signal in text:
                    score -= 0.05
        return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# CreativityAgent
# ---------------------------------------------------------------------------

class CreativityAgent(SidekickAgent):
    """Generates creative, kait-infused enhancements for responses.

    Adds:
    - Contextual metaphors and analogies
    - Humor calibrated to the tone of conversation
    - Visual/avatar mood suggestions
    - Vivid descriptions that make technical content memorable
    """

    _METAPHOR_BANK: Dict[str, List[str]] = {
        "debugging": [
            "like a detective dusting for fingerprints in a codebase",
            "peeling back layers of an onion -- each one might make you cry",
            "navigating a maze where the walls keep shifting",
        ],
        "architecture": [
            "building a cathedral -- every stone must bear its neighbor's weight",
            "like city planning: zoning matters more than any single building",
            "a symphony where each instrument must know when to play and when to rest",
        ],
        "learning": [
            "planting seeds -- growth is invisible until one day the garden blooms",
            "climbing a spiral staircase: you revisit the same view from higher up",
            "training a muscle -- repetition builds strength you can't see yet",
        ],
        "performance": [
            "tuning a race car -- small adjustments compound into big wins",
            "squeezing water from a stone: diminishing returns demand creativity",
            "sharpening a blade -- it cuts better not because it's bigger, but finer",
        ],
        "general": [
            "connecting dots that didn't know they were part of the same picture",
            "untangling headphones -- patience beats force every time",
            "surfing: you can't control the wave, only how you ride it",
        ],
    }

    _MOOD_MAP: Dict[str, SidekickMood] = {
        "debugging": SidekickMood.FOCUSED,
        "architecture": SidekickMood.CURIOUS,
        "learning": SidekickMood.EXCITED,
        "performance": SidekickMood.PROUD,
        "celebration": SidekickMood.PLAYFUL,
        "support": SidekickMood.EMPATHETIC,
    }

    def __init__(self) -> None:
        super().__init__(AgentType.CREATIVITY)

    def process(self, context: Dict[str, Any]) -> AgentResult:
        user_message: str = context.get("user_message", "")
        topic: str = context.get("topic", "general")
        tone: str = context.get("tone", "balanced")

        metaphor = self._pick_metaphor(topic, user_message)
        mood = self._suggest_mood(topic, user_message)
        style_hints = self._style_hints(tone)

        fragments: List[str] = []
        if metaphor:
            fragments.append(
                f"[Creativity] Consider weaving in this metaphor: \"{metaphor}\""
            )
        if mood:
            fragments.append(
                f"[Creativity] Suggested avatar mood: {mood.value}"
            )
        if style_hints:
            fragments.append(
                f"[Creativity] Style guidance: {style_hints}"
            )

        confidence = 0.65 if metaphor else 0.4

        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=confidence,
            data={
                "metaphor": metaphor,
                "suggested_mood": mood.value if mood else None,
                "style_hints": style_hints,
                "topic_detected": topic,
            },
            prompt_fragments=fragments,
        )

    # -- internals -----------------------------------------------------------

    def _pick_metaphor(self, topic: str, message: str) -> Optional[str]:
        """Select a contextually appropriate metaphor."""
        bank = self._METAPHOR_BANK.get(topic.lower())
        if not bank:
            # Fall back to keyword scanning.
            msg_lower = message.lower()
            for key, candidates in self._METAPHOR_BANK.items():
                if key in msg_lower:
                    bank = candidates
                    break
        if not bank:
            bank = self._METAPHOR_BANK["general"]

        # Deterministic selection based on message length (cheap hash).
        idx = len(message) % len(bank)
        return bank[idx]

    def _suggest_mood(self, topic: str, message: str) -> Optional[AvatarMood]:
        """Map topic/context to an avatar mood."""
        mood = self._MOOD_MAP.get(topic.lower())
        if mood:
            return mood

        msg_lower = message.lower()
        if any(w in msg_lower for w in ("thank", "awesome", "great", "love")):
            return AvatarMood.PLAYFUL
        if any(w in msg_lower for w in ("help", "stuck", "confused", "wrong")):
            return AvatarMood.EMPATHETIC
        if any(w in msg_lower for w in ("how", "why", "what if", "explore")):
            return AvatarMood.CURIOUS

        return AvatarMood.CALM

    def _style_hints(self, tone: str) -> str:
        hints: Dict[str, str] = {
            "playful": "Use light humor and conversational phrasing. Emojis welcome.",
            "technical": "Stay precise but add one vivid analogy to anchor the concept.",
            "empathetic": "Lead with acknowledgment. Mirror the user's emotional register.",
            "balanced": "Mix clarity with warmth. One metaphor per major idea.",
        }
        return hints.get(tone.lower(), hints["balanced"])


# ---------------------------------------------------------------------------
# LogicAgent
# ---------------------------------------------------------------------------

class LogicAgent(SidekickAgent):
    """Handles structured reasoning, math scaffolding, and logical deduction.

    Produces step-by-step reasoning chains that the LLM can follow or verify.
    Does NOT solve arbitrary math -- it sets up the scaffold (identify
    knowns/unknowns, suggest approach, structure the proof/deduction).
    """

    _MATH_PATTERN = re.compile(
        r"(?:what is|calculate|compute|solve|evaluate|how much|how many)"
        r"|[\d]+\s*[+\-*/^%]\s*[\d]+"
        r"|(?:sum|product|difference|ratio|average|mean|median)\b",
        re.IGNORECASE,
    )

    _LOGIC_KEYWORDS: Tuple[str, ...] = (
        "therefore", "implies", "if and only if", "because",
        "given that", "assuming", "conclude", "deduce",
        "prove", "contradict", "follows from",
    )

    def __init__(self) -> None:
        super().__init__(AgentType.LOGIC)

    def process(self, context: Dict[str, Any]) -> AgentResult:
        user_message: str = context.get("user_message", "")
        task_data: Dict[str, Any] = context.get("task_data", {})

        is_math = bool(self._MATH_PATTERN.search(user_message))
        is_logic = any(kw in user_message.lower() for kw in self._LOGIC_KEYWORDS)

        chain: List[str] = []
        approach = "general_reasoning"

        if is_math:
            approach = "mathematical"
            chain = self._build_math_scaffold(user_message, task_data)
        elif is_logic:
            approach = "logical_deduction"
            chain = self._build_logic_chain(user_message, task_data)
        else:
            approach = "structured_analysis"
            chain = self._build_analysis_scaffold(user_message, task_data)

        fragments: List[str] = []
        if chain:
            numbered = "\n".join(
                f"  {i+1}. {step}" for i, step in enumerate(chain)
            )
            fragments.append(
                f"[Logic] Reasoning scaffold ({approach}):\n{numbered}"
            )

        confidence = 0.7 if chain else 0.3

        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=confidence,
            data={
                "approach": approach,
                "is_math": is_math,
                "is_logic": is_logic,
                "reasoning_chain": chain,
                "chain_length": len(chain),
            },
            prompt_fragments=fragments,
        )

    # -- scaffolds -----------------------------------------------------------

    def _build_math_scaffold(
        self, message: str, task_data: Dict[str, Any],
    ) -> List[str]:
        """Create a step-by-step math reasoning scaffold."""
        steps: List[str] = [
            "Identify the quantities and unknowns in the problem.",
            "Determine which mathematical operation(s) apply.",
            "Set up the expression or equation.",
            "Compute step-by-step, showing intermediate results.",
            "Verify the result with a sanity check or estimation.",
        ]

        # If task_data provides explicit knowns, embed them.
        knowns = task_data.get("knowns")
        if isinstance(knowns, dict) and knowns:
            known_str = ", ".join(
                f"{k}={v}" for k, v in knowns.items()
            )
            steps[0] = f"Known values: {known_str}. Identify any remaining unknowns."

        return steps

    def _build_logic_chain(
        self, message: str, task_data: Dict[str, Any],
    ) -> List[str]:
        premises = task_data.get("premises", [])
        steps: List[str] = []

        if premises:
            for i, p in enumerate(premises, 1):
                steps.append(f"Premise {i}: {p}")
            steps.append("Check premises for internal consistency.")
        else:
            steps.append("Extract all premises/assumptions from the statement.")
            steps.append("Check premises for internal consistency.")

        steps.extend([
            "Apply relevant rules of inference (modus ponens, etc.).",
            "Derive intermediate conclusions.",
            "State the final conclusion with supporting chain.",
            "Identify any assumptions that could weaken the conclusion.",
        ])
        return steps

    def _build_analysis_scaffold(
        self, message: str, task_data: Dict[str, Any],
    ) -> List[str]:
        return [
            "Restate the problem in clear, unambiguous terms.",
            "Break the problem into independent sub-questions.",
            "For each sub-question, identify what information is needed.",
            "Synthesize sub-answers into a coherent overall answer.",
            "Flag remaining uncertainties or areas needing clarification.",
        ]


# ---------------------------------------------------------------------------
# ToolAgent
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    """Describes a registered local tool."""
    name: str
    description: str
    handler: Callable[..., Dict[str, Any]]
    parameters: Dict[str, str] = field(default_factory=dict)


class ToolAgent(SidekickAgent):
    """Dispatches and manages local tools (file I/O, math, system queries).

    Maintains a registry of available tools and either executes them directly
    (for safe, deterministic tools like math) or prepares structured prompts
    describing available tools for the LLM to invoke through the main loop.
    """

    def __init__(self) -> None:
        super().__init__(AgentType.TOOL)
        self._registry: Dict[str, ToolSpec] = {}
        self._register_builtins()

    def register_tool(self, spec: ToolSpec) -> None:
        """Add a tool to the registry."""
        self._registry[spec.name] = spec
        log.debug("Registered tool: %s", spec.name)

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool from the registry.  Returns True if it existed."""
        return self._registry.pop(name, None) is not None

    @property
    def available_tools(self) -> List[str]:
        return sorted(self._registry.keys())

    def process(self, context: Dict[str, Any]) -> AgentResult:
        tool_name: str = context.get("tool_name", "")
        tool_args: Dict[str, Any] = context.get("tool_args", {})
        user_message: str = context.get("user_message", "")

        # If no explicit tool requested, try to detect one.
        if not tool_name:
            tool_name = self._detect_tool(user_message)

        if tool_name and tool_name in self._registry:
            return self._execute_tool(tool_name, tool_args)

        # No tool matched -- return tool inventory for the LLM.
        inventory = [
            {"name": s.name, "description": s.description, "params": s.parameters}
            for s in self._registry.values()
        ]

        fragments: List[str] = []
        if inventory:
            tool_list = ", ".join(t["name"] for t in inventory)
            fragments.append(
                f"[Tools] Available local tools: {tool_list}. "
                f"Use these for deterministic operations before resorting "
                f"to LLM reasoning."
            )

        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=0.3,
            data={"matched_tool": None, "inventory": inventory},
            prompt_fragments=fragments,
        )

    # -- tool execution ------------------------------------------------------

    def _execute_tool(
        self, name: str, args: Dict[str, Any],
    ) -> AgentResult:
        spec = self._registry[name]
        try:
            output = spec.handler(**args)
        except Exception as exc:
            log.warning("Tool %s failed: %s", name, exc)
            return AgentResult(
                agent=self.agent_type.value,
                success=False,
                confidence=0.0,
                errors=[f"Tool '{name}' error: {exc}"],
                data={"matched_tool": name},
            )

        fragments = [
            f"[Tools] Executed '{name}': {_truncate(str(output), 300)}"
        ]

        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=0.9,
            data={"matched_tool": name, "output": output},
            prompt_fragments=fragments,
        )

    # -- detection -----------------------------------------------------------

    # Explicit trigger words for each built-in tool.  Each entry maps a
    # tool name to a set of trigger phrases (whole-word).
    _TOOL_TRIGGERS: Dict[str, List[str]] = {
        "math_eval": [
            "calculate", "compute", "math", "evaluate",
            "what is", "how much is", "solve",
            "plus", "minus", "times", "divided by",
            "multiply", "add", "subtract",
        ],
        "timestamp": [
            "what time", "current time", "right now",
            "date today", "today's date", "utc time",
        ],
        "word_count": [
            "word count", "count words", "how many words",
            "count characters", "how long is",
        ],
    }

    _TOOL_TRIGGER_THRESHOLD: float = 0.5  # minimum confidence to match

    def _detect_tool(self, message: str) -> str:
        """Detect the best matching tool using explicit trigger phrases.

        Returns the tool name with the highest confidence above threshold,
        or empty string if no match.
        """
        if not message:
            return ""

        msg_lower = message.lower()
        msg_words = set(re.split(r"\W+", msg_lower))

        best_name = ""
        best_score = 0.0

        for tool_name, triggers in self._TOOL_TRIGGERS.items():
            if tool_name not in self._registry:
                continue
            # Score: fraction of triggers found in message
            hits = 0
            for phrase in triggers:
                # Check for multi-word phrases as substrings
                if " " in phrase:
                    if phrase in msg_lower:
                        hits += 1
                else:
                    # Single-word: match as whole word
                    if phrase in msg_words:
                        hits += 1
            if hits == 0:
                continue
            score = hits / len(triggers)
            if score > best_score:
                best_score = score
                best_name = tool_name

        if best_score >= self._TOOL_TRIGGER_THRESHOLD:
            return best_name

        # Fallback: check for arithmetic expression patterns
        if re.search(r"\d+\s*[+\-*/]\s*\d+", message):
            if "math_eval" in self._registry:
                return "math_eval"

        return ""

    # -- builtins ------------------------------------------------------------

    def _register_builtins(self) -> None:
        """Register safe, deterministic built-in tools."""
        self.register_tool(ToolSpec(
            name="math_eval",
            description="Evaluate a simple arithmetic expression",
            handler=_builtin_math_eval,
            parameters={"expression": "Arithmetic expression string (e.g. '2+3*4')"},
        ))
        self.register_tool(ToolSpec(
            name="timestamp",
            description="Return the current UTC timestamp",
            handler=_builtin_timestamp,
            parameters={},
        ))
        self.register_tool(ToolSpec(
            name="word_count",
            description="Count words in a text string",
            handler=_builtin_word_count,
            parameters={"text": "The text to count words in"},
        ))


# -- Built-in tool handlers (pure functions) ---------------------------------

def _builtin_math_eval(expression: str = "") -> Dict[str, Any]:
    """Safely evaluate simple arithmetic.  Allows only digits and operators."""
    expr = expression.strip()
    if not expr:
        return {"error": "empty expression"}

    # Whitelist: digits, decimal point, operators, parens, spaces.
    if not re.match(r'^[\d\s+\-*/.()%]+$', expr):
        return {"error": "expression contains disallowed characters", "expression": expr}

    try:
        # Use compile + eval with empty globals for safety.
        code = compile(expr, "<math>", "eval")
        # Disallow names -- pure arithmetic only.
        for name in code.co_names:
            return {"error": f"disallowed name: {name}", "expression": expr}
        result = eval(code, {"__builtins__": {}}, {})  # noqa: S307
        return {"result": result, "expression": expr}
    except Exception as exc:
        return {"error": str(exc), "expression": expr}


def _builtin_timestamp() -> Dict[str, Any]:
    now = time.time()
    return {
        "unix": now,
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }


def _builtin_word_count(text: str = "") -> Dict[str, Any]:
    words = text.split()
    return {"word_count": len(words), "char_count": len(text)}


# ---------------------------------------------------------------------------
# SentimentAgent
# ---------------------------------------------------------------------------

class SentimentAgent(SidekickAgent):
    """Analyzes user sentiment from text, tracks emotional patterns over time,
    and suggests personality adjustments for the sidekick.

    Uses a keyword/heuristic approach (no external NLP).  Tracks a rolling
    window of sentiment scores to detect trends (improving, declining, stable).
    """

    _POSITIVE_WORDS: Tuple[str, ...] = (
        "great", "awesome", "thanks", "perfect", "love", "nice", "amazing",
        "excellent", "helpful", "cool", "fantastic", "brilliant", "wonderful",
        "happy", "glad", "appreciate", "impressed", "excited", "good",
    )
    _NEGATIVE_WORDS: Tuple[str, ...] = (
        "bad", "wrong", "terrible", "hate", "annoyed", "frustrated",
        "confused", "broken", "useless", "stupid", "awful", "horrible",
        "angry", "disappointed", "upset", "sucks", "fail", "worse",
    )
    _INTENSIFIERS: Tuple[str, ...] = (
        "very", "really", "extremely", "so", "incredibly", "absolutely",
        "totally", "completely",
    )
    _NEGATORS: Tuple[str, ...] = (
        "not", "no", "never", "don't", "doesn't", "didn't", "isn't",
        "aren't", "wasn't", "weren't", "won't", "can't", "couldn't",
    )

    _MAX_HISTORY = 50

    def __init__(self) -> None:
        super().__init__(AgentType.SENTIMENT)
        self._history: List[Dict[str, Any]] = []

    def process(self, context: Dict[str, Any]) -> AgentResult:
        user_message: str = context.get("user_message", "")

        score = self._score_text(user_message)
        label = self._label_from_score(score)
        trend = self._compute_trend()

        # Record for pattern tracking.
        self._history.append({
            "score": score,
            "label": label.value,
            "ts": time.time(),
        })
        if len(self._history) > self._MAX_HISTORY:
            self._history = self._history[-self._MAX_HISTORY:]

        personality_hint = self._suggest_personality(label, trend)

        fragments: List[str] = []
        if label in (SentimentLabel.NEGATIVE, SentimentLabel.VERY_NEGATIVE):
            fragments.append(
                f"[Sentiment] User sentiment is {label.value} (score={score:.2f}). "
                f"Trend: {trend}. {personality_hint}"
            )
        elif label == SentimentLabel.VERY_POSITIVE:
            fragments.append(
                f"[Sentiment] User sentiment is very positive. Match their energy."
            )

        confidence = min(1.0, 0.5 + abs(score) * 0.5)

        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=confidence,
            data={
                "score": round(score, 3),
                "label": label.value,
                "trend": trend,
                "personality_hint": personality_hint,
                "history_length": len(self._history),
            },
            prompt_fragments=fragments,
        )

    # -- scoring -------------------------------------------------------------

    def _score_text(self, text: str) -> float:
        """Score text on a -1.0 to +1.0 scale."""
        words = text.lower().split()
        if not words:
            return 0.0

        score = 0.0
        negate = False

        for i, word in enumerate(words):
            # Clean punctuation at word boundaries.
            clean = re.sub(r'[^\w]', '', word)
            if not clean:
                continue

            if clean in self._NEGATORS:
                negate = True
                continue

            multiplier = 1.0
            if i > 0:
                prev = re.sub(r'[^\w]', '', words[i - 1])
                if prev in self._INTENSIFIERS:
                    multiplier = 1.5

            if clean in self._POSITIVE_WORDS:
                delta = 0.15 * multiplier
                score += -delta if negate else delta
                negate = False
            elif clean in self._NEGATIVE_WORDS:
                delta = 0.15 * multiplier
                score += delta if negate else -delta
                negate = False
            else:
                # Non-sentiment word: reset negation after one skip.
                if negate:
                    negate = False

        # Normalize.
        return max(-1.0, min(1.0, score))

    @staticmethod
    def _label_from_score(score: float) -> SentimentLabel:
        if score >= 0.4:
            return SentimentLabel.VERY_POSITIVE
        if score >= 0.1:
            return SentimentLabel.POSITIVE
        if score <= -0.4:
            return SentimentLabel.VERY_NEGATIVE
        if score <= -0.1:
            return SentimentLabel.NEGATIVE
        return SentimentLabel.NEUTRAL

    def _compute_trend(self) -> str:
        """Compute sentiment trend from recent history."""
        if len(self._history) < 3:
            return "insufficient_data"

        recent = [h["score"] for h in self._history[-5:]]
        older = [h["score"] for h in self._history[-10:-5]] if len(self._history) >= 10 else []

        if not older:
            return "establishing"

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        delta = recent_avg - older_avg

        if delta > 0.15:
            return "improving"
        if delta < -0.15:
            return "declining"
        return "stable"

    def _suggest_personality(self, label: SentimentLabel, trend: str) -> str:
        if label == SentimentLabel.VERY_NEGATIVE:
            return (
                "Shift to empathetic mode: acknowledge frustration, "
                "lower complexity, offer clear next step."
            )
        if label == SentimentLabel.NEGATIVE:
            if trend == "declining":
                return (
                    "Sentiment declining -- check if current approach is "
                    "working; consider changing strategy."
                )
            return "Be supportive and patient. Confirm understanding before acting."
        if label == SentimentLabel.VERY_POSITIVE:
            return "User is energized -- match enthusiasm, suggest stretch goals."
        if trend == "improving":
            return "Momentum is building -- keep current approach."
        return ""


# ---------------------------------------------------------------------------
# BrowserAgent
# ---------------------------------------------------------------------------

class BrowserAgent(SidekickAgent):
    """Handles web browsing, searching, and content extraction.

    Detects when the user needs live web data and dispatches to the
    ``lib.sidekick.web_browser`` module.  Returns structured results
    as prompt fragments for the LLM to incorporate.
    """

    # Trigger phrases that indicate the user wants web access.
    _WEB_TRIGGERS: tuple = (
        "search the web", "search online", "search for", "google",
        "look up", "look online", "find online", "browse", "web search",
        "what's new", "latest news", "current price", "today's",
        "right now", "real-time", "realtime", "live data",
        "on the internet", "on the web", "website", "webpage",
        "go to http", "go to www", "open http", "open www",
        "visit http", "visit www", "check http", "check www",
        "navigate to", "pull up", "show me",
    )

    # URL pattern for direct URL requests.
    _URL_RE = re.compile(
        r"https?://[^\s<>\"']+|www\.[^\s<>\"']+",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(AgentType.BROWSER)
        self._browser = None  # Lazy import

    def _get_browser(self):
        """Lazy-load the web browser module."""
        if self._browser is None:
            try:
                from lib.sidekick.web_browser import get_web_browser
                self._browser = get_web_browser()
            except ImportError:
                pass
        return self._browser

    def process(self, context: Dict[str, Any]) -> AgentResult:
        user_message: str = context.get("user_message", "")
        explicit_action: str = context.get("browser_action", "")  # search/browse/extract/task
        url: str = context.get("url", "")
        query: str = context.get("query", "")

        # Detect if web access is needed.
        needs_web = bool(explicit_action)
        detected_url = ""

        if not needs_web:
            msg_lower = user_message.lower()
            for trigger in self._WEB_TRIGGERS:
                if trigger in msg_lower:
                    needs_web = True
                    break

        if not needs_web:
            url_match = self._URL_RE.search(user_message)
            if url_match:
                needs_web = True
                detected_url = url_match.group(0)

        if not needs_web:
            return AgentResult(
                agent=self.agent_type.value,
                success=True,
                confidence=0.1,
                data={"web_needed": False},
            )

        # Web access is needed -- try to execute.
        browser = self._get_browser()
        if browser is None:
            return AgentResult(
                agent=self.agent_type.value,
                success=False,
                confidence=0.0,
                errors=["browser-use not installed (pip install 'browser-use>=0.11.0')"],
                data={"web_needed": True},
            )

        if not browser.available:
            return AgentResult(
                agent=self.agent_type.value,
                success=False,
                confidence=0.0,
                errors=[browser.init_error or "Browser not available"],
                data={"web_needed": True},
            )

        # Dispatch based on action type.
        try:
            target_url = url or detected_url
            if explicit_action == "browse" and target_url:
                result = browser.browse_url(target_url, instruction=query)
            elif explicit_action == "extract" and target_url:
                result = browser.extract_content(target_url, query or user_message)
            elif explicit_action == "search" or (not target_url and not explicit_action):
                search_query = query or user_message
                result = browser.search(search_query)
            elif target_url:
                result = browser.browse_url(target_url, instruction=user_message)
            else:
                result = browser.run_task(user_message)
        except Exception as exc:
            return AgentResult(
                agent=self.agent_type.value,
                success=False,
                confidence=0.0,
                errors=[f"Browser error: {type(exc).__name__}: {exc}"],
                data={"web_needed": True},
            )

        if not result.success:
            return AgentResult(
                agent=self.agent_type.value,
                success=False,
                confidence=0.3,
                errors=[result.error or "Unknown browser error"],
                data={"web_needed": True, "browse_result": result.to_dict()},
            )

        # Build prompt fragments from results.
        fragments = [
            f"[Web] {result.for_llm_context()}"
        ]

        return AgentResult(
            agent=self.agent_type.value,
            success=True,
            confidence=0.9,
            data={
                "web_needed": True,
                "browse_result": result.to_dict(),
                "url": result.url,
                "content_length": len(result.content),
            },
            prompt_fragments=fragments,
        )

    def detect_web_intent(self, message: str) -> bool:
        """Public check: does the message need web access?"""
        msg_lower = message.lower()
        for trigger in self._WEB_TRIGGERS:
            if trigger in msg_lower:
                return True
        if self._URL_RE.search(message):
            return True
        return False


# ---------------------------------------------------------------------------
# ClaudeCodeAgent
# ---------------------------------------------------------------------------

class ClaudeCodeAgent(SidekickAgent):
    """Detects build/create/research/code intents and delegates to ClaudeCodeOps.

    Analyzes user messages for code generation, project building, or
    research intents and produces structured prompts or directly invokes
    the ``claude`` CLI when available.
    """

    _CODE_TRIGGERS: tuple = (
        "build", "create", "generate", "scaffold", "write code",
        "make a", "code a", "implement", "develop",
        "set up", "setup", "bootstrap",
    )
    _RESEARCH_TRIGGERS: tuple = (
        "research", "look into", "investigate", "deep dive",
        "analyze", "study", "explore the topic",
    )

    def __init__(self) -> None:
        super().__init__(AgentType.CLAUDE_CODE)
        self._ops = None  # lazy import

    def _get_ops(self):
        if self._ops is None:
            try:
                from lib.sidekick.claude_code_ops import ClaudeCodeOps
                self._ops = ClaudeCodeOps()
            except ImportError:
                pass
        return self._ops

    def process(self, context: Dict[str, Any]) -> AgentResult:
        user_message: str = context.get("user_message", "")
        explicit_action: str = context.get("claude_code_action", "")

        intent = self._detect_intent(user_message) if not explicit_action else explicit_action
        if not intent:
            return AgentResult(
                agent=self.agent_type.value,
                success=True,
                confidence=0.1,
                data={"intent_detected": False},
            )

        ops = self._get_ops()
        if ops is None or not ops.is_available():
            fragments = [
                f"[ClaudeCode] Detected {intent} intent but claude CLI not available. "
                f"Install with: npm install -g @anthropic-ai/claude-code"
            ]
            return AgentResult(
                agent=self.agent_type.value,
                success=True,
                confidence=0.5,
                data={"intent_detected": True, "intent": intent, "available": False},
                prompt_fragments=fragments,
            )

        # Execute via Claude CLI
        if intent == "research":
            result = ops.research(user_message)
        elif intent == "build":
            result = ops.generate_code(user_message)
        else:
            result = ops.execute(user_message)

        fragments = []
        if result.success:
            fragments.append(
                f"[ClaudeCode] Executed ({intent}): {_truncate(result.output, 500)}"
            )
        else:
            fragments.append(
                f"[ClaudeCode] Failed ({intent}): {result.error}"
            )

        return AgentResult(
            agent=self.agent_type.value,
            success=result.success,
            confidence=0.85 if result.success else 0.3,
            data={
                "intent_detected": True,
                "intent": intent,
                "available": True,
                "result": result.to_dict(),
            },
            prompt_fragments=fragments,
        )

    def _detect_intent(self, message: str) -> str:
        msg_lower = message.lower()
        for trigger in self._CODE_TRIGGERS:
            if trigger in msg_lower:
                return "build"
        for trigger in self._RESEARCH_TRIGGERS:
            if trigger in msg_lower:
                return "research"
        return ""

    def detect_code_intent(self, message: str) -> bool:
        """Public check: does the message need Claude Code?"""
        return bool(self._detect_intent(message))


# ---------------------------------------------------------------------------
# AgentOrchestrator
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    """Central dispatcher that routes tasks to sidekick agents.

    Usage::

        orch = AgentOrchestrator()
        result = orch.dispatch("reflection", context)
        multi  = orch.dispatch_multi(["reflection", "sentiment"], context)
        stats  = orch.get_agent_stats()
    """

    # Map task_type strings to AgentType enum for flexible dispatch.
    _ALIASES: Dict[str, AgentType] = {
        "reflection": AgentType.REFLECTION,
        "reflect": AgentType.REFLECTION,
        "creativity": AgentType.CREATIVITY,
        "creative": AgentType.CREATIVITY,
        "kait": AgentType.CREATIVITY,
        "logic": AgentType.LOGIC,
        "reason": AgentType.LOGIC,
        "math": AgentType.LOGIC,
        "tool": AgentType.TOOL,
        "tools": AgentType.TOOL,
        "sentiment": AgentType.SENTIMENT,
        "emotion": AgentType.SENTIMENT,
        "mood": AgentType.SENTIMENT,
        "browser": AgentType.BROWSER,
        "browse": AgentType.BROWSER,
        "web": AgentType.BROWSER,
        "search": AgentType.BROWSER,
        "internet": AgentType.BROWSER,
        "claude_code": AgentType.CLAUDE_CODE,
        "claude-code": AgentType.CLAUDE_CODE,
        "code": AgentType.CLAUDE_CODE,
        "build": AgentType.CLAUDE_CODE,
        "generate": AgentType.CLAUDE_CODE,
    }

    def __init__(self) -> None:
        self._agents: Dict[AgentType, SidekickAgent] = {
            AgentType.REFLECTION: ReflectionAgent(),
            AgentType.CREATIVITY: CreativityAgent(),
            AgentType.LOGIC: LogicAgent(),
            AgentType.TOOL: ToolAgent(),
            AgentType.SENTIMENT: SentimentAgent(),
            AgentType.BROWSER: BrowserAgent(),
            AgentType.CLAUDE_CODE: ClaudeCodeAgent(),
        }

    def get_agent(self, agent_type: AgentType) -> SidekickAgent:
        """Return the agent instance for a given type."""
        return self._agents[agent_type]

    # -- dispatch ------------------------------------------------------------

    def dispatch(self, task_type: str, context: Dict[str, Any]) -> AgentResult:
        """Route a single task to the appropriate agent.

        Args:
            task_type: Agent name or alias (e.g. ``"reflection"``, ``"math"``).
            context: Arbitrary dict forwarded to the agent's ``process()``.

        Returns:
            ``AgentResult`` from the matched agent, or an error result if
            no agent matches.
        """
        agent_type = self._resolve(task_type)
        if agent_type is None:
            return AgentResult(
                agent="orchestrator",
                success=False,
                confidence=0.0,
                errors=[f"Unknown task type: '{task_type}'"],
            )
        return self._agents[agent_type].run(context)

    def dispatch_multi(
        self,
        task_types: List[str],
        context: Dict[str, Any],
    ) -> Dict[str, AgentResult]:
        """Run multiple agents and collect their results.

        Args:
            task_types: List of agent names/aliases.
            context: Shared context forwarded to every agent.

        Returns:
            Dict mapping each resolved agent name to its ``AgentResult``.
            Unknown task types are included with error results.
        """
        results: Dict[str, AgentResult] = {}
        for tt in task_types:
            agent_type = self._resolve(tt)
            key = agent_type.value if agent_type else tt
            if agent_type is None:
                results[key] = AgentResult(
                    agent="orchestrator",
                    success=False,
                    confidence=0.0,
                    errors=[f"Unknown task type: '{tt}'"],
                )
            else:
                results[key] = self._agents[agent_type].run(context)
        return results

    def merge_prompt_fragments(
        self, results: Dict[str, AgentResult],
    ) -> List[str]:
        """Collect and deduplicate prompt fragments from multiple agent results.

        Returns fragments ordered by agent confidence (highest first).
        """
        pairs: List[Tuple[float, str]] = []
        for result in results.values():
            if not result.success:
                continue
            for frag in result.prompt_fragments:
                pairs.append((result.confidence, frag))

        pairs.sort(key=lambda p: p[0], reverse=True)
        seen: set[str] = set()
        ordered: List[str] = []
        for _, frag in pairs:
            if frag not in seen:
                seen.add(frag)
                ordered.append(frag)
        return ordered

    # -- stats ---------------------------------------------------------------

    def get_agent_stats(self) -> Dict[str, Dict[str, Any]]:
        """Return performance metrics for every registered agent."""
        return {
            agent_type.value: agent.stats
            for agent_type, agent in self._agents.items()
        }

    # -- internals -----------------------------------------------------------

    def _resolve(self, task_type: str) -> Optional[AgentType]:
        """Resolve a task_type string to an AgentType enum."""
        normalized = task_type.strip().lower()

        # Direct enum match.
        try:
            return AgentType(normalized)
        except ValueError:
            pass

        # Alias match.
        return self._ALIASES.get(normalized)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = 200) -> str:
    """Truncate text with ellipsis if it exceeds *max_len*."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
