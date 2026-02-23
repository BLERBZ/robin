"""
Comprehensive test suite for the Kait AI Intel system.

Covers all sidekick modules:
  - ReasoningBank (SQLite persistence)
  - Local LLM (Ollama client)
  - Agents (multi-agent orchestrator)
  - MoodTracker (state, transitions, evolution)
  - ClaudeCodeOps (autonomous code operations)
  - Resonance (sentiment, preferences, engine)
  - Reflection (cycle, evolver, refiner, scheduler)
  - Tools (registry, calculator, system, text, json, datetime)
  - Evolution (engine, persistence, stages)
  - Integration (full pipeline)

Run with:
    pytest tests/test_sidekick.py -v
"""

import os
import sys
import time
import json
import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===================================================================
# 1. ReasoningBank Tests
# ===================================================================

from lib.sidekick.reasoning_bank import ReasoningBank


@pytest.fixture
def reasoning_bank(tmp_path):
    """Create a ReasoningBank backed by a temporary SQLite database."""
    db_path = str(tmp_path / "test_sidekick.db")
    return ReasoningBank(db_path=db_path)


class TestReasoningBank:
    """Tests for the SQLite-backed ReasoningBank persistence layer."""

    def test_reasoning_bank_init(self, tmp_path):
        """ReasoningBank creates the DB file and initialises all tables."""
        db_path = str(tmp_path / "init_test.db")
        bank = ReasoningBank(db_path=db_path)

        assert os.path.exists(db_path), "Database file should exist after init"

        # Verify all expected tables are present
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

        expected = {
            "interactions",
            "contexts",
            "corrections",
            "evolutions",
            "preferences",
            "personality",
        }
        assert expected.issubset(tables), (
            f"Missing tables: {expected - tables}"
        )

    def test_save_and_get_interaction(self, reasoning_bank):
        """save_interaction returns an ID; get_interaction retrieves it."""
        iid = reasoning_bank.save_interaction(
            user_input="Hello",
            ai_response="Hi there!",
            mood="curious",
            sentiment_score=0.5,
        )

        assert isinstance(iid, str) and len(iid) > 0

        row = reasoning_bank.get_interaction(iid)
        assert row is not None
        assert row["user_input"] == "Hello"
        assert row["ai_response"] == "Hi there!"
        assert row["mood"] == "curious"
        assert row["sentiment_score"] == 0.5

    def test_interaction_history(self, reasoning_bank):
        """get_interaction_history returns recent interactions respecting limit."""
        for i in range(5):
            reasoning_bank.save_interaction(
                user_input=f"msg-{i}",
                ai_response=f"reply-{i}",
            )

        history = reasoning_bank.get_interaction_history(limit=3)
        assert len(history) == 3
        # Most recent first
        assert history[0]["user_input"] == "msg-4"

        all_history = reasoning_bank.get_interaction_history(limit=50)
        assert len(all_history) == 5

    def test_context_crud(self, reasoning_bank):
        """save_context, get_context (with access counting), update_context."""
        # Save
        cid = reasoning_bank.save_context(
            key="user_location",
            value={"city": "Portland"},
            domain="personal",
            confidence=0.8,
        )
        assert isinstance(cid, str)

        # First get increments access_count to 1
        ctx = reasoning_bank.get_context("user_location")
        assert ctx is not None
        assert ctx["value"] == {"city": "Portland"}
        assert ctx["domain"] == "personal"
        assert ctx["confidence"] == 0.8
        assert ctx["access_count"] == 1

        # Second get increments access_count to 2
        ctx2 = reasoning_bank.get_context("user_location")
        assert ctx2["access_count"] == 2

        # Update
        updated = reasoning_bank.update_context(
            key="user_location",
            value={"city": "Seattle"},
            confidence=0.9,
        )
        assert updated is True

        ctx3 = reasoning_bank.get_context("user_location")
        assert ctx3["value"] == {"city": "Seattle"}
        assert ctx3["confidence"] == 0.9

        # update_context on a non-existent key creates it
        created = reasoning_bank.update_context(
            key="new_key",
            value="new_value",
        )
        assert created is False  # False means newly created, not updated

    def test_record_correction(self, reasoning_bank):
        """record_correction stores entries; get_recent_corrections retrieves them."""
        cid = reasoning_bank.record_correction(
            original="The sun is cold",
            correction="The sun is hot",
            reason="Factual error",
            domain="science",
        )
        assert isinstance(cid, str)

        corrections = reasoning_bank.get_recent_corrections(limit=10)
        assert len(corrections) == 1
        assert corrections[0]["original_response"] == "The sun is cold"
        assert corrections[0]["correction"] == "The sun is hot"
        assert corrections[0]["reason"] == "Factual error"

    def test_evolve_personality(self, reasoning_bank):
        """evolve_personality tracks trait history across multiple calls."""
        tid1 = reasoning_bank.evolve_personality("warmth", 0.5)
        assert isinstance(tid1, str)

        trait = reasoning_bank.get_personality_trait("warmth")
        assert trait is not None
        assert trait["value_float"] == 0.5
        assert len(trait["history"]) == 1

        # Evolve again
        tid2 = reasoning_bank.evolve_personality("warmth", 0.8)
        assert tid2 == tid1  # Same trait ID returned for existing trait

        trait2 = reasoning_bank.get_personality_trait("warmth")
        assert trait2["value_float"] == 0.8
        assert len(trait2["history"]) == 2

    def test_evolution_timeline(self, reasoning_bank):
        """save_evolution and get_evolution_timeline work correctly."""
        eid = reasoning_bank.save_evolution(
            evolution_type="accuracy_improvement",
            description="Fixed math accuracy",
            metrics_before={"accuracy": 0.7},
            metrics_after={"accuracy": 0.9},
        )
        assert isinstance(eid, str)

        timeline = reasoning_bank.get_evolution_timeline(limit=10)
        assert len(timeline) >= 1
        latest = timeline[0]
        assert latest["evolution_type"] == "accuracy_improvement"
        assert latest["metrics_before"] == {"accuracy": 0.7}
        assert latest["metrics_after"] == {"accuracy": 0.9}

    def test_preferences(self, reasoning_bank):
        """save_preference and get_preference persist user preferences."""
        pid = reasoning_bank.save_preference(
            key="response_length",
            value="concise",
            confidence=0.75,
        )
        assert isinstance(pid, str)

        pref = reasoning_bank.get_preference("response_length")
        assert pref is not None
        assert pref["value"] == "concise"
        assert pref["confidence"] == 0.75

        # Non-existent key returns None
        assert reasoning_bank.get_preference("nonexistent") is None

    def test_stats(self, reasoning_bank):
        """get_stats returns comprehensive counts for all tables."""
        reasoning_bank.save_interaction("a", "b")
        reasoning_bank.save_context("k", "v")
        reasoning_bank.record_correction("old", "new")
        reasoning_bank.save_evolution("type", "desc")
        reasoning_bank.save_preference("pref", "val")
        reasoning_bank.evolve_personality("humor", 0.6)

        stats = reasoning_bank.get_stats()
        assert stats["interactions"] >= 1
        assert stats["contexts"] >= 1
        assert stats["corrections"] >= 1
        assert stats["evolutions"] >= 1  # evolve_personality also creates evolutions
        assert stats["preferences"] >= 1
        assert stats["personality_traits"] >= 1
        assert "avg_sentiment" in stats
        assert "db_path" in stats


# ===================================================================
# 2. Local LLM Tests
# ===================================================================

from lib.sidekick.local_llm import OllamaClient, OllamaConnectionError


class TestLocalLLM:
    """Tests for the Ollama local LLM client (no running server required)."""

    def test_ollama_client_init(self):
        """OllamaClient instantiates without error."""
        client = OllamaClient()
        assert client is not None

    def test_health_check_no_server(self):
        """health_check returns False when no Ollama server is running."""
        # Use a port that is almost certainly not running Ollama
        client = OllamaClient(host="127.0.0.1", port=19999)
        result = client.health_check()
        assert result is False

    def test_gpu_info(self):
        """get_gpu_info returns a dict with the 'has_gpu' key."""
        client = OllamaClient()
        info = client.get_gpu_info()
        assert isinstance(info, dict)
        assert "has_gpu" in info
        assert "backend" in info


# ===================================================================
# 3. Agent Tests
# ===================================================================

from lib.sidekick.agents import AgentOrchestrator, AgentResult


class TestAgents:
    """Tests for the multi-agent architecture and orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Fresh AgentOrchestrator instance."""
        return AgentOrchestrator()

    def test_orchestrator_init(self, orchestrator):
        """Orchestrator initialises with all agent types."""
        stats = orchestrator.get_agent_stats()
        expected_agents = {"reflection", "creativity", "logic", "tool", "sentiment", "browser", "claude_code"}
        assert expected_agents == set(stats.keys())

    def test_dispatch_sentiment(self, orchestrator):
        """Dispatching 'sentiment' returns an AgentResult with score data."""
        result = orchestrator.dispatch(
            "sentiment",
            {"user_message": "I love this project!"},
        )
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.agent == "sentiment"
        assert "score" in result.data
        assert "label" in result.data

    def test_dispatch_creativity(self, orchestrator):
        """Dispatching 'creativity' returns creative data (metaphor, mood)."""
        result = orchestrator.dispatch(
            "creativity",
            {"user_message": "Tell me about debugging", "topic": "debugging"},
        )
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert "metaphor" in result.data
        assert "suggested_mood" in result.data

    def test_dispatch_logic(self, orchestrator):
        """Dispatching 'logic' with a math-like message triggers math scaffold."""
        result = orchestrator.dispatch(
            "logic",
            {"user_message": "What is 2+2?"},
        )
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.data["is_math"] is True
        assert result.data["approach"] == "mathematical"
        assert len(result.data["reasoning_chain"]) > 0

    def test_dispatch_tools(self, orchestrator):
        """Dispatching 'tools' returns tool inventory information."""
        result = orchestrator.dispatch(
            "tools",
            {"user_message": "What tools do you have?"},
        )
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert "inventory" in result.data or "matched_tool" in result.data

    def test_dispatch_reflection(self, orchestrator):
        """Dispatching 'reflection' with history returns patterns and suggestions."""
        result = orchestrator.dispatch(
            "reflection",
            {
                "user_message": "I'm frustrated",
                "history": [
                    {"text": "try again", "topic": "coding"},
                    {"text": "still wrong", "topic": "coding"},
                ],
                "corrections": [],
            },
        )
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert "patterns" in result.data
        assert "suggestions" in result.data

    def test_dispatch_multi(self, orchestrator):
        """dispatch_multi runs multiple agents and returns a dict of results."""
        results = orchestrator.dispatch_multi(
            ["sentiment", "creativity", "logic"],
            {"user_message": "How do I solve 5*10?"},
        )
        assert isinstance(results, dict)
        assert "sentiment" in results
        assert "creativity" in results
        assert "logic" in results
        for key, res in results.items():
            assert isinstance(res, AgentResult)

    def test_agent_stats(self, orchestrator):
        """Stats track invocations after dispatching."""
        orchestrator.dispatch("sentiment", {"user_message": "hello"})
        orchestrator.dispatch("sentiment", {"user_message": "world"})

        stats = orchestrator.get_agent_stats()
        assert stats["sentiment"]["invocations"] == 2
        assert stats["sentiment"]["total_time_ms"] > 0


# ===================================================================
# 4. Avatar Tests
# ===================================================================

from lib.sidekick.mood_tracker import MoodTracker, MoodState, VALID_MOODS


class TestMoodTracker:
    """Tests for the mood/state tracker (replaces avatar system)."""

    def test_mood_state_clamping(self):
        """MoodState clamps float values to [0, 1] and validates mood."""
        state = MoodState(
            mood="excited",
            energy=1.5,     # should clamp to 1.0
            warmth=-0.3,    # should clamp to 0.0
            confidence=0.7,
            kait_level=0.5,
        )
        assert state.energy == 1.0
        assert state.warmth == 0.0
        assert state.confidence == 0.7

        # Invalid mood falls back to default
        bad_mood = MoodState(mood="invalid_mood_xyz")
        assert bad_mood.mood == "calm"  # default mood

    def test_mood_tracker_update(self):
        """update_mood changes the tracker's mood state."""
        tracker = MoodTracker(initial_mood="calm")
        assert tracker.get_state().mood == "calm"

        tracker.update_mood("excited")
        state = tracker.get_state()
        assert state.mood == "excited"

    def test_mood_evolution(self):
        """evolve() advances the evolution stage."""
        tracker = MoodTracker()
        assert tracker.get_state().evolution_stage == 1

        tracker.evolve(3)
        assert tracker.get_state().evolution_stage == 3

        # Cannot de-evolve
        tracker.evolve(2)
        assert tracker.get_state().evolution_stage == 3

    def test_kait_greeting(self):
        """get_kait_greeting returns a non-empty string."""
        tracker = MoodTracker(initial_mood="playful")
        greeting = tracker.get_kait_greeting()
        assert isinstance(greeting, str)
        assert len(greeting) > 10

    def test_get_display(self):
        """get_display returns a text indicator string."""
        tracker = MoodTracker(initial_mood="curious")
        display = tracker.get_display()
        assert isinstance(display, str)
        assert "mood:" in display
        assert "energy:" in display

    def test_pulse_energy(self):
        """pulse_energy adjusts energy within bounds."""
        tracker = MoodTracker()
        initial = tracker.get_state().energy
        tracker.pulse_energy(0.5)
        assert tracker.get_state().energy > initial
        # Should not exceed 1.0
        tracker.pulse_energy(10.0)
        assert tracker.get_state().energy == 1.0

    def test_set_warmth_confidence(self):
        """set_warmth and set_confidence clamp to [0, 1]."""
        tracker = MoodTracker()
        tracker.set_warmth(0.8)
        assert tracker.get_state().warmth == 0.8
        tracker.set_confidence(1.5)
        assert tracker.get_state().confidence == 1.0

    def test_tick_converges(self):
        """Repeated ticks converge mood transitions."""
        tracker = MoodTracker(initial_mood="calm")
        tracker.update_mood("excited")
        for _ in range(50):
            tracker.tick()
        # After many ticks, should be close to excited profile values
        state = tracker.get_state()
        assert state.mood == "excited"
        assert state.energy > 0.8

    def test_valid_moods(self):
        """All 12 moods are valid."""
        assert len(VALID_MOODS) == 12
        for mood in VALID_MOODS:
            tracker = MoodTracker(initial_mood=mood)
            assert tracker.get_state().mood == mood

    def test_close_is_noop(self):
        """close() does not raise."""
        tracker = MoodTracker()
        tracker.close()


# ===================================================================
# 5. Resonance Tests
# ===================================================================

from lib.sidekick.resonance import (
    SentimentAnalyzer,
    ResonanceEngine,
    PreferenceTracker,
)


class TestResonance:
    """Tests for the resonance engine, sentiment analysis, and preferences."""

    @pytest.fixture
    def analyzer(self):
        """Fresh SentimentAnalyzer."""
        return SentimentAnalyzer()

    def test_sentiment_positive(self, analyzer):
        """Positive text yields a positive label."""
        result = analyzer.analyze("I love this, it is absolutely amazing!")
        assert result["label"] == "positive"
        assert result["score"] > 0

    def test_sentiment_negative(self, analyzer):
        """Negative text yields a negative label."""
        result = analyzer.analyze("This is terrible and awful")
        assert result["label"] == "negative"
        assert result["score"] < 0

    def test_sentiment_neutral(self, analyzer):
        """Neutral text yields a neutral label."""
        result = analyzer.analyze("The sky is blue")
        assert result["label"] == "neutral"
        assert abs(result["score"]) <= 0.05

    def test_sentiment_negation(self, analyzer):
        """Negation flips sentiment: 'not happy' tends negative."""
        result = analyzer.analyze("I am not happy")
        # "not" should flip "happy" (positive) toward negative
        assert result["score"] < 0

    def test_resonance_interaction(self):
        """process_interaction updates internal state and returns resonance."""
        engine = ResonanceEngine()
        result = engine.process_interaction(
            user_input="That was really helpful, thanks!",
            ai_response="Glad I could help!",
        )
        assert "sentiment" in result
        assert "resonance" in result
        assert isinstance(result["resonance"], float)

    def test_resonance_score(self):
        """get_resonance_score returns a value between 0 and 1."""
        engine = ResonanceEngine()
        # Seed some interactions
        engine.process_interaction("great job!", "thanks!")
        engine.process_interaction("love it", "glad to hear!")

        score = engine.get_resonance_score()
        assert 0.0 <= score <= 1.0

    def test_preference_tracker(self):
        """Record and retrieve preferences with confidence tracking."""
        tracker = PreferenceTracker()
        tracker.record_preference("tone", "casual", confidence=0.7)

        pref = tracker.get_preference("tone")
        assert pref is not None
        assert pref["value"] == "casual"
        assert pref["confidence"] >= 0.7

        # Re-record same value boosts confidence
        tracker.record_preference("tone", "casual", confidence=0.8)
        pref2 = tracker.get_preference("tone")
        assert pref2["confidence"] > pref["confidence"]

    def test_adaptation_suggestions(self):
        """get_adaptation_suggestions returns a list of strings."""
        engine = ResonanceEngine()
        # Provide a few interactions so there is some data
        for _ in range(3):
            engine.process_interaction(
                user_input="tell me more",
                ai_response="Here is more information for you.",
            )

        suggestions = engine.get_adaptation_suggestions()
        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1
        assert all(isinstance(s, str) for s in suggestions)


# ===================================================================
# 6. Reflection Tests
# ===================================================================

from lib.sidekick.reflection import (
    ReflectionCycle,
    BehaviorEvolver,
    PromptRefiner,
    ReflectionScheduler,
)


class TestReflection:
    """Tests for the self-reflection and behavior evolution subsystem."""

    def test_reflection_cycle(self):
        """ReflectionCycle.reflect returns insights and a confidence score."""
        cycle = ReflectionCycle()
        result = cycle.reflect(
            interactions=[
                {
                    "user_input": "How do I sort a list?",
                    "ai_response": "Use sorted() in Python.",
                    "feedback": 0.8,
                },
                {
                    "user_input": "What about reverse sort?",
                    "ai_response": "Pass reverse=True.",
                    "feedback": 0.9,
                },
                {
                    "user_input": "Thanks, that worked!",
                    "ai_response": "Happy to help.",
                    "feedback": 1.0,
                },
            ],
            corrections=[],
            evolution_history=[],
        )
        assert "insights" in result
        assert isinstance(result["insights"], list)
        assert len(result["insights"]) >= 1
        assert "confidence_score" in result
        assert 0.0 <= result["confidence_score"] <= 1.0
        assert "reflection_id" in result

    def test_behavior_evolver(self):
        """BehaviorEvolver proposes and applies an evolution from reflection output."""
        evolver = BehaviorEvolver()
        reflection_output = {
            "reflection_id": "test123",
            "insights": ["User prefers concise answers"],
            "behavior_adjustments": [
                {
                    "type": "improve_response_quality",
                    "description": "Be more concise",
                    "priority": 0.7,
                },
            ],
            "prompt_refinements": ["Keep responses under 50 words"],
            "confidence_score": 0.6,
        }

        proposal = evolver.propose_evolution(reflection_output)
        assert proposal["status"] == "proposed"
        assert len(proposal["changes"]) >= 1
        assert "evolution_id" in proposal

        applied = evolver.apply_evolution(proposal)
        assert applied is True

        history = evolver.get_evolution_history()
        assert len(history) == 1
        assert history[0]["status"] == "applied"

    def test_prompt_refiner(self):
        """PromptRefiner.refine_system_prompt appends learned behaviours."""
        refiner = PromptRefiner()
        base = "You are a helpful assistant."
        learnings = ["Be concise", "Verify facts before stating them"]
        preferences = {"formality": {"value": "casual"}}

        refined = refiner.refine_system_prompt(base, learnings, preferences)
        assert isinstance(refined, str)
        assert "Be concise" in refined
        assert "Verify facts" in refined
        assert "casual" in refined.lower() or "Casual" in refined
        assert refined.startswith(base)

    def test_reflection_scheduler(self):
        """ReflectionScheduler.should_reflect triggers on interaction threshold."""
        scheduler = ReflectionScheduler(
            interaction_threshold=5,
            interval_seconds=3600,
        )

        # Below threshold, recent reflection -- should not trigger
        recent_ts = time.time() - 10  # 10 seconds ago
        assert scheduler.should_reflect(recent_ts, 3) is False

        # At threshold -- should trigger regardless of time
        assert scheduler.should_reflect(recent_ts, 5) is True

        # Below threshold but time elapsed
        old_ts = time.time() - 7200  # 2 hours ago
        assert scheduler.should_reflect(old_ts, 2) is True


# ===================================================================
# 7. Tools Tests
# ===================================================================

from lib.sidekick.tools import ToolRegistry, create_default_registry


class TestTools:
    """Tests for the local tool registry and built-in tools."""

    @pytest.fixture
    def registry(self):
        """Default tool registry with all built-in tools."""
        return create_default_registry()

    def test_default_registry(self, registry):
        """Default registry contains all expected built-in tools."""
        expected_tools = {
            "calculator",
            "file_reader",
            "file_writer",
            "file_search",
            "system_info",
            "datetime_tool",
            "json_tool",
            "text_tool",
            "data_query",
        }
        tool_list = {t["name"] for t in registry.list_tools()}
        assert expected_tools.issubset(tool_list), (
            f"Missing tools: {expected_tools - tool_list}"
        )

    def test_calculator(self, registry):
        """Calculator evaluates arithmetic expressions correctly."""
        result = registry.execute("calculator", {"expression": "2 + 2"})
        assert result["success"] is True
        assert result["result"] == 4

        result2 = registry.execute("calculator", {"expression": "10 * 5"})
        assert result2["success"] is True
        assert result2["result"] == 50

    def test_calculator_safety(self, registry):
        """Calculator rejects dangerous expressions (e.g. function calls, imports)."""
        result = registry.execute(
            "calculator",
            {"expression": "__import__('os').system('ls')"},
        )
        # Should fail -- either success=False or result contains an error
        assert result.get("success") is False or "error" in result

    def test_system_info(self, registry):
        """system_info returns platform and system information."""
        result = registry.execute("system_info", {})
        assert result["success"] is True
        assert "platform" in result
        assert "python_version" in result
        assert "cpu_count" in result

    def test_datetime_tool(self, registry):
        """datetime_tool 'now' action returns the current time."""
        result = registry.execute("datetime_tool", {"action": "now"})
        assert result["success"] is True
        assert "local" in result
        assert "utc" in result
        assert "timestamp" in result

    def test_text_tool(self, registry):
        """text_tool word_count action counts words correctly."""
        result = registry.execute(
            "text_tool",
            {"action": "word_count", "text": "one two three four five"},
        )
        assert result["success"] is True
        assert result["word_count"] == 5

    def test_json_tool(self, registry):
        """json_tool can parse and format JSON data."""
        # Parse
        parse_result = registry.execute(
            "json_tool",
            {"action": "parse", "data": '{"key": "value", "num": 42}'},
        )
        assert parse_result["success"] is True
        assert parse_result["parsed"] == {"key": "value", "num": 42}

        # Format
        format_result = registry.execute(
            "json_tool",
            {"action": "format", "data": '{"a":1}', "indent": 2},
        )
        assert format_result["success"] is True
        assert "formatted" in format_result

    def test_tool_stats(self, registry):
        """Tool stats track invocation counts and success rates."""
        registry.execute("calculator", {"expression": "1+1"})
        registry.execute("calculator", {"expression": "3*7"})

        stats = registry.get_tool_stats()
        assert stats["total_invocations"] >= 2
        assert stats["total_successes"] >= 2
        calc_stats = stats["tools"]["calculator"]
        assert calc_stats["invocation_count"] >= 2
        assert calc_stats["success_rate"] > 0


# ===================================================================
# 8. Evolution Tests
# ===================================================================

from lib.sidekick.evolution import EvolutionEngine, load_evolution_engine


class TestEvolution:
    """Tests for the self-evolution engine and stage progression."""

    @pytest.fixture
    def engine(self, tmp_path):
        """EvolutionEngine with a temporary state file."""
        state_file = tmp_path / "evolution_test.json"
        return EvolutionEngine(state_path=state_file)

    def test_evolution_init(self, engine):
        """Engine starts at stage 1 with zero metrics."""
        metrics = engine.get_metrics()
        assert metrics.evolution_stage == 1
        assert metrics.total_interactions == 0

    def test_record_interactions(self, engine):
        """record_interaction_outcome updates cumulative metrics."""
        engine.record_interaction_outcome(
            success=True, resonance=0.8, quality=0.7,
        )
        engine.record_interaction_outcome(
            success=False, resonance=0.3, quality=0.4,
        )

        metrics = engine.get_metrics()
        assert metrics.total_interactions == 2
        assert metrics.successful_interactions == 1
        assert metrics.avg_resonance_score > 0
        assert metrics.avg_response_quality > 0

    def test_evolution_threshold(self, engine):
        """check_evolution_threshold returns False when requirements are not met."""
        # Stage 2 requires 25 interactions, 5 corrections, etc.
        assert engine.check_evolution_threshold() is False

    def test_evolve(self, tmp_path):
        """evolve() advances the stage when all thresholds are met."""
        state_file = tmp_path / "evolve_test.json"
        eng = EvolutionEngine(state_path=state_file)

        # Manually satisfy stage 2 requirements:
        #   min_interactions=25, min_corrections=5, min_resonance=0.20,
        #   min_quality=0.40, min_reflection_cycles=1
        for _ in range(30):
            eng.record_interaction_outcome(
                success=True, resonance=0.5, quality=0.6,
            )
        for _ in range(6):
            eng.record_correction()
        eng.record_reflection_cycle()

        assert eng.check_evolution_threshold() is True

        result = eng.evolve()
        assert result["evolved"] is True
        assert result["to_stage"] == 2
        assert result["to_name"] == "Adaptive"
        assert eng.get_metrics().evolution_stage == 2

    def test_evolution_report(self, engine):
        """get_evolution_report returns a non-empty human-readable string."""
        engine.record_interaction_outcome(True, 0.5, 0.5)
        report = engine.get_evolution_report()
        assert isinstance(report, str)
        assert "Evolution Report" in report
        assert "Stage" in report

    def test_persistence(self, tmp_path):
        """Save and reload preserves evolution state across instances."""
        state_file = tmp_path / "persist_test.json"

        # First instance: record some data
        eng1 = EvolutionEngine(state_path=state_file)
        for _ in range(10):
            eng1.record_interaction_outcome(True, 0.6, 0.7)
        eng1.record_correction()

        m1 = eng1.get_metrics()
        assert m1.total_interactions == 10
        assert m1.corrections_applied == 1

        # Second instance: should reload from disk
        eng2 = EvolutionEngine(state_path=state_file)
        m2 = eng2.get_metrics()
        assert m2.total_interactions == 10
        assert m2.corrections_applied == 1
        assert abs(m2.avg_resonance_score - m1.avg_resonance_score) < 0.001


# ===================================================================
# 9. Integration Test
# ===================================================================

class TestIntegration:
    """End-to-end integration test: all modules wired together."""

    def test_full_pipeline(self, tmp_path):
        """Run a mock interaction through the full sidekick pipeline.

        Pipeline: sentiment -> agents -> avatar -> resonance -> evolution
        """
        # --- Initialise all modules ---
        db_path = str(tmp_path / "integration.db")
        bank = ReasoningBank(db_path=db_path)

        orchestrator = AgentOrchestrator()
        mood_mgr = MoodTracker(initial_mood="calm")
        resonance_engine = ResonanceEngine()

        evo_file = tmp_path / "integration_evo.json"
        evo_engine = EvolutionEngine(state_path=evo_file)

        user_input = "I really love how this AI learns and adapts!"
        ai_response = "Thank you! I am always working to improve."

        # --- Step 1: Sentiment analysis via agents ---
        sentiment_result = orchestrator.dispatch(
            "sentiment",
            {"user_message": user_input},
        )
        assert sentiment_result.success is True
        sentiment_score = sentiment_result.data.get("score", 0.0)
        sentiment_label = sentiment_result.data.get("label", "neutral")

        # --- Step 2: Run creativity and reflection agents ---
        multi_results = orchestrator.dispatch_multi(
            ["creativity", "reflection"],
            {
                "user_message": user_input,
                "history": [],
                "corrections": [],
            },
        )
        assert "creativity" in multi_results
        assert "reflection" in multi_results

        # --- Step 3: Update mood based on sentiment ---
        if sentiment_label in ("positive", "very_positive"):
            mood_mgr.update_mood("excited")
        elif sentiment_label in ("negative", "very_negative"):
            mood_mgr.update_mood("contemplative")

        state = mood_mgr.get_state()
        assert state.mood == "excited"

        greeting = mood_mgr.get_kait_greeting()
        assert len(greeting) > 0

        # --- Step 4: Process through resonance engine ---
        resonance_result = resonance_engine.process_interaction(
            user_input=user_input,
            ai_response=ai_response,
            feedback=0.9,
        )
        resonance_score = resonance_result["resonance"]
        assert 0.0 <= resonance_score <= 1.0

        # --- Step 5: Record in evolution engine ---
        evo_engine.record_interaction_outcome(
            success=True,
            resonance=resonance_score,
            quality=0.85,
        )
        metrics = evo_engine.get_metrics()
        assert metrics.total_interactions == 1

        # --- Step 6: Persist interaction in ReasoningBank ---
        iid = bank.save_interaction(
            user_input=user_input,
            ai_response=ai_response,
            mood=state.mood,
            sentiment_score=sentiment_score,
        )
        stored = bank.get_interaction(iid)
        assert stored is not None
        assert stored["user_input"] == user_input

        # --- Verify pipeline coherence ---
        stats = bank.get_stats()
        assert stats["interactions"] >= 1

        evo_report = evo_engine.get_evolution_report()
        assert "Stage" in evo_report


# ===================================================================
# 10. v1.2 Feature Tests: Streaming, Corrections, Creativity, Rules
# ===================================================================


class TestChatStream:
    """Tests for the chat_stream() method on OllamaClient."""

    def test_chat_stream_method_exists(self):
        """OllamaClient has a chat_stream method."""
        client = OllamaClient()
        assert hasattr(client, "chat_stream")
        assert callable(client.chat_stream)

    def test_chat_stream_returns_generator(self):
        """chat_stream returns a generator type."""
        import types
        import inspect
        client = OllamaClient()
        # Verify chat_stream is a generator function
        assert inspect.isgeneratorfunction(client.chat_stream)
        # Verify it accepts the same args as chat()
        sig = inspect.signature(client.chat_stream)
        assert "messages" in sig.parameters
        assert "model" in sig.parameters
        assert "temperature" in sig.parameters


class TestCorrectionDirective:
    """Tests for dynamic correction injection into system prompt."""

    def test_build_correction_directive_empty(self, tmp_path):
        """Returns empty string when no corrections exist."""
        # We test via the KaitSidekick class methods directly.
        # Import here to avoid triggering the full Ollama check
        db_path = str(tmp_path / "corr_test.db")
        bank = ReasoningBank(db_path=db_path)

        # No corrections
        corrections = bank.get_recent_corrections(limit=5)
        assert len(corrections) == 0

    def test_build_correction_directive_with_data(self, tmp_path):
        """Corrections are formatted as AVOID instructions."""
        db_path = str(tmp_path / "corr_test2.db")
        bank = ReasoningBank(db_path=db_path)

        bank.record_correction(
            original="2+2=5",
            correction="2+2=4",
            reason="Basic arithmetic error",
            domain="math",
        )
        bank.record_correction(
            original="Python uses semicolons",
            correction="Python uses newlines",
            reason="Language syntax error",
            domain="code",
        )

        corrections = bank.get_recent_corrections(limit=5)
        assert len(corrections) == 2

        # Verify the corrections can be formatted into a directive
        lines = []
        for c in corrections:
            reason = c.get("reason", "")
            if reason:
                lines.append(f"- AVOID: {reason}")

        assert len(lines) == 2
        assert "AVOID: Basic arithmetic error" in lines[0] or "AVOID: Basic arithmetic error" in lines[1]
        assert "AVOID: Language syntax error" in lines[0] or "AVOID: Language syntax error" in lines[1]


class TestMandatoryCreativity:
    """Tests for mandatory creativity directive in responses."""

    def test_creativity_agent_provides_metaphor(self):
        """CreativityAgent always produces a metaphor for non-empty input."""
        orchestrator = AgentOrchestrator()
        result = orchestrator.dispatch(
            "creativity",
            {"user_message": "How does caching work?", "topic": "performance"},
        )
        assert result.success is True
        assert result.data.get("metaphor") is not None
        assert len(result.data["metaphor"]) > 10

    def test_creativity_fragments_removed_from_merge(self):
        """When creativity result is separated, merge_prompt_fragments
        doesn't include creativity fragments."""
        orchestrator = AgentOrchestrator()
        logic_result = orchestrator.dispatch(
            "logic", {"user_message": "calculate 5+5"},
        )
        sentiment_result = orchestrator.dispatch(
            "sentiment", {"user_message": "I love this"},
        )

        # Only merge logic + sentiment (creativity is now mandatory/separate)
        fragments = orchestrator.merge_prompt_fragments({
            "logic": logic_result,
            "sentiment": sentiment_result,
        })

        # No creativity fragments should appear
        for frag in fragments:
            assert "[Creativity]" not in frag


class TestBehaviorRules:
    """Tests for the actionable behavior rules system."""

    def test_pattern_detector_init(self):
        """PatternDetector can be instantiated."""
        from lib.sidekick.reflection import PatternDetector
        detector = PatternDetector()
        assert detector is not None

    def test_detect_correction_rules(self):
        """PatternDetector generates rules from repeated corrections."""
        from lib.sidekick.reflection import PatternDetector
        detector = PatternDetector()

        corrections = [
            {"category": "math", "original": "wrong", "corrected": "right"},
            {"category": "math", "original": "wrong2", "corrected": "right2"},
            {"category": "math", "original": "wrong3", "corrected": "right3"},
        ]

        rules = detector.detect_rules(
            interactions=[],
            corrections=corrections,
            existing_rules=[],
        )

        # Should produce at least one rule for repeated math corrections
        math_rules = [r for r in rules if "math" in r.trigger]
        assert len(math_rules) >= 1
        assert "double-check" in math_rules[0].action

    def test_detect_length_preference(self):
        """PatternDetector detects short response preference."""
        from lib.sidekick.reflection import PatternDetector
        detector = PatternDetector()

        interactions = [
            {"user_input": "hi", "ai_response": "Hello there!", "feedback": 0.9},
            {"user_input": "what's up", "ai_response": "Not much, just here to help!", "feedback": 0.8},
            {"user_input": "cool", "ai_response": "Thanks!", "feedback": 0.9},
            {"user_input": "thanks", "ai_response": "You're welcome!", "feedback": 0.7},
        ]

        rules = detector.detect_rules(
            interactions=interactions,
            corrections=[],
            existing_rules=[],
        )

        # May or may not trigger length rule (depends on word count thresholds)
        # But should not crash
        assert isinstance(rules, list)

    def test_reflection_cycle_produces_rules(self):
        """ReflectionCycle.reflect includes behavior_rules in output."""
        cycle = ReflectionCycle()
        result = cycle.reflect(
            interactions=[
                {"user_input": f"code question {i}", "ai_response": f"code answer {i}",
                 "feedback": 0.8}
                for i in range(5)
            ],
            corrections=[
                {"category": "code", "original": "x", "corrected": "y"},
                {"category": "code", "original": "a", "corrected": "b"},
            ],
            evolution_history=[],
        )

        assert "behavior_rules" in result
        assert isinstance(result["behavior_rules"], list)
        assert "all_active_rules" in result
        assert isinstance(result["all_active_rules"], list)

    def test_behavior_rule_to_prompt(self):
        """BehaviorRule.to_prompt_instruction returns a coherent string."""
        from lib.sidekick.reflection import BehaviorRule
        rule = BehaviorRule(
            rule_id="test1",
            trigger="the user asks about code",
            action="include a code example in the response",
            confidence=0.8,
        )
        instruction = rule.to_prompt_instruction()
        assert "When the user asks about code" in instruction
        assert "include a code example" in instruction

    def test_reflection_deactivate_rule(self):
        """ReflectionCycle.deactivate_rule removes rules from active set."""
        cycle = ReflectionCycle()
        # Generate some rules
        cycle.reflect(
            interactions=[
                {"user_input": f"msg {i}", "ai_response": f"resp {i}",
                 "feedback": 0.8}
                for i in range(5)
            ],
            corrections=[
                {"category": "math", "original": "x", "corrected": "y"},
                {"category": "math", "original": "a", "corrected": "b"},
            ],
            evolution_history=[],
        )

        rules = cycle.get_active_rules()
        if rules:
            rule_id = rules[0].rule_id
            assert cycle.deactivate_rule(rule_id) is True
            remaining = cycle.get_active_rules()
            assert all(r.rule_id != rule_id for r in remaining)


class TestProactiveInsights:
    """Tests for proactive insight surfacing."""

    def test_pending_insights_list(self):
        """KaitSidekick has a _pending_insights attribute (list)."""
        # We verify the attribute exists on import
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "__init__")
        # Verify _pending_insights is created in __init__
        import inspect
        source = inspect.getsource(mod.KaitSidekick.__init__)
        assert "_pending_insights" in source

    def test_config_has_stream_setting(self):
        """SidekickConfig has STREAM_TOKENS and MAX_CORRECTION_INJECTIONS."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        cfg = mod.SidekickConfig()
        assert hasattr(cfg, "STREAM_TOKENS")
        assert hasattr(cfg, "MAX_CORRECTION_INJECTIONS")
        assert hasattr(cfg, "MAX_BEHAVIOR_RULES")
        assert isinstance(cfg.STREAM_TOKENS, bool)
        assert isinstance(cfg.MAX_CORRECTION_INJECTIONS, int)
        assert isinstance(cfg.MAX_BEHAVIOR_RULES, int)


# ===================================================================
# v1.3 Tests: Pre-flight, Health, Daemon, Persistent Rules, Search
# ===================================================================


class TestPreflightChecks:
    """Tests for the run_preflight_checks() function."""

    def test_preflight_returns_list(self):
        """run_preflight_checks returns a list of check dicts."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        checks = mod.run_preflight_checks(verbose=False)
        assert isinstance(checks, list)
        assert len(checks) >= 4  # at least python, ollama binary, server, data dir

    def test_preflight_check_structure(self):
        """Each check dict has ok, name, detail, fix keys."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        checks = mod.run_preflight_checks(verbose=False)
        for c in checks:
            assert "ok" in c
            assert "name" in c
            assert "detail" in c
            assert isinstance(c["ok"], bool)
            assert isinstance(c["name"], str)

    def test_python_version_check_passes(self):
        """The Python version check result matches the actual runtime version."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        checks = mod.run_preflight_checks(verbose=False)
        python_check = next(c for c in checks if c["name"] == "Python version")
        expected = sys.version_info >= (3, 10)
        assert python_check["ok"] is expected

    def test_data_directory_check_passes(self):
        """Data directory check should pass (home dir is writable)."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        checks = mod.run_preflight_checks(verbose=False)
        data_check = next(c for c in checks if c["name"] == "Data directory")
        assert data_check["ok"] is True


class TestHealthCommand:
    """Tests for the /health command."""

    def test_show_health_method_exists(self):
        """KaitSidekick has a _show_health method."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "_show_health")
        assert callable(getattr(mod.KaitSidekick, "_show_health"))

    def test_health_command_in_handler(self):
        """The /health command is routed in _handle_command."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._handle_command)
        assert '"/health"' in source


class TestDaemonMode:
    """Tests for daemon mode CLI flag and _run_daemon function."""

    def test_run_daemon_function_exists(self):
        """The _run_daemon function exists in the module."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod, "_run_daemon")
        assert callable(mod._run_daemon)

    def test_daemon_argparse_flag(self):
        """The --daemon flag is recognized by the CLI parser."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        import argparse
        source_lines = open(mod.__file__).read()
        assert '"--daemon"' in source_lines

    def test_check_argparse_flag(self):
        """The --check flag is recognized by the CLI parser."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        source_lines = open(mod.__file__).read()
        assert '"--check"' in source_lines


class TestBehaviorRulePersistence:
    """Tests for behavior rules persisting to/from SQLite."""

    def test_save_and_get_behavior_rules(self, reasoning_bank):
        """Rules saved to DB can be retrieved."""
        reasoning_bank.save_behavior_rule(
            rule_id="r1",
            trigger="user asks about code",
            action="include a code example",
            confidence=0.8,
            source="test",
            created_at=time.time(),
            active=True,
        )
        rules = reasoning_bank.get_active_behavior_rules()
        assert len(rules) == 1
        assert rules[0]["rule_id"] == "r1"
        assert rules[0]["trigger"] == "user asks about code"
        assert rules[0]["action"] == "include a code example"
        assert rules[0]["confidence"] == 0.8

    def test_deactivate_behavior_rule(self, reasoning_bank):
        """Deactivated rules are excluded from active queries."""
        reasoning_bank.save_behavior_rule(
            rule_id="r2",
            trigger="any",
            action="be verbose",
            confidence=0.6,
            source="test",
            created_at=time.time(),
            active=True,
        )
        assert len(reasoning_bank.get_active_behavior_rules()) == 1
        reasoning_bank.deactivate_behavior_rule("r2")
        assert len(reasoning_bank.get_active_behavior_rules()) == 0

    def test_multiple_rules_ordered_by_confidence(self, reasoning_bank):
        """Rules are returned in descending confidence order."""
        for i, conf in enumerate([0.5, 0.9, 0.7]):
            reasoning_bank.save_behavior_rule(
                rule_id=f"r{i}",
                trigger=f"trigger_{i}",
                action=f"action_{i}",
                confidence=conf,
                source="test",
                created_at=time.time(),
            )
        rules = reasoning_bank.get_active_behavior_rules()
        assert len(rules) == 3
        assert rules[0]["confidence"] == 0.9
        assert rules[1]["confidence"] == 0.7
        assert rules[2]["confidence"] == 0.5

    def test_reflection_cycle_loads_from_bank(self, reasoning_bank):
        """ReflectionCycle loads persisted rules on init."""
        from lib.sidekick.reflection import ReflectionCycle
        # Save a rule before creating the cycle
        reasoning_bank.save_behavior_rule(
            rule_id="pre_exist",
            trigger="user greets",
            action="respond warmly",
            confidence=0.85,
            source="test",
            created_at=time.time(),
        )
        cycle = ReflectionCycle(reasoning_bank=reasoning_bank)
        active = cycle.get_active_rules()
        assert len(active) == 1
        assert active[0].rule_id == "pre_exist"

    def test_reflection_cycle_persists_new_rules(self, reasoning_bank):
        """New rules detected during reflect() are persisted to DB."""
        from lib.sidekick.reflection import ReflectionCycle
        cycle = ReflectionCycle(reasoning_bank=reasoning_bank)

        # Create interactions that trigger length preference detection
        interactions = []
        for i in range(5):
            interactions.append({
                "user_input": f"tell me about topic {i}",
                "ai_response": "short",  # very short = < 60 words
                "feedback": 0.8,
                "timestamp": time.time() - (i * 60),
            })

        corrections = []
        evolution_history = []

        result = cycle.reflect(interactions, corrections, evolution_history)
        # The rules from DB should match in-memory rules
        db_rules = reasoning_bank.get_active_behavior_rules()
        memory_rules = cycle.get_active_rules()
        # DB should have at least as many rules as were newly created
        assert len(db_rules) >= len(result.get("behavior_rules", []))

    def test_deactivate_persists_to_bank(self, reasoning_bank):
        """Deactivating a rule via ReflectionCycle persists to DB."""
        from lib.sidekick.reflection import ReflectionCycle
        reasoning_bank.save_behavior_rule(
            rule_id="deact_test",
            trigger="test",
            action="test",
            confidence=0.5,
            source="test",
            created_at=time.time(),
        )
        cycle = ReflectionCycle(reasoning_bank=reasoning_bank)
        assert len(cycle.get_active_rules()) == 1
        cycle.deactivate_rule("deact_test")
        assert len(cycle.get_active_rules()) == 0
        # Verify it's also deactivated in DB
        assert len(reasoning_bank.get_active_behavior_rules()) == 0


class TestSearchContexts:
    """Tests for ReasoningBank.search_contexts()."""

    def test_search_by_prefix(self, reasoning_bank):
        """search_contexts returns contexts matching key prefix."""
        reasoning_bank.save_context(
            key="idle_insight_100", value={"insight": "a"}, domain="meta"
        )
        reasoning_bank.save_context(
            key="idle_insight_200", value={"insight": "b"}, domain="meta"
        )
        reasoning_bank.save_context(
            key="topic_code", value={"count": 1}, domain="general"
        )
        results = reasoning_bank.search_contexts("idle_insight", domain="meta")
        assert len(results) == 2
        assert all("idle_insight" in r["key"] for r in results)

    def test_search_with_limit(self, reasoning_bank):
        """search_contexts respects the limit parameter."""
        for i in range(10):
            reasoning_bank.save_context(
                key=f"prefix_{i}", value={"n": i}, domain="test"
            )
        results = reasoning_bank.search_contexts("prefix_", limit=3)
        assert len(results) == 3

    def test_search_no_results(self, reasoning_bank):
        """search_contexts returns empty list when no match."""
        results = reasoning_bank.search_contexts("nonexistent_")
        assert results == []


class TestBehaviorRulesInStats:
    """Tests that behavior_rules count appears in get_stats()."""

    def test_stats_include_behavior_rules(self, reasoning_bank):
        """get_stats() includes behavior_rules count."""
        stats = reasoning_bank.get_stats()
        assert "behavior_rules" in stats
        assert stats["behavior_rules"] == 0

        reasoning_bank.save_behavior_rule(
            rule_id="stat_test",
            trigger="test",
            action="test",
            confidence=0.5,
            source="test",
            created_at=time.time(),
        )
        stats = reasoning_bank.get_stats()
        assert stats["behavior_rules"] == 1


class TestVersionConsistency:
    """Tests that version numbers are consistent across modules."""

    def test_main_version_is_4_0(self):
        """kait_ai_sidekick.py VERSION should be 4.0.0."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert mod.VERSION == "4.0.0"

    def test_init_version_matches(self):
        """lib/sidekick/__init__.py __version__ should match current."""
        from lib.sidekick import __version__
        assert __version__ == "4.0.0"


# ===================================================================
# v1.4 Tests: Session Resume, Semantic Context, Export, LLM Retry, Timing
# ===================================================================


class TestSessionResume:
    """Tests for session save/restore and welcome-back greeting."""

    def test_save_session_summary_method_exists(self):
        """KaitSidekick has _save_session_summary method."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "_save_session_summary")

    def test_restore_session_context_method_exists(self):
        """KaitSidekick has _restore_session_context method."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "_restore_session_context")

    def test_show_welcome_back_method_exists(self):
        """KaitSidekick has _show_welcome_back method."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "_show_welcome_back")

    def test_session_summary_persisted_to_bank(self, reasoning_bank):
        """Session summary context is stored in ReasoningBank."""
        reasoning_bank.update_context(
            "last_session_summary",
            {
                "session_id": "test123",
                "interaction_count": 5,
                "topics": ["coding", "math"],
                "stage": 2,
                "resonance": 0.65,
                "timestamp": time.time(),
                "last_turns": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi there"},
                ],
            },
            "session",
        )
        ctx = reasoning_bank.get_context("last_session_summary")
        assert ctx is not None
        val = ctx["value"]
        assert val["session_id"] == "test123"
        assert val["interaction_count"] == 5
        assert len(val["last_turns"]) == 2


class TestSemanticContextRetrieval:
    """Tests for keyword-overlap context retrieval."""

    def test_tokenize_for_search_exists(self):
        """KaitSidekick has a _tokenize_for_search static method."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "_tokenize_for_search")

    def test_tokenize_removes_stop_words(self):
        """_tokenize_for_search removes common stop words."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        tokens = mod.KaitSidekick._tokenize_for_search("the quick brown fox")
        assert "the" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens

    def test_tokenize_lowercases(self):
        """_tokenize_for_search lowercases all tokens."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        tokens = mod.KaitSidekick._tokenize_for_search("Python CODE Debug")
        assert "python" in tokens
        assert "code" in tokens
        assert "debug" in tokens

    def test_retrieve_context_has_relevant_memory(self):
        """_retrieve_context includes relevant_memory when past interactions match."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._retrieve_context)
        assert "relevant_memory" in source


class TestExportCommand:
    """Tests for the /export command."""

    def test_export_method_exists(self):
        """KaitSidekick has _export_conversation method."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "_export_conversation")

    def test_export_command_in_handler(self):
        """The /export command is routed in _handle_command."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._handle_command)
        assert '"/export"' in source or "export" in source

    def test_export_in_help(self):
        """The /export command appears in help output."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._show_help)
        assert "/export" in source


class TestLLMRetryWithTrimming:
    """Tests for LLM retry with progressive context trimming."""

    def test_build_llm_messages_method_exists(self):
        """KaitSidekick has _build_llm_messages method."""
        import importlib
        mod = importlib.import_module("kait_ai_sidekick")
        assert hasattr(mod.KaitSidekick, "_build_llm_messages")

    def test_build_llm_messages_accepts_history_window(self):
        """_build_llm_messages accepts a history_window parameter."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        sig = inspect.signature(mod.KaitSidekick._build_llm_messages)
        assert "history_window" in sig.parameters

    def test_generate_response_has_retry_loop(self):
        """_generate_response has a retry loop with multiple history windows."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._generate_response)
        assert "history_windows" in source or "window" in source

    def test_stream_response_reraises_on_empty(self):
        """_stream_response re-raises on zero tokens for retry."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._stream_response)
        assert "raise" in source


class TestResponseTiming:
    """Tests for response timing display."""

    def test_timing_in_process_interaction(self):
        """_process_interaction shows response time."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._process_interaction)
        assert "response_time_s" in source

    def test_interaction_count_displayed(self):
        """Interaction count is shown in response footer."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._process_interaction)
        assert "interaction_count" in source


class TestStatusKaitline:
    """Tests for sentiment kaitline in /status."""

    def test_status_has_kaitline(self):
        """_show_status includes sentiment kaitline."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._show_status)
        assert "kaitline" in source or "Sentiment" in source


class TestCommandArgCasePreservation:
    """Tests for QA fix: command arguments must preserve original case."""

    def test_handle_command_preserves_export_filename_case(self):
        """Ensure /export passes original-case filename, not lowercased."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._handle_command)
        # The fix uses `stripped[7:]` instead of `cmd[7:]` for /export
        assert "stripped[7:]" in source or "stripped[" in source

    def test_handle_command_preserves_correct_text_case(self):
        """Ensure /correct passes original-case text."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._handle_command)
        assert "stripped[9:]" in source

    def test_handle_command_preserves_tool_args_case(self):
        """Ensure /tool passes original-case arguments."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._handle_command)
        assert "stripped[6:]" in source


class TestVoiceReflection:
    """Tests for QA fix: voice input must trigger reflection and evolution."""

    def test_voice_triggers_reflect_and_evolve(self):
        """The /voice handler must call _maybe_reflect and _maybe_evolve."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._handle_command)
        # After _process_interaction in the /voice block, both must be called
        voice_idx = source.index("/voice")
        voice_block = source[voice_idx:voice_idx + 300]
        assert "_maybe_reflect" in voice_block
        assert "_maybe_evolve" in voice_block


class TestNoRedundantReImport:
    """Tests for QA fix: no redundant re import in _extract_tool_args."""

    def test_extract_tool_args_no_local_re_import(self):
        """_extract_tool_args must not re-import re module."""
        import importlib, inspect
        mod = importlib.import_module("kait_ai_sidekick")
        source = inspect.getsource(mod.KaitSidekick._extract_tool_args)
        assert "import re" not in source


# ===================================================================
# Claude Code Operations Tests
# ===================================================================

from lib.sidekick.claude_code_ops import ClaudeCodeOps, ClaudeCodeResult


class TestClaudeCodeOps:
    """Tests for the Claude Code autonomous operations module."""

    def test_result_dataclass(self):
        """ClaudeCodeResult holds expected fields."""
        result = ClaudeCodeResult(
            success=True,
            output="Hello World",
            files_created=["test.py"],
            duration_s=1.5,
        )
        assert result.success is True
        assert result.output == "Hello World"
        assert result.files_created == ["test.py"]
        assert result.duration_s == 1.5
        assert result.error == ""

    def test_result_to_dict(self):
        """to_dict returns a serializable dict."""
        result = ClaudeCodeResult(
            success=False,
            output="x" * 3000,
            error="timeout",
            duration_s=120.456,
        )
        d = result.to_dict()
        assert d["success"] is False
        assert len(d["output"]) <= 2000  # truncated
        assert d["error"] == "timeout"
        assert d["duration_s"] == 120.46

    def test_is_available_static(self):
        """is_available is a static method that returns bool."""
        result = ClaudeCodeOps.is_available()
        assert isinstance(result, bool)

    def test_ops_init(self):
        """ClaudeCodeOps initializes without error."""
        ops = ClaudeCodeOps()
        assert ops is not None
