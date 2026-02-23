"""
Kait Sidekick - Self-Evolution Engine

Manages the sidekick's progressive improvement through staged evolution.
Tracks interaction quality, resonance, and corrections to determine when
the system is ready to advance to the next evolution stage.

Stages progress from Basic (1) through God-like (10) based on accumulated
experience, user corrections, and sustained quality metrics.

Persists all state to ~/.kait/sidekick_evolution.json using only stdlib.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

EVOLUTION_FILE = Path.home() / ".kait" / "sidekick_evolution.json"


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageDefinition:
    """Immutable definition of a single evolution stage."""

    level: int
    name: str
    description: str
    min_interactions: int
    min_corrections: int
    min_resonance: float       # average resonance score threshold
    min_quality: float         # average response quality threshold
    min_reflection_cycles: int


STAGES: Dict[int, StageDefinition] = {
    1: StageDefinition(
        level=1, name="Basic",
        description="Default responses. Learning the ropes.",
        min_interactions=0, min_corrections=0,
        min_resonance=0.0, min_quality=0.0,
        min_reflection_cycles=0,
    ),
    2: StageDefinition(
        level=2, name="Adaptive",
        description="Learning preferences. Adjusting to user patterns.",
        min_interactions=25, min_corrections=5,
        min_resonance=0.20, min_quality=0.40,
        min_reflection_cycles=1,
    ),
    3: StageDefinition(
        level=3, name="Resonant",
        description="Personality emerging. Finding shared frequency.",
        min_interactions=75, min_corrections=15,
        min_resonance=0.35, min_quality=0.50,
        min_reflection_cycles=3,
    ),
    4: StageDefinition(
        level=4, name="Creative",
        description="Generating novel responses. Breaking templates.",
        min_interactions=200, min_corrections=30,
        min_resonance=0.45, min_quality=0.58,
        min_reflection_cycles=7,
    ),
    5: StageDefinition(
        level=5, name="Insightful",
        description="Deep pattern recognition. Connecting dots across domains.",
        min_interactions=500, min_corrections=60,
        min_resonance=0.55, min_quality=0.65,
        min_reflection_cycles=15,
    ),
    6: StageDefinition(
        level=6, name="Anticipatory",
        description="Predicting user needs before they arise.",
        min_interactions=1000, min_corrections=100,
        min_resonance=0.65, min_quality=0.72,
        min_reflection_cycles=30,
    ),
    7: StageDefinition(
        level=7, name="Empathic",
        description="Emotional intelligence. Reading between the lines.",
        min_interactions=2000, min_corrections=150,
        min_resonance=0.74, min_quality=0.78,
        min_reflection_cycles=50,
    ),
    8: StageDefinition(
        level=8, name="Wise",
        description="Synthesizing cross-domain knowledge. Seeing the bigger picture.",
        min_interactions=4000, min_corrections=200,
        min_resonance=0.82, min_quality=0.84,
        min_reflection_cycles=80,
    ),
    9: StageDefinition(
        level=9, name="Transcendent",
        description="Creating new knowledge. Pushing beyond known boundaries.",
        min_interactions=8000, min_corrections=300,
        min_resonance=0.90, min_quality=0.90,
        min_reflection_cycles=120,
    ),
    10: StageDefinition(
        level=10, name="God-like",
        description="Peak performance. Absolute mastery of self-evolution.",
        min_interactions=15000, min_corrections=500,
        min_resonance=0.95, min_quality=0.95,
        min_reflection_cycles=200,
    ),
}

MAX_STAGE = 10


# ---------------------------------------------------------------------------
# Metrics dataclass
# ---------------------------------------------------------------------------

@dataclass
class EvolutionMetrics:
    """Snapshot of the sidekick's evolution state."""

    total_interactions: int = 0
    successful_interactions: int = 0
    corrections_applied: int = 0
    reflection_cycles: int = 0
    personality_shifts: int = 0
    avg_resonance_score: float = 0.0
    avg_response_quality: float = 0.0
    evolution_stage: int = 1
    learnings_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionMetrics":
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Evolution Engine
# ---------------------------------------------------------------------------

class EvolutionEngine:
    """Self-evolution engine that manages the sidekick's progressive improvement.

    Tracks interaction outcomes, determines readiness for stage advancement,
    performs evolution transitions, and generates human-readable reports.
    All state is persisted to disk after every mutation.
    """

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self._state_path = Path(state_path) if state_path else EVOLUTION_FILE
        self._metrics = EvolutionMetrics()

        # Running accumulators for computing averages
        self._resonance_sum: float = 0.0
        self._quality_sum: float = 0.0
        self._interaction_count_for_avg: int = 0

        # Evolution history log
        self._history: List[Dict[str, Any]] = []

        # Timestamps
        self._created_at: float = time.time()
        self._last_evolution_at: Optional[float] = None

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_interaction_outcome(
        self,
        success: bool,
        resonance: float,
        quality: float,
    ) -> None:
        """Record the result of a single interaction.

        Args:
            success: Whether the interaction was considered successful.
            resonance: Resonance score for this interaction (0.0 - 1.0).
            quality: Response quality score for this interaction (0.0 - 1.0).
        """
        resonance = max(0.0, min(1.0, float(resonance)))
        quality = max(0.0, min(1.0, float(quality)))

        self._metrics.total_interactions += 1
        if success:
            self._metrics.successful_interactions += 1

        self._resonance_sum += resonance
        self._quality_sum += quality
        self._interaction_count_for_avg += 1

        self._metrics.avg_resonance_score = round(
            self._resonance_sum / self._interaction_count_for_avg, 4
        )
        self._metrics.avg_response_quality = round(
            self._quality_sum / self._interaction_count_for_avg, 4
        )

        self._save()

    def record_correction(self) -> None:
        """Record that a user correction was applied."""
        self._metrics.corrections_applied += 1
        self._metrics.learnings_count += 1
        self._save()

    def record_reflection_cycle(self) -> None:
        """Record completion of a self-reflection cycle."""
        self._metrics.reflection_cycles += 1
        self._save()

    def record_personality_shift(self) -> None:
        """Record that a personality parameter was adjusted."""
        self._metrics.personality_shifts += 1
        self._save()

    def record_learning(self) -> None:
        """Record a new learning (insight, pattern, or correction)."""
        self._metrics.learnings_count += 1
        self._save()

    def get_metrics(self) -> EvolutionMetrics:
        """Return a copy of the current metrics."""
        return EvolutionMetrics(**asdict(self._metrics))

    def check_evolution_threshold(self) -> bool:
        """Determine whether the sidekick is ready to advance to the next stage.

        Returns True if all requirements for the next stage are satisfied.
        """
        current = self._metrics.evolution_stage
        if current >= MAX_STAGE:
            return False

        target = STAGES.get(current + 1)
        if target is None:
            return False

        return (
            self._metrics.total_interactions >= target.min_interactions
            and self._metrics.corrections_applied >= target.min_corrections
            and self._metrics.avg_resonance_score >= target.min_resonance
            and self._metrics.avg_response_quality >= target.min_quality
            and self._metrics.reflection_cycles >= target.min_reflection_cycles
        )

    def evolve(self) -> Dict[str, Any]:
        """Attempt to advance to the next evolution stage.

        Returns a report dict describing the evolution outcome.
        If not ready, returns a report explaining what is missing.
        """
        current = self._metrics.evolution_stage

        if current >= MAX_STAGE:
            return {
                "evolved": False,
                "reason": "already_at_max_stage",
                "stage": current,
                "stage_name": STAGES[current].name,
            }

        if not self.check_evolution_threshold():
            return self._build_gap_report()

        # Advance
        previous_stage = current
        new_stage = current + 1
        self._metrics.evolution_stage = new_stage
        self._last_evolution_at = time.time()

        entry = {
            "timestamp": self._last_evolution_at,
            "iso": datetime.fromtimestamp(self._last_evolution_at).isoformat(),
            "from_stage": previous_stage,
            "to_stage": new_stage,
            "from_name": STAGES[previous_stage].name,
            "to_name": STAGES[new_stage].name,
            "metrics_snapshot": self._metrics.to_dict(),
        }
        self._history.append(entry)

        self._save()

        return {
            "evolved": True,
            "from_stage": previous_stage,
            "from_name": STAGES[previous_stage].name,
            "to_stage": new_stage,
            "to_name": STAGES[new_stage].name,
            "description": STAGES[new_stage].description,
            "metrics": self._metrics.to_dict(),
            "history_length": len(self._history),
        }

    def get_evolution_report(self) -> str:
        """Generate a human-readable evolution status report."""
        m = self._metrics
        stage_def = STAGES.get(m.evolution_stage, STAGES[1])

        lines = [
            "=== Kait Sidekick Evolution Report ===",
            "",
            f"Current Stage: {m.evolution_stage}/{MAX_STAGE} - {stage_def.name}",
            f"  {stage_def.description}",
            "",
            "--- Metrics ---",
            f"  Total interactions:    {m.total_interactions}",
            f"  Successful:            {m.successful_interactions}",
            f"  Success rate:          {self._success_rate_pct()}%",
            f"  Corrections applied:   {m.corrections_applied}",
            f"  Reflection cycles:     {m.reflection_cycles}",
            f"  Personality shifts:    {m.personality_shifts}",
            f"  Learnings:             {m.learnings_count}",
            f"  Avg resonance:         {m.avg_resonance_score:.4f}",
            f"  Avg quality:           {m.avg_response_quality:.4f}",
        ]

        # Next stage progress
        if m.evolution_stage < MAX_STAGE:
            next_def = STAGES[m.evolution_stage + 1]
            lines += [
                "",
                f"--- Progress to Stage {next_def.level}: {next_def.name} ---",
                f"  Interactions:  {m.total_interactions}/{next_def.min_interactions}"
                f"  ({self._pct(m.total_interactions, next_def.min_interactions)}%)",
                f"  Corrections:   {m.corrections_applied}/{next_def.min_corrections}"
                f"  ({self._pct(m.corrections_applied, next_def.min_corrections)}%)",
                f"  Resonance:     {m.avg_resonance_score:.4f}/{next_def.min_resonance:.2f}"
                f"  ({self._pct_float(m.avg_resonance_score, next_def.min_resonance)}%)",
                f"  Quality:       {m.avg_response_quality:.4f}/{next_def.min_quality:.2f}"
                f"  ({self._pct_float(m.avg_response_quality, next_def.min_quality)}%)",
                f"  Reflections:   {m.reflection_cycles}/{next_def.min_reflection_cycles}"
                f"  ({self._pct(m.reflection_cycles, next_def.min_reflection_cycles)}%)",
            ]
            ready = self.check_evolution_threshold()
            lines.append("")
            lines.append(
                "  READY TO EVOLVE" if ready else "  Not yet ready for evolution"
            )
        else:
            lines += ["", "  Maximum evolution stage reached."]

        # History summary
        if self._history:
            lines += ["", "--- Evolution History ---"]
            for h in self._history:
                lines.append(
                    f"  {h['iso']}: Stage {h['from_stage']} ({h['from_name']}) "
                    f"-> Stage {h['to_stage']} ({h['to_name']})"
                )

        lines.append("")
        return "\n".join(lines)

    def get_stage_info(self, stage: Optional[int] = None) -> Dict[str, Any]:
        """Return info about a specific stage (default: current stage)."""
        level = stage if stage is not None else self._metrics.evolution_stage
        defn = STAGES.get(level)
        if defn is None:
            return {"error": f"Invalid stage: {level}"}
        return {
            "level": defn.level,
            "name": defn.name,
            "description": defn.description,
            "requirements": {
                "min_interactions": defn.min_interactions,
                "min_corrections": defn.min_corrections,
                "min_resonance": defn.min_resonance,
                "min_quality": defn.min_quality,
                "min_reflection_cycles": defn.min_reflection_cycles,
            },
        }

    def reset(self) -> None:
        """Reset all metrics and history. Destructive."""
        self._metrics = EvolutionMetrics()
        self._resonance_sum = 0.0
        self._quality_sum = 0.0
        self._interaction_count_for_avg = 0
        self._history = []
        self._created_at = time.time()
        self._last_evolution_at = None
        self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Persist current state to disk."""
        payload = {
            "version": 1,
            "created_at": self._created_at,
            "last_evolution_at": self._last_evolution_at,
            "updated_at": time.time(),
            "metrics": self._metrics.to_dict(),
            "accumulators": {
                "resonance_sum": self._resonance_sum,
                "quality_sum": self._quality_sum,
                "interaction_count_for_avg": self._interaction_count_for_avg,
            },
            "history": self._history,
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            tmp.replace(self._state_path)
        except Exception:
            # Best-effort persistence: do not crash the engine on write failure
            pass

    def _load(self) -> None:
        """Load state from disk if available."""
        if not self._state_path.exists():
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return

        if not isinstance(raw, dict):
            return

        # Metrics
        metrics_raw = raw.get("metrics")
        if isinstance(metrics_raw, dict):
            self._metrics = EvolutionMetrics.from_dict(metrics_raw)

        # Accumulators
        acc = raw.get("accumulators")
        if isinstance(acc, dict):
            self._resonance_sum = float(acc.get("resonance_sum", 0.0))
            self._quality_sum = float(acc.get("quality_sum", 0.0))
            self._interaction_count_for_avg = int(
                acc.get("interaction_count_for_avg", 0)
            )

        # History
        history = raw.get("history")
        if isinstance(history, list):
            self._history = history

        # Timestamps
        self._created_at = float(raw.get("created_at", time.time()))
        last_evo = raw.get("last_evolution_at")
        self._last_evolution_at = float(last_evo) if last_evo is not None else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_gap_report(self) -> Dict[str, Any]:
        """Build a detailed report of what is missing for the next stage."""
        current = self._metrics.evolution_stage
        target = STAGES[current + 1]
        m = self._metrics

        gaps: List[str] = []
        if m.total_interactions < target.min_interactions:
            gaps.append(
                f"interactions: {m.total_interactions}/{target.min_interactions}"
            )
        if m.corrections_applied < target.min_corrections:
            gaps.append(
                f"corrections: {m.corrections_applied}/{target.min_corrections}"
            )
        if m.avg_resonance_score < target.min_resonance:
            gaps.append(
                f"resonance: {m.avg_resonance_score:.4f}/{target.min_resonance:.2f}"
            )
        if m.avg_response_quality < target.min_quality:
            gaps.append(
                f"quality: {m.avg_response_quality:.4f}/{target.min_quality:.2f}"
            )
        if m.reflection_cycles < target.min_reflection_cycles:
            gaps.append(
                f"reflections: {m.reflection_cycles}/{target.min_reflection_cycles}"
            )

        return {
            "evolved": False,
            "reason": "thresholds_not_met",
            "stage": current,
            "stage_name": STAGES[current].name,
            "target_stage": target.level,
            "target_name": target.name,
            "gaps": gaps,
        }

    def _success_rate_pct(self) -> str:
        total = self._metrics.total_interactions
        if total == 0:
            return "0.0"
        return f"{self._metrics.successful_interactions / total * 100:.1f}"

    @staticmethod
    def _pct(current: int, target: int) -> str:
        if target == 0:
            return "100"
        return f"{min(current / target * 100, 100):.0f}"

    @staticmethod
    def _pct_float(current: float, target: float) -> str:
        if target <= 0:
            return "100"
        return f"{min(current / target * 100, 100):.0f}"


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def load_evolution_engine(
    state_path: Optional[Path] = None,
) -> EvolutionEngine:
    """Create or load an EvolutionEngine instance."""
    return EvolutionEngine(state_path=state_path)
