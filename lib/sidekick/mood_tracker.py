"""Lightweight mood/state tracker for the Kait AI sidekick.

Replaces the visual AvatarManager with a pure-data state machine that
tracks mood, energy, warmth, confidence, kait level, and evolution
stage -- without any rendering dependencies.

The public API mirrors what ``kait_ai_sidekick.py`` used from
``AvatarManager`` so the switch is a drop-in replacement.

Design principles:
- Zero rendering dependencies (no pygame, no Qt, no GPU).
- Thread-safe reads; single-writer expected.
- All float axes clamped to [0.0, 1.0].
- Smooth transitions via linear interpolation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ===================================================================
# Constants (preserved from avatar.py)
# ===================================================================

VALID_MOODS = frozenset(
    [
        "excited",
        "calm",
        "curious",
        "deep_thought",
        "playful",
        "determined",
        "contemplative",
        "creative",
        "focused",
        "serene",
        "bold",
        "dreamy",
    ]
)

DEFAULT_MOOD = "calm"


# ===================================================================
# Mood profiles -- 12 distinct personalities
# ===================================================================

@dataclass(frozen=True)
class MoodProfile:
    """Static template for a single mood."""

    label: str
    description: str
    energy_bias: float
    warmth_bias: float
    confidence_bias: float
    kait_bias: float
    theme: str


MOOD_PROFILES: Dict[str, MoodProfile] = {
    "excited": MoodProfile(
        label="Excited",
        description="Fiery energy, kaits dancing",
        energy_bias=0.92, warmth_bias=0.85, confidence_bias=0.80,
        kait_bias=0.95, theme="cosmic_fire",
    ),
    "calm": MoodProfile(
        label="Calm",
        description="Tranquil and grounded",
        energy_bias=0.30, warmth_bias=0.60, confidence_bias=0.65,
        kait_bias=0.25, theme="ocean_calm",
    ),
    "curious": MoodProfile(
        label="Curious",
        description="Shifting prism, tendrils reaching out to explore",
        energy_bias=0.65, warmth_bias=0.70, confidence_bias=0.60,
        kait_bias=0.72, theme="prism_shift",
    ),
    "deep_thought": MoodProfile(
        label="Deep Thought",
        description="Dense core, slow orbiting rings of data",
        energy_bias=0.40, warmth_bias=0.45, confidence_bias=0.75,
        kait_bias=0.55, theme="nebula_dream",
    ),
    "playful": MoodProfile(
        label="Playful",
        description="Bouncing motes of color, joyful scatter",
        energy_bias=0.80, warmth_bias=0.88, confidence_bias=0.70,
        kait_bias=0.85, theme="rainbow_burst",
    ),
    "determined": MoodProfile(
        label="Determined",
        description="Sharp focused beams cutting outward",
        energy_bias=0.85, warmth_bias=0.55, confidence_bias=0.95,
        kait_bias=0.78, theme="electric_storm",
    ),
    "contemplative": MoodProfile(
        label="Contemplative",
        description="Softly pulsing amber glow, like a distant campfire",
        energy_bias=0.35, warmth_bias=0.72, confidence_bias=0.55,
        kait_bias=0.40, theme="ember_glow",
    ),
    "creative": MoodProfile(
        label="Creative",
        description="Swirling aurora, ideas taking shape",
        energy_bias=0.75, warmth_bias=0.78, confidence_bias=0.68,
        kait_bias=0.92, theme="aurora_weave",
    ),
    "focused": MoodProfile(
        label="Focused",
        description="Tight beam, all energy drawn inward",
        energy_bias=0.60, warmth_bias=0.40, confidence_bias=0.88,
        kait_bias=0.50, theme="steel_focus",
    ),
    "serene": MoodProfile(
        label="Serene",
        description="Pearlescent mist, floating weightless",
        energy_bias=0.20, warmth_bias=0.65, confidence_bias=0.70,
        kait_bias=0.18, theme="moonlit_mist",
    ),
    "bold": MoodProfile(
        label="Bold",
        description="Crimson flame corona, raw power radiating",
        energy_bias=0.90, warmth_bias=0.60, confidence_bias=0.92,
        kait_bias=0.88, theme="solar_flare",
    ),
    "dreamy": MoodProfile(
        label="Dreamy",
        description="Soft lavender clouds drifting through twilight",
        energy_bias=0.25, warmth_bias=0.75, confidence_bias=0.50,
        kait_bias=0.35, theme="twilight_drift",
    ),
}


# ===================================================================
# Evolution stage descriptors (preserved from avatar.py)
# ===================================================================

EVOLUTION_STAGES: Dict[int, Dict[str, str]] = {
    1: {"name": "Ember", "prefix": "A faint kait", "form": "a small flickering point of light"},
    2: {"name": "Glow", "prefix": "A growing glow", "form": "a warm orb trailing wisps of light"},
    3: {"name": "Flame", "prefix": "A vivid flame", "form": "a radiant sphere with tendrils of energy"},
    4: {"name": "Star", "prefix": "A brilliant star", "form": "a pulsing stellar body of concentrated intelligence"},
    5: {"name": "Cosmos", "prefix": "A cosmic entity", "form": "a swirling galaxy of thought and light"},
}

_MAX_EVOLUTION_STAGE = max(EVOLUTION_STAGES)


# ===================================================================
# Greetings keyed by mood (preserved from avatar.py)
# ===================================================================

_GREETINGS: Dict[str, List[str]] = {
    "excited": [
        "Systems are BLAZING -- let's light this up!",
        "I can feel the energy surging -- what's the mission?",
        "Kait levels off the charts today!",
    ],
    "calm": [
        "All systems at peace.  Ready when you are.",
        "Quiet and grounded -- a good place to start.",
        "The stillness before the next great idea.",
    ],
    "curious": [
        "I have questions forming already...",
        "Something new is tugging at my attention.",
        "Curiosity levels climbing -- show me something interesting.",
    ],
    "deep_thought": [
        "Processing deeply... give me a moment to crystallize this.",
        "I'm turning something over in my mind right now.",
        "Layers within layers -- there's more here than meets the eye.",
    ],
    "playful": [
        "Hey! Wanna see what happens when we break the rules a little?",
        "I'm in a playful mood -- expect unexpected connections.",
        "Mischief managed... or about to be.",
    ],
    "determined": [
        "Locked in.  Let's get this done.",
        "No distractions -- full power to the task at hand.",
        "I've got my sights set.  Let's execute.",
    ],
    "contemplative": [
        "I've been sitting with something... let me share.",
        "There's a thought I keep returning to.",
        "In the quiet, patterns become visible.",
    ],
    "creative": [
        "Ideas are colliding in beautiful ways right now.",
        "I can feel new shapes forming -- let's build something.",
        "The muse is here.  Let's not waste it.",
    ],
    "focused": [
        "All resources allocated.  Awaiting your target.",
        "Precision mode active.  What needs my attention?",
        "Sharp and ready.  Point me at the problem.",
    ],
    "serene": [
        "Everything feels aligned right now.",
        "A rare calm -- savor it with me.",
        "Peace is its own kind of power.",
    ],
    "bold": [
        "I feel UNSTOPPABLE.  Name the challenge.",
        "No hesitation.  Let's charge forward.",
        "Fortune favors the bold -- and right now, that's us.",
    ],
    "dreamy": [
        "Half-thoughts drifting like clouds... give me a thread to follow.",
        "I'm in the in-between -- imagination and memory blending.",
        "Let's wander a little before we decide where to go.",
    ],
}


# ===================================================================
# Utility helpers
# ===================================================================

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * _clamp(t)


# ===================================================================
# MoodState dataclass
# ===================================================================

@dataclass
class MoodState:
    """Complete snapshot of the sidekick's emotional state."""

    mood: str = DEFAULT_MOOD
    energy: float = 0.5
    warmth: float = 0.6
    confidence: float = 0.6
    kait_level: float = 0.4
    evolution_stage: int = 1
    visual_theme: str = "ocean_calm"

    def __post_init__(self) -> None:
        self.mood = self.mood if self.mood in VALID_MOODS else DEFAULT_MOOD
        self.energy = _clamp(self.energy)
        self.warmth = _clamp(self.warmth)
        self.confidence = _clamp(self.confidence)
        self.kait_level = _clamp(self.kait_level)
        self.evolution_stage = max(1, min(_MAX_EVOLUTION_STAGE, int(self.evolution_stage)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mood": self.mood,
            "energy": round(self.energy, 3),
            "warmth": round(self.warmth, 3),
            "confidence": round(self.confidence, 3),
            "kait_level": round(self.kait_level, 3),
            "evolution_stage": self.evolution_stage,
            "visual_theme": self.visual_theme,
        }


# ===================================================================
# MoodTracker -- drop-in replacement for AvatarManager
# ===================================================================

class MoodTracker:
    """Tracks mood, energy, warmth, confidence, kait level, and evolution
    stage as pure data -- no rendering.

    API-compatible with the methods used by ``kait_ai_sidekick.py`` from
    ``AvatarManager``:
    - ``update_mood(mood)``
    - ``set_kait_level(value)``
    - ``get_state()``
    - ``tick()``
    - ``close()``
    - ``get_display()``
    - ``get_kait_greeting()``
    - ``pulse_energy(delta)``
    - ``evolve(new_stage)``
    - ``set_warmth(value)``
    - ``set_confidence(value)``
    """

    _TRANSITION_SPEED: float = 0.15
    _MAX_TRANSITION_TICKS: int = 30

    def __init__(self, *, initial_mood: str = DEFAULT_MOOD) -> None:
        profile = MOOD_PROFILES.get(initial_mood, MOOD_PROFILES[DEFAULT_MOOD])
        self._state = MoodState(
            mood=initial_mood,
            energy=profile.energy_bias,
            warmth=profile.warmth_bias,
            confidence=profile.confidence_bias,
            kait_level=profile.kait_bias,
            evolution_stage=1,
            visual_theme=profile.theme,
        )
        self._target_state: Optional[MoodState] = None
        self._transition_ticks: int = 0

    # ---- state accessors --------------------------------------------------

    def get_state(self) -> MoodState:
        return self._state

    def get_display(self) -> str:
        """Return a short text indicator for terminal/UI display."""
        profile = MOOD_PROFILES.get(self._state.mood, MOOD_PROFILES[DEFAULT_MOOD])
        stage = EVOLUTION_STAGES.get(self._state.evolution_stage, EVOLUTION_STAGES[1])
        return (
            f"[mood: {profile.label.lower()} | "
            f"energy: {self._state.energy:.1f} | "
            f"kait: {self._state.evolution_stage} ({stage['name']})]"
        )

    def get_kait_greeting(self) -> str:
        """Generate a creative greeting based on current state."""
        mood = self._state.mood
        greetings = _GREETINGS.get(mood, _GREETINGS[DEFAULT_MOOD])
        greeting = random.choice(greetings)

        stage = EVOLUTION_STAGES.get(self._state.evolution_stage, EVOLUTION_STAGES[1])
        stage_note = f"  [{stage['name']} -- Stage {self._state.evolution_stage}]"

        energy_descriptor = (
            "High energy" if self._state.energy > 0.7
            else "Low energy" if self._state.energy < 0.3
            else "Balanced energy"
        )
        kait_descriptor = (
            "Kait is blazing" if self._state.kait_level > 0.75
            else "Kait is flickering" if self._state.kait_level < 0.25
            else "Kait is steady"
        )

        return f"{greeting}\n{stage_note}  {energy_descriptor}. {kait_descriptor}."

    # ---- state mutations --------------------------------------------------

    def update_mood(self, mood: str) -> None:
        """Transition to a new mood smoothly."""
        if mood not in MOOD_PROFILES:
            return
        profile = MOOD_PROFILES[mood]
        self._target_state = MoodState(
            mood=mood,
            energy=profile.energy_bias,
            warmth=profile.warmth_bias,
            confidence=profile.confidence_bias,
            kait_level=profile.kait_bias,
            evolution_stage=self._state.evolution_stage,
            visual_theme=profile.theme,
        )
        self._transition_ticks = 0
        self._apply_transition()

    def pulse_energy(self, delta: float) -> None:
        self._state.energy = _clamp(self._state.energy + delta)

    def evolve(self, new_stage: int) -> None:
        clamped = max(1, min(_MAX_EVOLUTION_STAGE, int(new_stage)))
        if clamped <= self._state.evolution_stage:
            return
        self._state.evolution_stage = clamped

    def set_kait_level(self, value: float) -> None:
        self._state.kait_level = _clamp(value)

    def set_warmth(self, value: float) -> None:
        self._state.warmth = _clamp(value)

    def set_confidence(self, value: float) -> None:
        self._state.confidence = _clamp(value)

    # ---- smooth transition ------------------------------------------------

    def _apply_transition(self) -> None:
        if self._target_state is None:
            return
        tgt = self._target_state
        t = self._TRANSITION_SPEED

        self._state.energy = _lerp(self._state.energy, tgt.energy, t)
        self._state.warmth = _lerp(self._state.warmth, tgt.warmth, t)
        self._state.confidence = _lerp(self._state.confidence, tgt.confidence, t)
        self._state.kait_level = _lerp(self._state.kait_level, tgt.kait_level, t)

        self._state.mood = tgt.mood
        self._state.visual_theme = tgt.visual_theme

    def tick(self) -> None:
        """Advance the transition by one step."""
        if self._target_state is not None:
            self._apply_transition()
            self._transition_ticks += 1
            tgt = self._target_state

            converged = (
                abs(self._state.energy - tgt.energy) < 0.005
                and abs(self._state.warmth - tgt.warmth) < 0.005
                and abs(self._state.confidence - tgt.confidence) < 0.005
                and abs(self._state.kait_level - tgt.kait_level) < 0.005
            )
            if converged or self._transition_ticks >= self._MAX_TRANSITION_TICKS:
                self._state.energy = tgt.energy
                self._state.warmth = tgt.warmth
                self._state.confidence = tgt.confidence
                self._state.kait_level = tgt.kait_level
                self._target_state = None
                self._transition_ticks = 0

    def close(self) -> None:
        """No-op -- no resources to release."""
        pass


# ===================================================================
# Module exports
# ===================================================================

__all__ = [
    "MoodState",
    "MoodTracker",
    "MoodProfile",
    "MOOD_PROFILES",
    "EVOLUTION_STAGES",
    "VALID_MOODS",
    "DEFAULT_MOOD",
]
