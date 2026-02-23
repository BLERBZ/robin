"""
Kait Sidekick Resonance Engine - User Resonance Tracking

Tracks sentiment, preferences, and personalizes responses so the AI
sidekick can adapt its behaviour to the individual user over time.

Components:
  - SentimentAnalyzer: Rule-based sentiment scoring (no external deps)
  - PreferenceTracker: Persistent preference recording and inference
  - ResonanceEngine: Orchestrates sentiment + preferences into a single
    resonance score with actionable adaptation suggestions

All state is held in-memory with dict-serialisable snapshots so callers
can persist however they choose (SQLite, JSON file, etc.).
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Word lists for rule-based sentiment
# ---------------------------------------------------------------------------

_POSITIVE_WORDS: Set[str] = {
    "good", "great", "awesome", "excellent", "amazing", "wonderful",
    "fantastic", "love", "like", "enjoy", "happy", "pleased", "glad",
    "brilliant", "perfect", "beautiful", "nice", "cool", "superb",
    "outstanding", "delightful", "impressive", "helpful", "thanks",
    "thank", "appreciate", "bravo", "solid", "yes", "right", "correct",
    "agree", "fun", "exciting", "interesting", "useful", "valuable",
    "clear", "elegant", "smooth", "fast", "reliable", "intuitive",
    "creative", "insightful", "thoughtful", "kind", "generous",
    "remarkable", "exceptional", "fabulous", "terrific", "magnificent",
    "splendid", "marvelous", "phenomenal", "stellar", "glorious",
}

_NEGATIVE_WORDS: Set[str] = {
    "bad", "terrible", "awful", "horrible", "poor", "hate", "dislike",
    "annoying", "frustrated", "angry", "sad", "disappointing",
    "disappointed", "wrong", "broken", "ugly", "slow", "confusing",
    "confused", "boring", "useless", "stupid", "dumb", "worst",
    "fail", "failed", "failure", "error", "bug", "crash", "sucks",
    "painful", "irritating", "problem", "issue", "difficult",
    "hard", "impossible", "ridiculous", "absurd", "lousy", "mediocre",
    "weak", "flawed", "clunky", "bloated", "messy", "unclear",
    "pointless", "wasteful", "dreadful", "atrocious", "abysmal",
    "pathetic", "wretched", "miserable", "horrendous", "appalling",
}

_INTENSIFIERS: Dict[str, float] = {
    "very": 1.5,
    "really": 1.5,
    "extremely": 2.0,
    "incredibly": 2.0,
    "absolutely": 2.0,
    "totally": 1.8,
    "completely": 1.8,
    "utterly": 2.0,
    "highly": 1.5,
    "super": 1.6,
    "so": 1.3,
    "quite": 1.2,
    "pretty": 1.2,
    "somewhat": 0.7,
    "slightly": 0.5,
    "barely": 0.4,
    "hardly": 0.4,
    "a bit": 0.6,
    "a little": 0.6,
}

_NEGATION_WORDS: Set[str] = {
    "not", "no", "never", "neither", "nobody", "nothing", "nowhere",
    "nor", "cannot", "can't", "won't", "don't", "doesn't", "didn't",
    "isn't", "aren't", "wasn't", "weren't", "shouldn't", "wouldn't",
    "couldn't", "hasn't", "haven't", "hadn't",
}

_NEGATION_CONTRACTIONS: Dict[str, str] = {
    "can't": "cannot",
    "won't": "will not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "shouldn't": "should not",
    "wouldn't": "would not",
    "couldn't": "could not",
    "hasn't": "has not",
    "haven't": "have not",
    "hadn't": "had not",
}


# ---------------------------------------------------------------------------
# SentimentAnalyzer
# ---------------------------------------------------------------------------

class SentimentAnalyzer:
    """Rule-based sentiment analyser using curated word lists.

    No external dependencies.  Handles:
    - Positive / negative keyword matching
    - Intensity modifiers (very, extremely, ...)
    - Negation ("not happy" flips polarity)

    Usage::

        sa = SentimentAnalyzer()
        result = sa.analyze("I really love this new feature!")
        # => {"score": 0.75, "label": "positive", "confidence": 0.82, "keywords": ["love"]}
    """

    def __init__(
        self,
        *,
        positive_words: Optional[Set[str]] = None,
        negative_words: Optional[Set[str]] = None,
        intensifiers: Optional[Dict[str, float]] = None,
        negation_words: Optional[Set[str]] = None,
    ) -> None:
        self._positive = positive_words or _POSITIVE_WORDS
        self._negative = negative_words or _NEGATIVE_WORDS
        self._intensifiers = intensifiers or _INTENSIFIERS
        self._negation = negation_words or _NEGATION_WORDS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, text: str) -> Dict[str, Any]:
        """Analyse *text* and return a sentiment dict.

        Returns
        -------
        dict
            score      : float in [-1.0, 1.0]
            label      : "positive" | "negative" | "neutral"
            confidence : float in [0.0, 1.0]
            keywords   : list[str] of matched sentiment words
        """
        if not text or not text.strip():
            return {
                "score": 0.0,
                "label": "neutral",
                "confidence": 1.0,
                "keywords": [],
            }

        tokens = self._tokenize(text)
        pos_score, neg_score, keywords = self._score_tokens(tokens)

        raw = pos_score - neg_score
        total_hits = pos_score + neg_score
        # Normalise to [-1, 1] using a soft sigmoid-style squash
        score = self._squash(raw)

        if score > 0.05:
            label = "positive"
        elif score < -0.05:
            label = "negative"
        else:
            label = "neutral"

        # Confidence rises with more evidence; fewer hits = lower confidence
        if total_hits == 0:
            confidence = 0.5  # no signal, we just guess neutral
        else:
            confidence = min(1.0, 0.5 + total_hits * 0.1)

        return {
            "score": round(score, 4),
            "label": label,
            "confidence": round(confidence, 4),
            "keywords": sorted(set(keywords)),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowercase and split on non-alpha boundaries, preserving contractions."""
        cleaned = text.lower()
        # Keep apostrophes for contractions, split everything else
        tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", cleaned)
        return tokens

    def _score_tokens(
        self, tokens: List[str]
    ) -> Tuple[float, float, List[str]]:
        """Walk tokens, accumulate positive/negative scores.

        Returns (pos_total, neg_total, matched_keywords).
        """
        pos_total = 0.0
        neg_total = 0.0
        keywords: List[str] = []

        negation_window = 0  # tokens remaining under negation influence
        intensity_mult = 1.0

        for token in tokens:
            # Track negation context (next 2 tokens after a negation)
            if token in self._negation or token in _NEGATION_CONTRACTIONS:
                negation_window = 3  # affects the next few tokens
                continue

            # Track intensity modifier
            if token in self._intensifiers:
                intensity_mult = self._intensifiers[token]
                continue

            # Sentiment match
            is_positive = token in self._positive
            is_negative = token in self._negative

            if is_positive or is_negative:
                base_weight = 1.0 * intensity_mult
                negated = negation_window > 0

                if is_positive:
                    if negated:
                        neg_total += base_weight * 0.75  # "not good" is mildly negative
                    else:
                        pos_total += base_weight
                elif is_negative:
                    if negated:
                        pos_total += base_weight * 0.5  # "not bad" is mildly positive
                    else:
                        neg_total += base_weight

                keywords.append(token)
                intensity_mult = 1.0  # reset after use

            # Decay negation window
            if negation_window > 0:
                negation_window -= 1

        return pos_total, neg_total, keywords

    @staticmethod
    def _squash(raw: float, k: float = 2.0) -> float:
        """Squash *raw* into [-1, 1] using tanh-style curve.

        ``k`` controls sensitivity; smaller = more gradual.
        """
        import math
        return math.tanh(raw / k)


# ---------------------------------------------------------------------------
# PreferenceTracker
# ---------------------------------------------------------------------------

@dataclass
class _Preference:
    """Internal preference record."""
    value: Any
    confidence: float
    updated_at: float
    observation_count: int = 1


class PreferenceTracker:
    """Records and infers user preferences from interaction data.

    Preferences are key-value pairs with an associated confidence score
    (0.0 - 1.0).  Confidence increases with repeated observations and
    decays slightly over time to allow preference drift.

    Usage::

        pt = PreferenceTracker()
        pt.record_preference("response_length", "concise", confidence=0.8)
        pt.get_preference("response_length")
        # => {"value": "concise", "confidence": 0.8, ...}
    """

    def __init__(self) -> None:
        self._prefs: Dict[str, _Preference] = {}
        self._interaction_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_preference(
        self, key: str, value: Any, confidence: float = 0.7
    ) -> None:
        """Store or update a preference.

        If the same key already exists, the new confidence is blended
        with the old one (higher of the two wins, with a small boost
        for repeated agreement).
        """
        confidence = max(0.0, min(1.0, confidence))
        existing = self._prefs.get(key)
        if existing is not None:
            if existing.value == value:
                # Reinforce: small confidence boost, capped at 1.0
                blended = min(1.0, max(existing.confidence, confidence) + 0.05)
                existing.confidence = blended
                existing.observation_count += 1
                existing.updated_at = time.time()
            else:
                # Value changed: replace, but dampen confidence
                self._prefs[key] = _Preference(
                    value=value,
                    confidence=confidence * 0.9,
                    updated_at=time.time(),
                )
        else:
            self._prefs[key] = _Preference(
                value=value,
                confidence=confidence,
                updated_at=time.time(),
            )

    def get_preference(self, key: str) -> Optional[Dict[str, Any]]:
        """Return a single preference dict, or ``None`` if unknown."""
        pref = self._prefs.get(key)
        if pref is None:
            return None
        return {
            "key": key,
            "value": pref.value,
            "confidence": round(pref.confidence, 4),
            "observation_count": pref.observation_count,
            "updated_at": pref.updated_at,
        }

    def infer_preferences(
        self, interactions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyse a batch of interactions and infer preferences.

        Each interaction dict should have at minimum:
            - ``user_input``  (str)
            - ``ai_response`` (str)
            - ``feedback``    (float, optional, -1 to 1)

        Infers:
            - Preferred response length (short / medium / long)
            - Formality level (casual / balanced / formal)
            - Topic interests
        """
        if not interactions:
            return {}

        self._interaction_log.extend(interactions)

        lengths: List[int] = []
        positive_lengths: List[int] = []
        topics: Dict[str, int] = defaultdict(int)
        formality_signals: List[float] = []

        for ix in interactions:
            ai_resp = ix.get("ai_response", "")
            user_inp = ix.get("user_input", "")
            feedback = ix.get("feedback")

            resp_len = len(ai_resp.split())
            lengths.append(resp_len)

            if feedback is not None and feedback > 0.3:
                positive_lengths.append(resp_len)

            # Topic extraction: pull out nouns / significant words
            for word in re.findall(r"[a-z]{4,}", user_inp.lower()):
                if word not in _STOP_WORDS:
                    topics[word] += 1

            # Formality heuristic: contractions + slang = casual
            formality_signals.append(self._estimate_formality(user_inp))

        # --- Infer preferred length ---
        ref_lengths = positive_lengths if positive_lengths else lengths
        avg_len = sum(ref_lengths) / len(ref_lengths) if ref_lengths else 50
        if avg_len < 30:
            length_pref = "short"
        elif avg_len < 100:
            length_pref = "medium"
        else:
            length_pref = "long"
        self.record_preference("response_length", length_pref, confidence=0.6)

        # --- Infer formality ---
        if formality_signals:
            avg_formality = sum(formality_signals) / len(formality_signals)
            if avg_formality < 0.35:
                formality_pref = "casual"
            elif avg_formality < 0.65:
                formality_pref = "balanced"
            else:
                formality_pref = "formal"
            self.record_preference("formality", formality_pref, confidence=0.55)

        # --- Infer topic interests ---
        top_topics = sorted(topics.items(), key=lambda kv: kv[1], reverse=True)[:10]
        if top_topics:
            self.record_preference(
                "topic_interests",
                [t[0] for t in top_topics],
                confidence=0.5,
            )

        return {
            "inferred_length": length_pref,
            "inferred_formality": formality_pref if formality_signals else "balanced",
            "top_topics": [t[0] for t in top_topics],
            "interactions_analyzed": len(interactions),
        }

    def get_profile(self) -> Dict[str, Any]:
        """Return the full user preference profile."""
        return {
            key: {
                "value": p.value,
                "confidence": round(p.confidence, 4),
                "observation_count": p.observation_count,
                "updated_at": p.updated_at,
            }
            for key, p in self._prefs.items()
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_formality(text: str) -> float:
        """Return a 0-1 formality estimate.  0 = very casual, 1 = very formal."""
        indicators_casual = [
            r"\b(lol|haha|omg|btw|imo|idk|tbh|ngl)\b",
            r"!!+",
            r"\b(gonna|wanna|gotta|kinda|sorta)\b",
        ]
        indicators_formal = [
            r"\b(therefore|furthermore|moreover|consequently|hereby)\b",
            r"\b(please|kindly|regarding|concerning)\b",
        ]
        text_l = text.lower()
        casual_hits = sum(
            1 for pat in indicators_casual if re.search(pat, text_l)
        )
        formal_hits = sum(
            1 for pat in indicators_formal if re.search(pat, text_l)
        )
        total = casual_hits + formal_hits
        if total == 0:
            return 0.5
        return formal_hits / total


# Minimal stop words for topic extraction (no NLTK dependency)
_STOP_WORDS: Set[str] = {
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


# ---------------------------------------------------------------------------
# ResonanceEngine
# ---------------------------------------------------------------------------

class ResonanceEngine:
    """Orchestrates sentiment analysis and preference tracking to produce
    a single *resonance score* that measures how well the AI aligns with
    the user.

    The resonance score (0.0 - 1.0) aggregates:
      - Sentiment trend of recent interactions
      - Explicit feedback when provided
      - Consistency of preference alignment
      - Response-length match

    Usage::

        engine = ResonanceEngine()
        result = engine.process_interaction(
            user_input="That was really helpful, thanks!",
            ai_response="Glad I could help!",
        )
        engine.get_resonance_score()
        engine.get_adaptation_suggestions()
    """

    # Number of recent interactions to keep for sliding-window analysis
    _WINDOW_SIZE: int = 50

    def __init__(
        self,
        *,
        sentiment_analyzer: Optional[SentimentAnalyzer] = None,
        preference_tracker: Optional[PreferenceTracker] = None,
    ) -> None:
        self.sentiment = sentiment_analyzer or SentimentAnalyzer()
        self.preferences = preference_tracker or PreferenceTracker()

        # Rolling history
        self._interactions: List[Dict[str, Any]] = []
        self._sentiment_scores: List[float] = []
        self._feedback_scores: List[float] = []

        # Tracking dimensions
        self._response_lengths: List[int] = []
        self._formality_samples: List[float] = []
        self._humor_hits: int = 0
        self._humor_misses: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_interaction(
        self,
        user_input: str,
        ai_response: str,
        feedback: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Analyse a single interaction and update internal state.

        Parameters
        ----------
        user_input : str
            What the user said.
        ai_response : str
            What the AI responded.
        feedback : float, optional
            Explicit feedback (-1.0 to 1.0).  ``None`` = no feedback.

        Returns
        -------
        dict
            sentiment   : dict from SentimentAnalyzer
            resonance   : float (current overall resonance)
            preferences : dict snapshot
        """
        sentiment_result = self.sentiment.analyze(user_input)
        self._sentiment_scores.append(sentiment_result["score"])

        if feedback is not None:
            clamped = max(-1.0, min(1.0, feedback))
            self._feedback_scores.append(clamped)

        # Track response length
        resp_word_count = len(ai_response.split())
        self._response_lengths.append(resp_word_count)

        # Detect humor signals in AI response
        self._detect_humor_signal(user_input, ai_response, feedback)

        # Formality of user input
        formality = PreferenceTracker._estimate_formality(user_input)
        self._formality_samples.append(formality)

        # Build interaction record
        record: Dict[str, Any] = {
            "user_input": user_input,
            "ai_response": ai_response,
            "feedback": feedback,
            "sentiment": sentiment_result,
            "timestamp": time.time(),
        }
        self._interactions.append(record)

        # Trim to window
        if len(self._interactions) > self._WINDOW_SIZE:
            self._interactions = self._interactions[-self._WINDOW_SIZE:]
            self._sentiment_scores = self._sentiment_scores[-self._WINDOW_SIZE:]
            self._feedback_scores = self._feedback_scores[-self._WINDOW_SIZE:]
            self._response_lengths = self._response_lengths[-self._WINDOW_SIZE:]
            self._formality_samples = self._formality_samples[-self._WINDOW_SIZE:]

        # Periodically infer preferences (every 5 interactions)
        if len(self._interactions) % 5 == 0:
            self.preferences.infer_preferences(self._interactions[-5:])

        # Update tracked preferences explicitly
        self._update_tracked_preferences()

        resonance = self.get_resonance_score()
        return {
            "sentiment": sentiment_result,
            "resonance": round(resonance, 4),
            "preferences": self.preferences.get_profile(),
        }

    def get_resonance_score(self) -> float:
        """Compute overall resonance (0.0 - 1.0).

        Combines:
          40% - Sentiment trend (mapped from [-1,1] to [0,1])
          30% - Explicit feedback trend (mapped from [-1,1] to [0,1])
          20% - Preference alignment (how well we match inferred prefs)
          10% - Engagement signal (interaction count momentum)

        When no feedback is available, sentiment weight increases.
        """
        if not self._interactions:
            return 0.5  # neutral baseline

        # --- Sentiment component ---
        recent_sentiments = self._sentiment_scores[-20:]
        avg_sentiment = sum(recent_sentiments) / len(recent_sentiments)
        sentiment_component = (avg_sentiment + 1.0) / 2.0  # map [-1,1] -> [0,1]

        # --- Feedback component ---
        if self._feedback_scores:
            recent_feedback = self._feedback_scores[-20:]
            avg_feedback = sum(recent_feedback) / len(recent_feedback)
            feedback_component = (avg_feedback + 1.0) / 2.0
            has_feedback = True
        else:
            feedback_component = 0.5
            has_feedback = False

        # --- Preference alignment ---
        alignment = self._compute_preference_alignment()

        # --- Engagement momentum ---
        engagement = min(1.0, len(self._interactions) / 20.0)

        # Weight distribution
        if has_feedback:
            score = (
                0.40 * sentiment_component
                + 0.30 * feedback_component
                + 0.20 * alignment
                + 0.10 * engagement
            )
        else:
            # No explicit feedback: lean more on sentiment
            score = (
                0.55 * sentiment_component
                + 0.25 * alignment
                + 0.20 * engagement
            )

        return max(0.0, min(1.0, score))

    def get_adaptation_suggestions(self) -> List[str]:
        """Return actionable suggestions for improving resonance."""
        suggestions: List[str] = []
        profile = self.preferences.get_profile()

        # --- Response length ---
        length_pref = profile.get("response_length", {}).get("value")
        if length_pref and self._response_lengths:
            avg_len = sum(self._response_lengths[-10:]) / len(
                self._response_lengths[-10:]
            )
            if length_pref == "short" and avg_len > 80:
                suggestions.append(
                    "User prefers shorter responses. Aim for <80 words."
                )
            elif length_pref == "long" and avg_len < 60:
                suggestions.append(
                    "User prefers detailed responses. Consider expanding explanations."
                )

        # --- Formality ---
        formality_pref = profile.get("formality", {}).get("value")
        if formality_pref == "casual":
            suggestions.append(
                "User communicates casually. Match their tone with "
                "contractions and relaxed language."
            )
        elif formality_pref == "formal":
            suggestions.append(
                "User prefers formal communication. Avoid slang and "
                "maintain professional tone."
            )

        # --- Humor ---
        humor_pref = profile.get("humor_appreciation", {}).get("value")
        if humor_pref == "low":
            suggestions.append(
                "User doesn't respond well to humor. Stay focused and direct."
            )
        elif humor_pref == "high":
            suggestions.append(
                "User appreciates humor. Feel free to add light-hearted "
                "touches to responses."
            )

        # --- Sentiment trend ---
        if len(self._sentiment_scores) >= 5:
            recent = self._sentiment_scores[-5:]
            trend = sum(recent) / len(recent)
            if trend < -0.2:
                suggestions.append(
                    "Recent sentiment is declining. Consider asking the user "
                    "if they need help with something specific."
                )

        # --- Topic interests ---
        topics = profile.get("topic_interests", {}).get("value")
        if topics and isinstance(topics, list) and len(topics) >= 3:
            top3 = ", ".join(topics[:3])
            suggestions.append(
                f"User shows interest in: {top3}. Proactively reference "
                f"these topics when relevant."
            )

        if not suggestions:
            suggestions.append(
                "Resonance is healthy. Continue current interaction style."
            )

        return suggestions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_humor_signal(
        self,
        user_input: str,
        ai_response: str,
        feedback: Optional[float],
    ) -> None:
        """Detect whether humorous elements in the AI response landed."""
        humor_patterns = re.compile(
            r"(😂|😄|😆|🤣|lol|haha|😁|:D|:\)|joke|pun)", re.IGNORECASE
        )
        ai_has_humor = bool(humor_patterns.search(ai_response))
        if not ai_has_humor:
            return

        # Check if user reacted positively
        user_laughed = bool(humor_patterns.search(user_input))
        positive_feedback = feedback is not None and feedback > 0.3

        if user_laughed or positive_feedback:
            self._humor_hits += 1
        else:
            self._humor_misses += 1

    def _update_tracked_preferences(self) -> None:
        """Update derived preferences from accumulated signals."""
        # Humor appreciation
        total_humor = self._humor_hits + self._humor_misses
        if total_humor >= 3:
            ratio = self._humor_hits / total_humor
            if ratio > 0.6:
                level = "high"
            elif ratio < 0.3:
                level = "low"
            else:
                level = "moderate"
            self.preferences.record_preference(
                "humor_appreciation", level, confidence=min(0.9, 0.4 + total_humor * 0.05)
            )

        # Formality from samples
        if len(self._formality_samples) >= 3:
            avg_f = sum(self._formality_samples[-10:]) / len(
                self._formality_samples[-10:]
            )
            if avg_f < 0.35:
                self.preferences.record_preference("formality", "casual", confidence=0.6)
            elif avg_f > 0.65:
                self.preferences.record_preference("formality", "formal", confidence=0.6)
            else:
                self.preferences.record_preference("formality", "balanced", confidence=0.5)

    def _compute_preference_alignment(self) -> float:
        """Score how well the AI's recent outputs match user preferences.

        Returns 0.0 - 1.0.
        """
        profile = self.preferences.get_profile()
        if not profile:
            return 0.5  # unknown = neutral

        alignment_scores: List[float] = []

        # Response length alignment
        length_pref = profile.get("response_length", {}).get("value")
        if length_pref and self._response_lengths:
            avg_len = sum(self._response_lengths[-10:]) / len(
                self._response_lengths[-10:]
            )
            if length_pref == "short":
                alignment_scores.append(1.0 if avg_len < 50 else max(0.2, 1.0 - avg_len / 200))
            elif length_pref == "medium":
                alignment_scores.append(1.0 if 30 <= avg_len <= 120 else 0.5)
            elif length_pref == "long":
                alignment_scores.append(min(1.0, avg_len / 100))

        # Formality alignment
        formality_pref = profile.get("formality", {}).get("value")
        if formality_pref and self._formality_samples:
            avg_f = sum(self._formality_samples[-10:]) / len(
                self._formality_samples[-10:]
            )
            if formality_pref == "casual":
                alignment_scores.append(1.0 - avg_f)
            elif formality_pref == "formal":
                alignment_scores.append(avg_f)
            else:
                alignment_scores.append(1.0 - abs(avg_f - 0.5) * 2)

        if not alignment_scores:
            return 0.5
        return sum(alignment_scores) / len(alignment_scores)
