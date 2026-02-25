"""
Archive Worker: Auto-archive and summarize old chat sessions.

Orchestrates the archival pipeline:
1. Find sessions older than threshold (default 24h)
2. Group by calendar date into batches
3. Extract intelligence (memory, learning, EIDOS episodes)
4. Generate LLM narrative summary (with template fallback)
5. Save archive record and mark interactions as archived
6. Trigger MindBridge sync
"""

import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("kait.archive")


class ArchiveWorker:
    """Orchestrates the archival of stale chat sessions."""

    def __init__(self, bank, archive_age_seconds: int = 86400):
        self.bank = bank
        self.archive_age_seconds = archive_age_seconds

    # ------------------------------------------------------------------
    # Top-level entry point (called by QTimer)
    # ------------------------------------------------------------------

    def run_archive_cycle(self) -> Dict[str, Any]:
        """Find stale sessions, group by date, archive each batch.

        Returns:
            {batches_created: int, interactions_archived: int, errors: list}
        """
        result = {"batches_created": 0, "interactions_archived": 0, "errors": []}

        try:
            sessions = self.bank.get_archivable_sessions(
                age_seconds=self.archive_age_seconds,
            )
        except Exception as exc:
            log.warning("Failed to query archivable sessions: %s", exc)
            result["errors"].append(str(exc))
            return result

        if not sessions:
            return result

        # Group sessions by calendar date (UTC)
        date_buckets: Dict[str, list] = defaultdict(list)
        for sess in sessions:
            ts = sess.get("last_ts") or sess.get("first_ts") or 0
            day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            date_buckets[day].append(sess)

        for batch_date, batch_sessions in date_buckets.items():
            try:
                count = self._archive_batch(batch_date, batch_sessions)
                result["batches_created"] += 1
                result["interactions_archived"] += count
            except Exception as exc:
                log.error("Archive batch %s failed: %s", batch_date, exc)
                result["errors"].append(f"{batch_date}: {exc}")

        return result

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def _archive_batch(self, batch_date: str, sessions: List[Dict]) -> int:
        """Process one date's sessions into an archive record.

        Returns the number of interactions archived.
        """
        # Collect all interaction IDs across sessions
        all_interactions: List[Dict[str, Any]] = []
        session_ids: List[str] = []
        for sess in sessions:
            sid = sess.get("session_id")
            if not sid:
                continue
            session_ids.append(sid)
            history = self.bank.get_interaction_history(limit=500, session_id=sid)
            all_interactions.extend(history)

        if not all_interactions:
            return 0

        interaction_ids = [i["id"] for i in all_interactions]

        # Compute basic stats
        sentiments = [i.get("sentiment_score", 0.0) or 0.0 for i in all_interactions]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        timestamps = [i.get("timestamp", 0) for i in all_interactions]
        time_start = min(timestamps) if timestamps else 0
        time_end = max(timestamps) if timestamps else 0

        # Source breakdown
        source_counts: Dict[str, int] = defaultdict(int)
        for i in all_interactions:
            source_counts[i.get("source", "gui")] += 1

        # Mood summary from most common mood
        mood_counts: Dict[str, int] = defaultdict(int)
        for i in all_interactions:
            m = i.get("mood")
            if m:
                mood_counts[m] += 1
        mood_summary = max(mood_counts, key=mood_counts.get) if mood_counts else "neutral"

        # --- Programmatic extraction ---
        memory_entries = self._extract_memory_entries(all_interactions)
        learning_records = self._extract_learning_records(all_interactions)
        eidos_episode_id = self._create_eidos_episode(batch_date, all_interactions)

        # --- LLM narrative ---
        programmatic_data = {
            "memory_entries": memory_entries,
            "learning_records": learning_records,
            "eidos_episode_id": eidos_episode_id,
        }
        narrative_result = self._generate_narrative(
            all_interactions, programmatic_data, batch_date, session_ids,
        )

        status = "complete" if narrative_result.get("llm_used") else "partial"

        # --- Save archive ---
        archive_data = {
            "archive_id": uuid.uuid4().hex[:16],
            "batch_label": batch_date,
            "session_ids": session_ids,
            "interaction_ids": interaction_ids,
            "interaction_count": len(interaction_ids),
            "time_range_start": time_start,
            "time_range_end": time_end,
            "memory_entries": memory_entries,
            "learning_records": learning_records,
            "eidos_episode_id": eidos_episode_id,
            "distillation_ids": [],
            "mind_sync_status": "pending",
            "narrative_summary": narrative_result.get("narrative", ""),
            "topics": narrative_result.get("topics", []),
            "mood_summary": narrative_result.get("mood_label", mood_summary),
            "avg_sentiment": round(avg_sentiment, 4),
            "source_breakdown": dict(source_counts),
            "status": status,
        }

        self.bank.save_archive(archive_data)
        archived_count = self.bank.mark_interactions_archived(interaction_ids)

        # --- MindBridge sync (best-effort) ---
        self._trigger_mind_sync(archive_data)

        return archived_count

    # ------------------------------------------------------------------
    # Programmatic extraction
    # ------------------------------------------------------------------

    def _extract_memory_entries(self, interactions: List[Dict]) -> List[Dict[str, Any]]:
        """Store high-signal interactions as memories."""
        entries: List[Dict[str, Any]] = []
        try:
            from lib.memory_banks import store_memory
        except ImportError:
            log.debug("memory_banks not available, skipping memory extraction")
            return entries

        preference_keywords = {
            "prefer", "always", "never", "like", "hate", "want", "please",
            "don't", "stop", "use", "favorite",
        }

        for interaction in interactions:
            sentiment = abs(interaction.get("sentiment_score", 0) or 0)
            text = interaction.get("user_input", "")
            text_lower = text.lower()
            has_preference = any(kw in text_lower for kw in preference_keywords)

            if sentiment > 0.5 or has_preference:
                mood = interaction.get("mood", "neutral")
                category = "user_understanding" if has_preference else "reasoning"
                try:
                    entry = store_memory(
                        text=text[:300],
                        category=category,
                        session_id=interaction.get("session_id"),
                        source="archive",
                    )
                    if entry:
                        entries.append({
                            "entry_id": getattr(entry, "entry_id", str(entry)),
                            "text": text[:120],
                            "category": category,
                        })
                except Exception as exc:
                    log.debug("Memory store failed: %s", exc)

        return entries

    def _extract_learning_records(self, interactions: List[Dict]) -> List[Dict[str, str]]:
        """Detect patterns and feed them into CognitiveLearner."""
        records: List[Dict[str, str]] = []
        try:
            from lib.cognitive_learner import get_cognitive_learner
            learner = get_cognitive_learner()
        except ImportError:
            log.debug("cognitive_learner not available, skipping learning extraction")
            return records

        # Detect repeated topics (words appearing in 3+ interactions)
        word_freq: Dict[str, int] = defaultdict(int)
        for i in interactions:
            seen = set()
            for word in (i.get("user_input", "") or "").lower().split():
                cleaned = word.strip(".,!?;:\"'()[]{}").strip()
                if len(cleaned) > 3 and cleaned not in seen:
                    word_freq[cleaned] += 1
                    seen.add(cleaned)

        repeated_topics = [w for w, c in word_freq.items() if c >= 3]
        if repeated_topics:
            top_topics = sorted(repeated_topics, key=lambda w: word_freq[w], reverse=True)[:5]
            try:
                learner.learn_user_preference(
                    "frequent_topics",
                    ", ".join(top_topics),
                    f"Appeared in {len(interactions)} archived interactions",
                )
                records.append({
                    "type": "user_preference",
                    "insight": f"Frequent topics: {', '.join(top_topics)}",
                })
            except Exception as exc:
                log.debug("Learning record failed: %s", exc)

        # Detect struggle runs (3+ consecutive low-sentiment interactions)
        streak = 0
        streak_topic = ""
        for i in interactions:
            sent = i.get("sentiment_score", 0) or 0
            if sent < -0.3:
                streak += 1
                if not streak_topic:
                    streak_topic = (i.get("user_input", "") or "")[:60]
            else:
                if streak >= 3:
                    try:
                        learner.learn_struggle_area(
                            streak_topic,
                            f"Low sentiment streak of {streak} messages",
                        )
                        records.append({
                            "type": "struggle_area",
                            "insight": f"Struggle streak ({streak} msgs): {streak_topic[:60]}",
                        })
                    except Exception as exc:
                        log.debug("Struggle learning failed: %s", exc)
                streak = 0
                streak_topic = ""

        return records

    def _create_eidos_episode(
        self, batch_date: str, interactions: List[Dict],
    ) -> Optional[str]:
        """Create an EIDOS Episode for the archive batch."""
        try:
            from lib.eidos.store import get_store
            from lib.eidos.models import Episode, Step, Phase, Outcome, Evaluation
        except ImportError:
            log.debug("EIDOS not available, skipping episode creation")
            return None

        store = get_store()

        timestamps = [i.get("timestamp", 0) for i in interactions]
        episode = Episode(
            episode_id=uuid.uuid4().hex[:12],
            goal=f"Archive batch {batch_date}: {len(interactions)} interactions",
            success_criteria="Interactions archived and intelligence extracted",
            phase=Phase.CONSOLIDATE,
            outcome=Outcome.SUCCESS,
            start_ts=min(timestamps) if timestamps else time.time(),
            end_ts=max(timestamps) if timestamps else time.time(),
            step_count=len(interactions),
        )

        try:
            store.save_episode(episode)
        except Exception as exc:
            log.warning("Failed to save EIDOS episode: %s", exc)
            return None

        # Save a subset of interactions as Steps (sample up to 20)
        sample = interactions[:20] if len(interactions) > 20 else interactions
        for interaction in sample:
            step = Step(
                step_id=uuid.uuid4().hex[:12],
                episode_id=episode.episode_id,
                intent=f"User: {(interaction.get('user_input', '') or '')[:80]}",
                decision=f"AI responded with {len((interaction.get('ai_response', '') or ''))} chars",
                result=(interaction.get("ai_response", "") or "")[:200],
                evaluation=Evaluation.PASS,
                confidence_before=0.5,
                confidence_after=max(0.5, (interaction.get("sentiment_score", 0) or 0) + 0.5),
                created_at=interaction.get("timestamp", time.time()),
            )
            try:
                store.save_step(step)
            except Exception as exc:
                log.debug("Failed to save EIDOS step: %s", exc)

        # Run distiller (best-effort)
        try:
            from lib.pattern_detection.distiller import PatternDistiller
            distiller = PatternDistiller()
            steps = store.get_steps_for_episode(episode.episode_id)
            if steps:
                distiller.distill_from_steps(steps)
        except Exception as exc:
            log.debug("Distillation skipped: %s", exc)

        return episode.episode_id

    # ------------------------------------------------------------------
    # LLM narrative
    # ------------------------------------------------------------------

    def _generate_narrative(
        self,
        interactions: List[Dict],
        programmatic_data: Dict,
        batch_date: str,
        session_ids: List[str],
    ) -> Dict[str, Any]:
        """Generate a narrative summary via LLM, with template fallback."""
        # Build condensed digest
        digest_parts: List[str] = []
        session_groups: Dict[str, List[Dict]] = defaultdict(list)
        for i in interactions:
            sid = i.get("session_id", "unknown")
            session_groups[sid].append(i)

        topic_words: Dict[str, int] = defaultdict(int)
        for sid, msgs in session_groups.items():
            if msgs:
                first_msg = (msgs[0].get("user_input", "") or "")[:100]
                last_msg = (msgs[-1].get("user_input", "") or "")[:100]
                digest_parts.append(f"Session {sid[:8]}: first='{first_msg}' last='{last_msg}'")
            for m in msgs:
                for word in (m.get("user_input", "") or "").lower().split():
                    cleaned = word.strip(".,!?;:\"'()[]{}").strip()
                    if len(cleaned) > 3:
                        topic_words[cleaned] += 1

        top_topics = sorted(topic_words.items(), key=lambda x: x[1], reverse=True)[:10]
        topic_list = [w for w, _ in top_topics]

        sentiments = [i.get("sentiment_score", 0) or 0 for i in interactions]
        avg_sent = sum(sentiments) / len(sentiments) if sentiments else 0
        sent_label = "positive" if avg_sent > 0.2 else "negative" if avg_sent < -0.2 else "neutral"

        digest = (
            f"Date: {batch_date}\n"
            f"Sessions: {len(session_ids)}, Messages: {len(interactions)}\n"
            f"Topics: {', '.join(topic_list)}\n"
            f"Sentiment arc: avg={avg_sent:.2f} ({sent_label})\n"
            f"Memory entries created: {len(programmatic_data.get('memory_entries', []))}\n"
            f"Learning records: {len(programmatic_data.get('learning_records', []))}\n\n"
            + "\n".join(digest_parts[:15])
        )

        # Try LLM
        try:
            from lib.sidekick.llm_gateway import LLMGateway
            gateway = LLMGateway()
            response = gateway.chat(
                messages=[{"role": "user", "content": digest}],
                system=(
                    "You are summarizing a day's archived chat sessions for Kait, an AI sidekick. "
                    "Return ONLY valid JSON with keys: narrative (1-3 sentence summary), "
                    "topics (list of 3-7 topic strings), mood_label (one word). "
                    "Be concise. Focus on what the user was working on and the overall tone."
                ),
                temperature=0.3,
                max_tokens=300,
            )
            if response:
                parsed = json.loads(response)
                return {
                    "narrative": parsed.get("narrative", ""),
                    "topics": parsed.get("topics", topic_list[:7]),
                    "mood_label": parsed.get("mood_label", sent_label),
                    "llm_used": True,
                }
        except Exception as exc:
            log.debug("LLM narrative generation failed, using template: %s", exc)

        # Template fallback
        topics_str = ", ".join(topic_list[:5]) if topic_list else "general conversation"
        narrative = (
            f"On {batch_date}, {len(interactions)} messages across "
            f"{len(session_ids)} session{'s' if len(session_ids) != 1 else ''} "
            f"covered {topics_str}. Sentiment: {sent_label}."
        )
        return {
            "narrative": narrative,
            "topics": topic_list[:7],
            "mood_label": sent_label,
            "llm_used": False,
        }

    # ------------------------------------------------------------------
    # MindBridge sync
    # ------------------------------------------------------------------

    def _trigger_mind_sync(self, archive_data: Dict[str, Any]) -> None:
        """Best-effort sync of new insights to MindBridge."""
        try:
            from lib.mind_bridge import sync_all_to_mind
            sync_all_to_mind()
        except Exception as exc:
            log.debug("MindBridge sync skipped: %s", exc)
