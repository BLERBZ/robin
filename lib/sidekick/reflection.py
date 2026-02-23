"""
Kait Sidekick Self-Reflection Engine

Periodic introspection cycles that allow the AI sidekick to evolve
its behaviour, refine its system prompts, and improve over time.

Components:
  - ReflectionCycle    : Analyses recent interactions / corrections to produce
                         actionable insights and behaviour adjustments.
  - BehaviorEvolver    : Proposes, applies, and can rollback concrete
                         behaviour evolutions based on reflection output.
  - PromptRefiner      : Iteratively refines the system prompt using
                         accumulated learnings and user preferences.
  - ReflectionScheduler: Determines when the next reflection cycle should
                         run (every N interactions or M minutes).

All components are stdlib-only, stateless-friendly (state is passed in /
returned as dicts), and fully type-hinted.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Actionable Behavior Rules
# ---------------------------------------------------------------------------

@dataclass
class BehaviorRule:
    """A concrete, actionable rule derived from pattern analysis.

    These rules are injected directly into the system prompt so the LLM
    *actually changes behavior* rather than just noting an insight.

    Attributes:
        rule_id: Unique identifier.
        trigger: When this rule activates (e.g. "user asks about code").
        action: What the AI should do (e.g. "include a code example").
        confidence: How sure we are this rule is valid (0-1).
        source: What evidence created this rule.
        created_at: When the rule was created.
        active: Whether the rule is currently applied.
    """
    rule_id: str = ""
    trigger: str = ""
    action: str = ""
    confidence: float = 0.5
    source: str = ""
    created_at: float = field(default_factory=time.time)
    active: bool = True

    def to_prompt_instruction(self) -> str:
        """Convert to a prompt-ready instruction string."""
        return f"When {self.trigger}, {self.action}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "trigger": self.trigger,
            "action": self.action,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "created_at": self.created_at,
            "active": self.active,
        }


# ---------------------------------------------------------------------------
# ReflectionCycle
# ---------------------------------------------------------------------------

class PatternDetector:
    """Detects actionable patterns from interaction history and produces
    concrete ``BehaviorRule`` instances that modify the AI's behavior.

    This is the heart of the "superior experience" upgrade: instead of
    producing generic insights like "user sentiment is neutral," it
    produces rules like "when user asks about code, include a code example."
    """

    def detect_rules(
        self,
        interactions: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        existing_rules: Optional[List[BehaviorRule]] = None,
    ) -> List[BehaviorRule]:
        """Analyze interactions and corrections to generate behavior rules."""
        rules: List[BehaviorRule] = []
        existing_triggers: Set[str] = {
            r.trigger for r in (existing_rules or []) if r.active
        }

        rules.extend(self._detect_topic_response_patterns(interactions, existing_triggers))
        rules.extend(self._detect_correction_patterns(corrections, existing_triggers))
        rules.extend(self._detect_length_preference(interactions, existing_triggers))
        rules.extend(self._detect_followup_patterns(interactions, existing_triggers))
        rules.extend(self._detect_time_patterns(interactions, existing_triggers))

        return rules

    def _detect_topic_response_patterns(
        self,
        interactions: List[Dict[str, Any]],
        existing: Set[str],
    ) -> List[BehaviorRule]:
        """If the user repeatedly asks about a topic and gives positive
        feedback, create a rule to proactively address that topic well."""
        rules: List[BehaviorRule] = []
        topic_feedback: Dict[str, List[float]] = defaultdict(list)

        for ix in interactions:
            user_input = ix.get("user_input", "").lower()
            feedback = ix.get("feedback")
            if feedback is None:
                continue

            # Detect topic keywords
            for topic, keywords in _TOPIC_KEYWORDS.items():
                if any(kw in user_input for kw in keywords):
                    topic_feedback[topic].append(float(feedback))

        for topic, feedbacks in topic_feedback.items():
            if len(feedbacks) < 2:
                continue
            avg_fb = sum(feedbacks) / len(feedbacks)
            trigger = f"the user asks about {topic}"
            if trigger in existing:
                continue

            if avg_fb > 0.3:
                rules.append(BehaviorRule(
                    rule_id=_short_uuid(),
                    trigger=trigger,
                    action=(
                        f"provide detailed, example-rich responses about {topic} "
                        f"since the user consistently engages well with this topic"
                    ),
                    confidence=min(0.9, 0.4 + len(feedbacks) * 0.1),
                    source=f"topic_pattern:{topic}:n={len(feedbacks)}:avg_fb={avg_fb:.2f}",
                ))
            elif avg_fb < -0.2:
                rules.append(BehaviorRule(
                    rule_id=_short_uuid(),
                    trigger=trigger,
                    action=(
                        f"be extra careful and ask clarifying questions about {topic} "
                        f"before diving deep, since past responses haven't landed well"
                    ),
                    confidence=min(0.9, 0.4 + len(feedbacks) * 0.1),
                    source=f"topic_pattern:{topic}:n={len(feedbacks)}:avg_fb={avg_fb:.2f}",
                ))

        return rules

    def _detect_correction_patterns(
        self,
        corrections: List[Dict[str, Any]],
        existing: Set[str],
    ) -> List[BehaviorRule]:
        """Turn repeated corrections into preventive rules."""
        rules: List[BehaviorRule] = []
        category_counts: Dict[str, int] = Counter(
            c.get("category", c.get("domain", "general")) for c in corrections
        )

        for category, count in category_counts.items():
            if count < 2:
                continue
            trigger = f"generating a response about {category}"
            if trigger in existing:
                continue

            rules.append(BehaviorRule(
                rule_id=_short_uuid(),
                trigger=trigger,
                action=(
                    f"double-check {category}-related claims before stating them, "
                    f"since {count} corrections have been needed in this area"
                ),
                confidence=min(0.95, 0.5 + count * 0.1),
                source=f"correction_pattern:{category}:count={count}",
            ))

        return rules

    def _detect_length_preference(
        self,
        interactions: List[Dict[str, Any]],
        existing: Set[str],
    ) -> List[BehaviorRule]:
        """Detect whether user prefers short or long responses."""
        trigger = "composing any response"
        if trigger in existing:
            return []

        positive_lengths: List[int] = []
        negative_lengths: List[int] = []

        for ix in interactions:
            feedback = ix.get("feedback")
            if feedback is None:
                continue
            resp_len = len(ix.get("ai_response", "").split())
            if feedback > 0.3:
                positive_lengths.append(resp_len)
            elif feedback < -0.2:
                negative_lengths.append(resp_len)

        if len(positive_lengths) < 3:
            return []

        avg_good = sum(positive_lengths) / len(positive_lengths)
        avg_bad = sum(negative_lengths) / len(negative_lengths) if negative_lengths else avg_good

        rules: List[BehaviorRule] = []
        if avg_good < 60 and (not negative_lengths or avg_bad > avg_good * 1.5):
            rules.append(BehaviorRule(
                rule_id=_short_uuid(),
                trigger=trigger,
                action=(
                    "keep responses concise and focused (under 80 words when possible), "
                    "since the user consistently prefers shorter answers"
                ),
                confidence=0.7,
                source=f"length_pref:avg_good={avg_good:.0f}:avg_bad={avg_bad:.0f}",
            ))
        elif avg_good > 120:
            rules.append(BehaviorRule(
                rule_id=_short_uuid(),
                trigger=trigger,
                action=(
                    "provide thorough, detailed responses with examples, "
                    "since the user appreciates depth and detail"
                ),
                confidence=0.7,
                source=f"length_pref:avg_good={avg_good:.0f}",
            ))

        return rules

    def _detect_followup_patterns(
        self,
        interactions: List[Dict[str, Any]],
        existing: Set[str],
    ) -> List[BehaviorRule]:
        """Detect when users frequently ask follow-up questions, suggesting
        the initial response should anticipate them."""
        trigger = "the user might need follow-up information"
        if trigger in existing:
            return []

        followup_signals = [
            "can you also", "what about", "and how", "but what if",
            "one more thing", "follow up", "additionally", "also",
            "related to that", "building on that",
        ]

        followup_count = 0
        for ix in interactions:
            user_input = ix.get("user_input", "").lower()
            if any(sig in user_input for sig in followup_signals):
                followup_count += 1

        if followup_count >= 3 and len(interactions) >= 5:
            ratio = followup_count / len(interactions)
            if ratio > 0.3:
                return [BehaviorRule(
                    rule_id=_short_uuid(),
                    trigger=trigger,
                    action=(
                        "anticipate follow-up questions and proactively address "
                        "related aspects in the response, since the user frequently "
                        "asks follow-ups"
                    ),
                    confidence=min(0.85, 0.5 + ratio),
                    source=f"followup_pattern:count={followup_count}:ratio={ratio:.2f}",
                )]
        return []

    def _detect_time_patterns(
        self,
        interactions: List[Dict[str, Any]],
        existing: Set[str],
    ) -> List[BehaviorRule]:
        """Detect time-of-day patterns (e.g., user is more casual at night)."""
        trigger = "interacting during late hours"
        if trigger in existing:
            return []

        evening_interactions = 0
        evening_positive = 0
        for ix in interactions:
            ts = ix.get("timestamp")
            if ts is None:
                continue
            import datetime
            hour = datetime.datetime.fromtimestamp(float(ts)).hour
            if 20 <= hour or hour < 6:
                evening_interactions += 1
                fb = ix.get("feedback")
                if fb is not None and fb > 0.3:
                    evening_positive += 1

        if evening_interactions >= 3:
            return [BehaviorRule(
                rule_id=_short_uuid(),
                trigger=trigger,
                action=(
                    "adopt a more relaxed, conversational tone since the user "
                    "tends to interact during off-hours"
                ),
                confidence=0.5,
                source=f"time_pattern:evening={evening_interactions}",
            )]
        return []


# Topic keywords for pattern detection
_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "code": ["code", "program", "function", "debug", "error", "bug", "script", "class", "api"],
    "math": ["calculate", "compute", "equation", "formula", "math", "number", "solve"],
    "creative": ["write", "story", "poem", "creative", "imagine", "design", "art"],
    "learning": ["learn", "explain", "teach", "understand", "how does", "what is"],
    "personal": ["feel", "think", "opinion", "advice", "recommend", "suggest"],
}


class ReflectionCycle:
    """Performs a full reflection cycle over recent interaction history.

    Analyses three streams:
      1. **interactions** - recent user<->AI exchanges
      2. **corrections**  - explicit user corrections or negative feedback
      3. **evolution_history** - past evolutions (to avoid repeats and detect regressions)

    Produces insights, behaviour adjustments, prompt refinement suggestions,
    behavior rules, and an overall confidence score.

    Usage::

        rc = ReflectionCycle()
        result = rc.reflect(
            interactions=[...],
            corrections=[...],
            evolution_history=[...],
        )
    """

    # Minimum interactions needed for a meaningful reflection
    _MIN_INTERACTIONS: int = 3

    def __init__(self, reasoning_bank=None) -> None:
        self._pattern_detector = PatternDetector()
        self._bank = reasoning_bank
        self._behavior_rules: List[BehaviorRule] = []

        # Load existing rules from DB if a reasoning bank is provided
        if self._bank is not None:
            try:
                for row in self._bank.get_active_behavior_rules():
                    self._behavior_rules.append(BehaviorRule(
                        rule_id=row["rule_id"],
                        trigger=row["trigger"],
                        action=row["action"],
                        confidence=row["confidence"],
                        source=row.get("source", ""),
                        created_at=row["created_at"],
                        active=bool(row.get("active", 1)),
                    ))
            except Exception:
                pass  # DB may not have the table yet

    def reflect(
        self,
        interactions: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        evolution_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run a full reflection cycle.

        Parameters
        ----------
        interactions : list[dict]
            Recent exchanges.  Each dict should have at least
            ``user_input``, ``ai_response``, and optionally ``feedback``
            (float, -1 to 1) and ``timestamp`` (float).
        corrections : list[dict]
            Explicit corrections.  Each should have ``original``,
            ``corrected``, and ``category`` (str).
        evolution_history : list[dict]
            Prior evolution records (from ``BehaviorEvolver``).

        Returns
        -------
        dict
            insights            : list[str]
            behavior_adjustments: list[dict]  (type, description, priority)
            prompt_refinements  : list[str]
            behavior_rules      : list[dict]  (actionable rules)
            confidence_score    : float (0.0 - 1.0)
            reflection_id       : str
            timestamp           : float
        """
        reflection_id = _short_uuid()
        ts = time.time()

        insights = self._extract_insights(interactions, corrections)
        adjustments = self._propose_adjustments(
            interactions, corrections, evolution_history
        )
        refinements = self._suggest_prompt_refinements(
            interactions, corrections
        )

        # NEW: Detect actionable behavior rules
        new_rules = self._pattern_detector.detect_rules(
            interactions, corrections, self._behavior_rules
        )
        self._behavior_rules.extend(new_rules)

        # Persist new rules to DB if a reasoning bank is available
        if self._bank is not None:
            for rule in new_rules:
                try:
                    self._bank.save_behavior_rule(
                        rule_id=rule.rule_id,
                        trigger=rule.trigger,
                        action=rule.action,
                        confidence=rule.confidence,
                        source=rule.source,
                        created_at=rule.created_at,
                        active=rule.active,
                    )
                except Exception:
                    pass

        confidence = self._compute_confidence(
            interactions, corrections, insights
        )

        return {
            "reflection_id": reflection_id,
            "timestamp": ts,
            "insights": insights,
            "behavior_adjustments": adjustments,
            "prompt_refinements": refinements,
            "behavior_rules": [r.to_dict() for r in new_rules],
            "all_active_rules": [
                r.to_prompt_instruction()
                for r in self._behavior_rules if r.active
            ],
            "confidence_score": round(confidence, 4),
            "interactions_analyzed": len(interactions),
            "corrections_analyzed": len(corrections),
        }

    def get_active_rules(self) -> List[BehaviorRule]:
        """Return all active behavior rules."""
        return [r for r in self._behavior_rules if r.active]

    def deactivate_rule(self, rule_id: str) -> bool:
        """Deactivate a behavior rule by ID."""
        for r in self._behavior_rules:
            if r.rule_id == rule_id:
                r.active = False
                if self._bank is not None:
                    try:
                        self._bank.deactivate_behavior_rule(rule_id)
                    except Exception:
                        pass
                return True
        return False

    # ------------------------------------------------------------------
    # Insight extraction
    # ------------------------------------------------------------------

    def _extract_insights(
        self,
        interactions: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
    ) -> List[str]:
        """Derive high-level insights from raw data."""
        insights: List[str] = []

        if not interactions:
            return ["Insufficient interaction data for reflection."]

        # 1. Sentiment trend
        sentiments = [
            ix.get("sentiment", {}).get("score", 0.0)
            if isinstance(ix.get("sentiment"), dict)
            else ix.get("feedback", 0.0)
            for ix in interactions
        ]
        sentiments = [s for s in sentiments if s is not None]
        if sentiments:
            avg = sum(sentiments) / len(sentiments)
            if avg > 0.3:
                insights.append(
                    "Overall user sentiment is positive. Current approach "
                    "is working well."
                )
            elif avg < -0.2:
                insights.append(
                    "User sentiment is trending negative. Review recent "
                    "responses for tone or accuracy issues."
                )
            else:
                insights.append("User sentiment is neutral/mixed.")

        # 2. Correction patterns
        if corrections:
            categories = Counter(c.get("category", "unknown") for c in corrections)
            top = categories.most_common(3)
            if top:
                cats = ", ".join(f"{cat} ({cnt})" for cat, cnt in top)
                insights.append(
                    f"Most common correction categories: {cats}. "
                    f"Focus improvement efforts here."
                )

        # 3. Response length analysis
        lengths = [
            len(ix.get("ai_response", "").split()) for ix in interactions
        ]
        if lengths:
            avg_len = sum(lengths) / len(lengths)
            feedbacks = [
                ix.get("feedback") for ix in interactions
                if ix.get("feedback") is not None
            ]
            if feedbacks:
                short_fb = [
                    fb for ix, fb in zip(interactions, feedbacks)
                    if ix.get("feedback") is not None
                    and len(ix.get("ai_response", "").split()) < avg_len * 0.5
                ]
                long_fb = [
                    fb for ix, fb in zip(interactions, feedbacks)
                    if ix.get("feedback") is not None
                    and len(ix.get("ai_response", "").split()) > avg_len * 1.5
                ]
                # Only report if we have enough data
                if len(short_fb) >= 2 and sum(short_fb) / len(short_fb) > 0.3:
                    insights.append(
                        "Shorter responses tend to receive better feedback."
                    )
                if len(long_fb) >= 2 and sum(long_fb) / len(long_fb) > 0.3:
                    insights.append(
                        "Longer, more detailed responses are appreciated."
                    )

        # 4. Topic clustering
        topic_counts: Dict[str, int] = defaultdict(int)
        for ix in interactions:
            for word in re.findall(r"[a-z]{4,}", ix.get("user_input", "").lower()):
                if word not in _REFLECTION_STOP_WORDS:
                    topic_counts[word] += 1
        top_topics = sorted(topic_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        if top_topics:
            topics_str = ", ".join(t[0] for t in top_topics)
            insights.append(f"Recurring user topics: {topics_str}.")

        return insights

    # ------------------------------------------------------------------
    # Behaviour adjustments
    # ------------------------------------------------------------------

    def _propose_adjustments(
        self,
        interactions: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        evolution_history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Propose specific behaviour adjustments."""
        adjustments: List[Dict[str, Any]] = []
        past_types = {
            e.get("type") for e in evolution_history if isinstance(e, dict)
        }

        # Correction-driven adjustments
        if corrections:
            cat_counts = Counter(c.get("category", "unknown") for c in corrections)
            for cat, count in cat_counts.most_common(3):
                adj_type = f"reduce_{cat}_errors"
                if adj_type not in past_types or count > 3:
                    adjustments.append({
                        "type": adj_type,
                        "description": (
                            f"Reduce {cat} errors (seen {count} time(s) "
                            f"in recent window). Add explicit verification "
                            f"step for {cat}-related outputs."
                        ),
                        "priority": min(1.0, 0.3 + count * 0.15),
                    })

        # Feedback-driven adjustments
        feedbacks = [
            ix.get("feedback")
            for ix in interactions
            if ix.get("feedback") is not None
        ]
        if feedbacks:
            avg_fb = sum(feedbacks) / len(feedbacks)
            if avg_fb < -0.1:
                adjustments.append({
                    "type": "improve_response_quality",
                    "description": (
                        "Average feedback is negative. Consider being more "
                        "concise, asking clarifying questions, or verifying "
                        "assumptions before responding."
                    ),
                    "priority": 0.8,
                })
            negative_streak = 0
            for fb in reversed(feedbacks):
                if fb < 0:
                    negative_streak += 1
                else:
                    break
            if negative_streak >= 3:
                adjustments.append({
                    "type": "break_negative_streak",
                    "description": (
                        f"Last {negative_streak} interactions received "
                        f"negative feedback. Significant style shift may "
                        f"be needed."
                    ),
                    "priority": 0.95,
                })

        # Staleness detection: if no evolution has happened in a while
        if evolution_history:
            last_ts = max(
                e.get("timestamp", 0.0) for e in evolution_history
                if isinstance(e, dict)
            )
            if time.time() - last_ts > 3600:  # >1 hour since last evolution
                adjustments.append({
                    "type": "freshness_check",
                    "description": (
                        "No evolution applied recently. Consider a proactive "
                        "style refresh based on recent interactions."
                    ),
                    "priority": 0.3,
                })

        return adjustments

    # ------------------------------------------------------------------
    # Prompt refinement suggestions
    # ------------------------------------------------------------------

    def _suggest_prompt_refinements(
        self,
        interactions: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate text-level suggestions for prompt refinement."""
        refinements: List[str] = []

        if corrections:
            cats = Counter(c.get("category", "unknown") for c in corrections)
            for cat, cnt in cats.most_common(2):
                refinements.append(
                    f"Add explicit instruction to double-check {cat} "
                    f"(corrected {cnt} time(s) recently)."
                )

        # Check for over/under verbosity based on feedback
        feedbacks_with_len = [
            (ix.get("feedback", 0.0), len(ix.get("ai_response", "").split()))
            for ix in interactions
            if ix.get("feedback") is not None
        ]
        if len(feedbacks_with_len) >= 3:
            short_good = sum(
                1 for fb, ln in feedbacks_with_len if fb > 0.3 and ln < 50
            )
            long_good = sum(
                1 for fb, ln in feedbacks_with_len if fb > 0.3 and ln > 100
            )
            if short_good > long_good and short_good >= 2:
                refinements.append(
                    "Add instruction: 'Keep responses concise and to the point.'"
                )
            elif long_good > short_good and long_good >= 2:
                refinements.append(
                    "Add instruction: 'Provide thorough, detailed responses.'"
                )

        return refinements

    # ------------------------------------------------------------------
    # Confidence scoring
    # ------------------------------------------------------------------

    def _compute_confidence(
        self,
        interactions: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        insights: List[str],
    ) -> float:
        """How confident we are in this reflection's output.

        Higher when we have more data and clearer signal.
        """
        # Base confidence from data volume
        n = len(interactions)
        if n < self._MIN_INTERACTIONS:
            volume_score = 0.2
        elif n < 10:
            volume_score = 0.5
        elif n < 30:
            volume_score = 0.7
        else:
            volume_score = 0.9

        # Signal clarity: do feedbacks agree?
        feedbacks = [
            ix.get("feedback")
            for ix in interactions
            if ix.get("feedback") is not None
        ]
        if feedbacks and len(feedbacks) >= 3:
            mean_fb = sum(feedbacks) / len(feedbacks)
            variance = sum((f - mean_fb) ** 2 for f in feedbacks) / len(feedbacks)
            # Low variance = clear signal = high confidence
            clarity_score = max(0.3, 1.0 - variance)
        else:
            clarity_score = 0.4

        # Insight count contribution (more insights = more actionable)
        insight_score = min(1.0, len(insights) * 0.2)

        return 0.4 * volume_score + 0.35 * clarity_score + 0.25 * insight_score


# ---------------------------------------------------------------------------
# BehaviorEvolver
# ---------------------------------------------------------------------------

class BehaviorEvolver:
    """Proposes, applies, tracks, and can roll back behaviour evolutions.

    An *evolution* is a concrete, named change to the AI's operating
    parameters.  Each evolution gets a unique ID and is tracked with
    full before/after state for rollback capability.

    Usage::

        evolver = BehaviorEvolver()
        proposal = evolver.propose_evolution(reflection_results)
        evolver.apply_evolution(proposal, reasoning_bank=my_bank)
        evolver.rollback_evolution(proposal["evolution_id"])
    """

    def __init__(self) -> None:
        self._history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def propose_evolution(
        self, reflection_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a concrete evolution proposal from reflection output.

        Parameters
        ----------
        reflection_results : dict
            Output of ``ReflectionCycle.reflect()``.

        Returns
        -------
        dict
            evolution_id  : str
            changes       : list[dict]  (parameter, old_value, new_value, reason)
            priority      : float (0-1)
            source_reflection : str  (reflection_id)
            status        : "proposed"
            timestamp     : float
        """
        evolution_id = _short_uuid()
        changes: List[Dict[str, Any]] = []

        adjustments = reflection_results.get("behavior_adjustments", [])
        refinements = reflection_results.get("prompt_refinements", [])

        # Convert adjustments to parameter changes
        for adj in adjustments:
            change = self._adjustment_to_change(adj)
            if change:
                changes.append(change)

        # Convert prompt refinements to changes
        for ref in refinements:
            changes.append({
                "parameter": "system_prompt",
                "action": "append_instruction",
                "new_value": ref,
                "reason": "Prompt refinement from reflection cycle.",
            })

        # Overall priority is the max of individual adjustment priorities
        priority = max(
            (adj.get("priority", 0.5) for adj in adjustments),
            default=0.5,
        )

        return {
            "evolution_id": evolution_id,
            "changes": changes,
            "priority": round(priority, 4),
            "source_reflection": reflection_results.get("reflection_id", "unknown"),
            "status": "proposed",
            "timestamp": time.time(),
        }

    def apply_evolution(
        self,
        proposal: Dict[str, Any],
        reasoning_bank: Any = None,
    ) -> bool:
        """Apply an approved evolution proposal.

        Parameters
        ----------
        proposal : dict
            The proposal from ``propose_evolution()``.
        reasoning_bank : object, optional
            A reasoning/memory bank that stores evolution metadata.
            If provided, its ``store_evolution(data)`` method is called
            (duck-typed).

        Returns
        -------
        bool
            ``True`` if applied successfully.
        """
        if not proposal.get("changes"):
            return False

        applied_record = {
            **proposal,
            "status": "applied",
            "applied_at": time.time(),
        }
        self._history.append(applied_record)

        # Persist to reasoning bank if available
        if reasoning_bank is not None and hasattr(reasoning_bank, "store_evolution"):
            try:
                reasoning_bank.store_evolution(applied_record)
            except Exception:
                pass  # non-critical persistence failure

        return True

    def get_evolution_history(self) -> List[Dict[str, Any]]:
        """Return all evolution records (proposed, applied, rolled-back)."""
        return list(self._history)

    def rollback_evolution(self, evolution_id: str) -> bool:
        """Roll back an applied evolution by ID.

        Marks the evolution as ``rolled_back`` and returns ``True`` if
        the evolution was found and was in ``applied`` status.
        """
        for record in self._history:
            if record.get("evolution_id") == evolution_id:
                if record.get("status") == "applied":
                    record["status"] = "rolled_back"
                    record["rolled_back_at"] = time.time()
                    return True
                return False  # not in applied state
        return False  # not found

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _adjustment_to_change(
        adjustment: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Convert a behaviour adjustment to a parameter change dict."""
        adj_type = adjustment.get("type", "")
        description = adjustment.get("description", "")

        if "response_quality" in adj_type or "negative_streak" in adj_type:
            return {
                "parameter": "response_strategy",
                "action": "modify",
                "new_value": "ask_clarifying_questions_first",
                "reason": description,
            }
        if "errors" in adj_type:
            category = adj_type.replace("reduce_", "").replace("_errors", "")
            return {
                "parameter": f"verification_{category}",
                "action": "enable",
                "new_value": True,
                "reason": description,
            }
        if "freshness" in adj_type:
            return {
                "parameter": "style_refresh",
                "action": "trigger",
                "new_value": time.time(),
                "reason": description,
            }
        return None


# ---------------------------------------------------------------------------
# PromptRefiner
# ---------------------------------------------------------------------------

class PromptRefiner:
    """Iteratively refines the system prompt based on accumulated learnings.

    Maintains a history of all refinements so prompt evolution can be
    traced and audited.

    Usage::

        refiner = PromptRefiner()
        new_prompt = refiner.refine_system_prompt(
            base_prompt="You are a helpful assistant.",
            learnings=["Be more concise", "Verify facts before stating them"],
            preferences={"formality": {"value": "casual"}},
        )
    """

    def __init__(self) -> None:
        self._history: List[Dict[str, Any]] = []

    def refine_system_prompt(
        self,
        base_prompt: str,
        learnings: List[str],
        preferences: Dict[str, Any],
    ) -> str:
        """Produce a refined system prompt.

        Parameters
        ----------
        base_prompt : str
            The current system prompt text.
        learnings : list[str]
            Specific instructions to weave into the prompt.
        preferences : dict
            User preference profile (from ``PreferenceTracker.get_profile()``).

        Returns
        -------
        str
            The refined system prompt.
        """
        sections: List[str] = [base_prompt.rstrip()]

        # --- Learnings section ---
        if learnings:
            learning_lines = "\n".join(f"- {l}" for l in learnings if l.strip())
            if learning_lines:
                sections.append(
                    "\n\n## Learned Behaviours\n"
                    "Apply the following learned behaviours:\n"
                    + learning_lines
                )

        # --- Preference-driven instructions ---
        pref_instructions = self._preferences_to_instructions(preferences)
        if pref_instructions:
            sections.append(
                "\n\n## User Preferences\n" + pref_instructions
            )

        refined = "\n".join(sections)

        # Record history
        self._history.append({
            "refinement_id": _short_uuid(),
            "timestamp": time.time(),
            "base_prompt_hash": _text_hash(base_prompt),
            "refined_prompt_hash": _text_hash(refined),
            "learnings_applied": len(learnings),
            "preferences_applied": len(pref_instructions.splitlines()) if pref_instructions else 0,
        })

        return refined

    def get_refinement_history(self) -> List[Dict[str, Any]]:
        """Return the full history of prompt refinements."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _preferences_to_instructions(
        preferences: Dict[str, Any],
    ) -> str:
        """Convert a preference profile dict into prompt-ready instructions."""
        lines: List[str] = []

        formality = _pref_value(preferences, "formality")
        if formality == "casual":
            lines.append(
                "- Use a casual, friendly tone. Contractions are fine."
            )
        elif formality == "formal":
            lines.append(
                "- Maintain a formal, professional tone throughout."
            )

        length = _pref_value(preferences, "response_length")
        if length == "short":
            lines.append(
                "- Keep responses concise (under 80 words when possible)."
            )
        elif length == "long":
            lines.append(
                "- Provide thorough, detailed responses with examples."
            )

        humor = _pref_value(preferences, "humor_appreciation")
        if humor == "high":
            lines.append(
                "- Feel free to include light humour and wordplay."
            )
        elif humor == "low":
            lines.append("- Stay serious and factual. Avoid humour.")

        topics = _pref_value(preferences, "topic_interests")
        if isinstance(topics, list) and topics:
            top = ", ".join(topics[:5])
            lines.append(
                f"- The user is interested in: {top}. "
                f"Reference these when relevant."
            )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ReflectionScheduler
# ---------------------------------------------------------------------------

class ReflectionScheduler:
    """Decides when the next reflection cycle should occur.

    Triggers reflection when either:
      - ``interaction_count`` reaches the configured threshold (default 10), or
      - At least ``interval_seconds`` (default 1800 = 30 min) have elapsed
        since the last reflection.

    Usage::

        sched = ReflectionScheduler()
        if sched.should_reflect(last_reflection_ts, interaction_count):
            run_reflection()
            new_ts = sched.schedule_reflection()
    """

    def __init__(
        self,
        *,
        interaction_threshold: int = 10,
        interval_seconds: float = 1800.0,
    ) -> None:
        self._interaction_threshold = max(1, interaction_threshold)
        self._interval = max(60.0, interval_seconds)
        self._last_reflection_ts: float = 0.0

    def should_reflect(
        self,
        last_reflection_ts: float,
        interaction_count: int,
    ) -> bool:
        """Return ``True`` if a reflection cycle should run now.

        Parameters
        ----------
        last_reflection_ts : float
            Unix timestamp of the last completed reflection.
        interaction_count : int
            Number of interactions since the last reflection.
        """
        now = time.time()

        # Interaction threshold reached
        if interaction_count >= self._interaction_threshold:
            return True

        # Time-based trigger
        if last_reflection_ts <= 0:
            # Never reflected: trigger after half the interval
            return now > (self._interval / 2)

        elapsed = now - last_reflection_ts
        if elapsed >= self._interval:
            return True

        return False

    def schedule_reflection(self) -> float:
        """Record that a reflection just completed and return the timestamp
        at which the *next* reflection should occur (at the latest).
        """
        now = time.time()
        self._last_reflection_ts = now
        return now + self._interval


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------

def _short_uuid() -> str:
    """Generate a short unique identifier."""
    return uuid.uuid4().hex[:12]


def _text_hash(text: str) -> str:
    """Produce a short SHA-256 hash of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _pref_value(profile: Dict[str, Any], key: str) -> Any:
    """Safely extract a preference value from a profile dict.

    Handles both ``{"key": {"value": X}}`` and ``{"key": X}`` layouts.
    """
    entry = profile.get(key)
    if entry is None:
        return None
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


_REFLECTION_STOP_WORDS = {
    "this", "that", "with", "from", "have", "been", "were", "they",
    "their", "what", "when", "where", "which", "there", "about",
    "would", "could", "should", "will", "just", "more", "some",
    "than", "then", "them", "also", "into", "your", "other",
    "only", "does", "very", "much", "most", "such", "here",
    "each", "like", "make", "made", "over", "after", "before",
    "being", "these", "those", "think", "know", "want", "because",
    "really", "still", "even", "well", "back", "going", "doing",
    "using", "thing", "things", "something", "anything", "everything",
}
