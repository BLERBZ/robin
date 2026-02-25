"""
Reasoning Bank: SQLite Persistence for AI Sidekick Intelligence

The durable memory for the sidekick system - every interaction, correction,
context evolution, and personality shift is stored here for continuous learning.

Tables:
- interactions: Every user<->AI exchange (the raw conversation record)
- contexts: Evolving knowledge contexts (the working memory)
- corrections: Mistakes and their fixes (where real learning lives)
- evolutions: System evolution events (the growth timeline)
- preferences: User preference signals (personalization layer)
- personality: AI personality traits (the identity state)
- behavior_rules: Learned behavioral rules from reflection cycles

This is the sidekick's long-term memory. Human-inspectable, debuggable,
and the single source of truth for all sidekick state.
"""

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReasoningBank:
    """
    SQLite-based persistence for AI sidekick reasoning and evolution.

    Design principles:
    - Source of truth for all sidekick memory
    - Human-inspectable (just open the SQLite file)
    - Simple schema that maps directly to sidekick concepts
    - Indexes optimized for retrieval patterns
    - No external dependencies beyond stdlib
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the reasoning bank.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.kait/sidekick.db
        """
        if db_path is None:
            kait_dir = Path.home() / ".kait"
            kait_dir.mkdir(exist_ok=True)
            db_path = str(kait_dir / "sidekick.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Interactions: every user<->AI exchange
                CREATE TABLE IF NOT EXISTS interactions (
                    id TEXT PRIMARY KEY,
                    user_input TEXT NOT NULL,
                    ai_response TEXT NOT NULL,
                    mood TEXT,
                    sentiment_score REAL DEFAULT 0.0,
                    timestamp REAL DEFAULT (strftime('%s', 'now')),
                    session_id TEXT,
                    feedback_score REAL
                );

                -- Contexts: evolving knowledge state
                CREATE TABLE IF NOT EXISTS contexts (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL UNIQUE,
                    value_json TEXT NOT NULL,
                    domain TEXT,
                    confidence REAL DEFAULT 0.5,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now')),
                    access_count INTEGER DEFAULT 0
                );

                -- Corrections: mistakes and their fixes
                CREATE TABLE IF NOT EXISTS corrections (
                    id TEXT PRIMARY KEY,
                    original_response TEXT NOT NULL,
                    correction TEXT NOT NULL,
                    reason TEXT,
                    domain TEXT,
                    learned_at REAL DEFAULT (strftime('%s', 'now')),
                    applied_count INTEGER DEFAULT 0
                );

                -- Evolutions: system evolution timeline
                CREATE TABLE IF NOT EXISTS evolutions (
                    id TEXT PRIMARY KEY,
                    evolution_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    metrics_before_json TEXT,
                    metrics_after_json TEXT,
                    timestamp REAL DEFAULT (strftime('%s', 'now'))
                );

                -- Preferences: user preference signals
                CREATE TABLE IF NOT EXISTS preferences (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT,
                    confidence REAL DEFAULT 0.5,
                    last_updated REAL DEFAULT (strftime('%s', 'now'))
                );

                -- Personality: AI personality trait state
                CREATE TABLE IF NOT EXISTS personality (
                    id TEXT PRIMARY KEY,
                    trait TEXT NOT NULL UNIQUE,
                    value_float REAL DEFAULT 0.5,
                    history_json TEXT DEFAULT '[]',
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                );

                -- Behavior rules: learned behavioral patterns from reflection
                CREATE TABLE IF NOT EXISTS behavior_rules (
                    rule_id TEXT PRIMARY KEY,
                    trigger TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    source TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    active INTEGER DEFAULT 1
                );

                -- Indexes for efficient retrieval
                CREATE INDEX IF NOT EXISTS idx_interactions_timestamp
                    ON interactions(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_interactions_session
                    ON interactions(session_id);
                CREATE INDEX IF NOT EXISTS idx_interactions_mood
                    ON interactions(mood);
                CREATE INDEX IF NOT EXISTS idx_interactions_sentiment
                    ON interactions(sentiment_score);

                CREATE INDEX IF NOT EXISTS idx_contexts_key
                    ON contexts(key);
                CREATE INDEX IF NOT EXISTS idx_contexts_domain
                    ON contexts(domain);
                CREATE INDEX IF NOT EXISTS idx_contexts_confidence
                    ON contexts(confidence DESC);
                CREATE INDEX IF NOT EXISTS idx_contexts_updated
                    ON contexts(updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_corrections_domain
                    ON corrections(domain);
                CREATE INDEX IF NOT EXISTS idx_corrections_learned
                    ON corrections(learned_at DESC);

                CREATE INDEX IF NOT EXISTS idx_evolutions_type
                    ON evolutions(evolution_type);
                CREATE INDEX IF NOT EXISTS idx_evolutions_timestamp
                    ON evolutions(timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_preferences_key
                    ON preferences(key);

                CREATE INDEX IF NOT EXISTS idx_personality_trait
                    ON personality(trait);

                -- Archives: summarized batches of old interactions
                CREATE TABLE IF NOT EXISTS archives (
                    archive_id TEXT PRIMARY KEY,
                    batch_label TEXT NOT NULL,
                    session_ids TEXT NOT NULL,
                    interaction_ids TEXT NOT NULL,
                    interaction_count INTEGER DEFAULT 0,
                    time_range_start REAL NOT NULL,
                    time_range_end REAL NOT NULL,
                    memory_entries_json TEXT,
                    learning_records_json TEXT,
                    eidos_episode_id TEXT,
                    distillation_ids_json TEXT,
                    mind_sync_status TEXT DEFAULT 'pending',
                    narrative_summary TEXT,
                    topics_json TEXT,
                    mood_summary TEXT,
                    avg_sentiment REAL DEFAULT 0.0,
                    created_at REAL DEFAULT (strftime('%s','now')),
                    source_breakdown_json TEXT,
                    status TEXT DEFAULT 'complete'
                );
                CREATE INDEX IF NOT EXISTS idx_archives_batch
                    ON archives(batch_label);
                CREATE INDEX IF NOT EXISTS idx_archives_time
                    ON archives(time_range_start DESC);
            """)
            conn.commit()

            # Migration: add source tracking columns
            for col_sql in [
                "ALTER TABLE interactions ADD COLUMN source TEXT DEFAULT 'gui'",
                "ALTER TABLE interactions ADD COLUMN source_meta TEXT",
                "ALTER TABLE interactions ADD COLUMN archived INTEGER DEFAULT 0",
            ]:
                try:
                    conn.execute(col_sql)
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_source ON interactions(source)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interactions_archived ON interactions(archived)"
            )
            conn.commit()

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique ID for new records."""
        return uuid.uuid4().hex[:16]

    # ==================== Interaction Operations ====================

    def save_interaction(
        self,
        user_input: str,
        ai_response: str,
        mood: Optional[str] = None,
        sentiment_score: float = 0.0,
        session_id: Optional[str] = None,
        feedback_score: Optional[float] = None,
        interaction_id: Optional[str] = None,
        source: str = "gui",
        source_meta: Optional[str] = None,
    ) -> str:
        """
        Save a user<->AI interaction.

        Args:
            user_input: What the user said.
            ai_response: What the AI responded.
            mood: Detected mood label (e.g. "curious", "frustrated").
            sentiment_score: Numeric sentiment (-1.0 to 1.0).
            session_id: Session grouping identifier.
            feedback_score: Optional user feedback rating.
            interaction_id: Optional explicit ID; auto-generated if omitted.
            source: Origin of the interaction ("gui", "matrix", "cli").
            source_meta: Optional JSON string with source-specific metadata.

        Returns:
            The interaction ID.
        """
        iid = interaction_id or self._generate_id()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO interactions (
                    id, user_input, ai_response, mood, sentiment_score,
                    timestamp, session_id, feedback_score, source, source_meta
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                iid, user_input, ai_response, mood, sentiment_score,
                time.time(), session_id, feedback_score, source, source_meta,
            ))
            conn.commit()
        return iid

    def get_interaction(self, interaction_id: str) -> Optional[Dict[str, Any]]:
        """Get a single interaction by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM interactions WHERE id = ?",
                (interaction_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_interaction_history(
        self,
        limit: int = 50,
        session_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent interactions, optionally filtered by session and/or source.

        Args:
            limit: Maximum number of interactions to return.
            session_id: If provided, only return interactions from this session.
            source: If provided, only return interactions from this source.

        Returns:
            List of interaction dicts, most recent first.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            clauses: List[str] = []
            params: list = []
            if session_id:
                clauses.append("session_id = ?")
                params.append(session_id)
            if source:
                clauses.append("source = ?")
                params.append(source)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM interactions {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_interaction(self, interaction_id: str) -> bool:
        """Delete an interaction by ID. Returns True if a row was removed."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM interactions WHERE id = ?",
                (interaction_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def update_interaction_feedback(
        self,
        interaction_id: str,
        feedback_score: float,
    ) -> bool:
        """Update the feedback score on an existing interaction."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE interactions SET feedback_score = ? WHERE id = ?",
                (feedback_score, interaction_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_sessions(
        self,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return distinct sessions with summary info.

        Each entry contains: session_id, source, first_ts, last_ts,
        msg_count, first_message, source_meta.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            clauses: List[str] = ["session_id IS NOT NULL"]
            params: list = []
            if source:
                clauses.append("source = ?")
                params.append(source)
            where = f"WHERE {' AND '.join(clauses)}"
            params.append(limit)
            rows = conn.execute(f"""
                SELECT
                    session_id,
                    source,
                    MIN(timestamp) AS first_ts,
                    MAX(timestamp) AS last_ts,
                    COUNT(*) AS msg_count,
                    MIN(user_input) AS first_message,
                    source_meta
                FROM interactions
                {where}
                GROUP BY session_id
                ORDER BY MAX(timestamp) DESC
                LIMIT ?
            """, params).fetchall()
            return [dict(r) for r in rows]

    def get_source_stats(self) -> Dict[str, int]:
        """Return interaction counts grouped by source."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT COALESCE(source, 'gui') AS src, COUNT(*) AS cnt "
                "FROM interactions GROUP BY src"
            ).fetchall()
            return {row[0]: row[1] for row in rows}

    # ==================== Context Operations ====================

    def save_context(
        self,
        key: str,
        value: Any,
        domain: Optional[str] = None,
        confidence: float = 0.5,
        context_id: Optional[str] = None,
    ) -> str:
        """
        Save or create a context entry.

        Args:
            key: Unique context key (e.g. "user_location", "project_stack").
            value: Arbitrary value (will be JSON-serialized).
            domain: Optional domain grouping.
            confidence: Confidence in this context (0.0-1.0).
            context_id: Optional explicit ID; auto-generated if omitted.

        Returns:
            The context ID.
        """
        cid = context_id or self._generate_id()
        now = time.time()
        value_json = json.dumps(value)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO contexts (
                    id, key, value_json, domain, confidence,
                    created_at, updated_at, access_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    domain = excluded.domain,
                    confidence = excluded.confidence,
                    updated_at = ?
            """, (
                cid, key, value_json, domain, confidence,
                now, now, now,
            ))
            conn.commit()
        return cid

    def get_context(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Fast context lookup by key.

        Increments the access counter on each read so hot contexts
        are easily identifiable.

        Args:
            key: The context key to look up.

        Returns:
            Context dict with deserialized value, or None.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Bump access counter first, then read the updated row
            cur = conn.execute(
                "UPDATE contexts SET access_count = access_count + 1 WHERE key = ?",
                (key,)
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM contexts WHERE key = ?",
                (key,)
            ).fetchone()
            conn.commit()
            if not row:
                return None
            result = dict(row)
            result["value"] = json.loads(result.pop("value_json"))
            return result

    def update_context(
        self,
        key: str,
        value: Any,
        domain: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> bool:
        """
        Update an existing context with access counting.

        If the key does not exist, creates it via save_context.

        Args:
            key: The context key to update.
            value: New value (JSON-serializable).
            domain: Optional new domain (unchanged if None).
            confidence: Optional new confidence (unchanged if None).

        Returns:
            True if an existing row was updated, False if a new row was created.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT * FROM contexts WHERE key = ?", (key,)
            ).fetchone()

            if not existing:
                self.save_context(key, value, domain=domain, confidence=confidence or 0.5)
                return False

            now = time.time()
            new_domain = domain if domain is not None else existing["domain"]
            new_confidence = confidence if confidence is not None else existing["confidence"]
            conn.execute("""
                UPDATE contexts
                SET value_json = ?, domain = ?, confidence = ?,
                    updated_at = ?, access_count = access_count + 1
                WHERE key = ?
            """, (
                json.dumps(value), new_domain, new_confidence, now, key,
            ))
            conn.commit()
            return True

    def get_contexts_by_domain(
        self,
        domain: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get all contexts for a given domain."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM contexts
                   WHERE domain = ?
                   ORDER BY confidence DESC, updated_at DESC LIMIT ?""",
                (domain, limit)
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["value"] = json.loads(d.pop("value_json"))
                results.append(d)
            return results

    def search_contexts(
        self,
        key_prefix: str,
        domain: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search contexts by key prefix, optionally filtered by domain."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if domain:
                rows = conn.execute(
                    """SELECT * FROM contexts
                       WHERE key LIKE ? AND domain = ?
                       ORDER BY updated_at DESC LIMIT ?""",
                    (f"{key_prefix}%", domain, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM contexts
                       WHERE key LIKE ?
                       ORDER BY updated_at DESC LIMIT ?""",
                    (f"{key_prefix}%", limit),
                ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["value"] = json.loads(d.pop("value_json"))
                results.append(d)
            return results

    def delete_context(self, key: str) -> bool:
        """Delete a context by key. Returns True if a row was removed."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM contexts WHERE key = ?", (key,))
            conn.commit()
            return cur.rowcount > 0

    # ==================== Correction Operations ====================

    def record_correction(
        self,
        original: str,
        correction: str,
        reason: Optional[str] = None,
        domain: Optional[str] = None,
        correction_id: Optional[str] = None,
    ) -> str:
        """
        Record a mistake and its correction for future learning.

        Args:
            original: The original (incorrect) response.
            correction: The corrected response.
            reason: Why the original was wrong.
            domain: Knowledge domain this applies to.
            correction_id: Optional explicit ID; auto-generated if omitted.

        Returns:
            The correction ID.
        """
        cid = correction_id or self._generate_id()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO corrections (
                    id, original_response, correction, reason,
                    domain, learned_at, applied_count
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (
                cid, original, correction, reason,
                domain, time.time(),
            ))
            conn.commit()
        return cid

    def get_correction(self, correction_id: str) -> Optional[Dict[str, Any]]:
        """Get a single correction by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM corrections WHERE id = ?",
                (correction_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_corrections_by_domain(
        self,
        domain: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get corrections for a given domain, most recent first."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM corrections
                   WHERE domain = ?
                   ORDER BY learned_at DESC LIMIT ?""",
                (domain, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_corrections(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get the most recently learned corrections."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM corrections
                   ORDER BY learned_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def increment_correction_applied(self, correction_id: str) -> bool:
        """Record that a correction was applied in a new response."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE corrections SET applied_count = applied_count + 1 WHERE id = ?",
                (correction_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_correction(self, correction_id: str) -> bool:
        """Delete a correction by ID. Returns True if a row was removed."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM corrections WHERE id = ?",
                (correction_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    # ==================== Evolution Operations ====================

    def save_evolution(
        self,
        evolution_type: str,
        description: str,
        metrics_before: Optional[Dict[str, Any]] = None,
        metrics_after: Optional[Dict[str, Any]] = None,
        evolution_id: Optional[str] = None,
    ) -> str:
        """
        Record a system evolution event.

        Args:
            evolution_type: Category of evolution (e.g. "personality_shift",
                "accuracy_improvement", "new_capability").
            description: Human-readable description of what changed.
            metrics_before: Snapshot of relevant metrics before the change.
            metrics_after: Snapshot of relevant metrics after the change.
            evolution_id: Optional explicit ID; auto-generated if omitted.

        Returns:
            The evolution ID.
        """
        eid = evolution_id or self._generate_id()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO evolutions (
                    id, evolution_type, description,
                    metrics_before_json, metrics_after_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                eid, evolution_type, description,
                json.dumps(metrics_before) if metrics_before else None,
                json.dumps(metrics_after) if metrics_after else None,
                time.time(),
            ))
            conn.commit()
        return eid

    def get_evolution(self, evolution_id: str) -> Optional[Dict[str, Any]]:
        """Get a single evolution event by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM evolutions WHERE id = ?",
                (evolution_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["metrics_before"] = (
                json.loads(result.pop("metrics_before_json"))
                if result.get("metrics_before_json") else None
            )
            result["metrics_after"] = (
                json.loads(result.pop("metrics_after_json"))
                if result.get("metrics_after_json") else None
            )
            return result

    def get_evolution_timeline(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Show the evolution history, most recent first.

        Args:
            limit: Maximum number of evolution events to return.

        Returns:
            List of evolution dicts with deserialized metrics.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM evolutions
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["metrics_before"] = (
                    json.loads(d.pop("metrics_before_json"))
                    if d.get("metrics_before_json") else None
                )
                d["metrics_after"] = (
                    json.loads(d.pop("metrics_after_json"))
                    if d.get("metrics_after_json") else None
                )
                results.append(d)
            return results

    def get_evolutions_by_type(
        self,
        evolution_type: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get evolution events of a specific type."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM evolutions
                   WHERE evolution_type = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (evolution_type, limit)
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["metrics_before"] = (
                    json.loads(d.pop("metrics_before_json"))
                    if d.get("metrics_before_json") else None
                )
                d["metrics_after"] = (
                    json.loads(d.pop("metrics_after_json"))
                    if d.get("metrics_after_json") else None
                )
                results.append(d)
            return results

    def delete_evolution(self, evolution_id: str) -> bool:
        """Delete an evolution event by ID. Returns True if a row was removed."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM evolutions WHERE id = ?",
                (evolution_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    # ==================== Preference Operations ====================

    def save_preference(
        self,
        key: str,
        value: str,
        confidence: float = 0.5,
        preference_id: Optional[str] = None,
    ) -> str:
        """
        Save or update a user preference.

        Args:
            key: Preference key (e.g. "response_length", "tone").
            value: Preference value.
            confidence: How confident we are in this preference (0.0-1.0).
            preference_id: Optional explicit ID; auto-generated if omitted.

        Returns:
            The preference ID.
        """
        pid = preference_id or self._generate_id()
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO preferences (
                    id, key, value, confidence, last_updated
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    last_updated = ?
            """, (
                pid, key, value, confidence, now, now,
            ))
            conn.commit()
        return pid

    def get_preference(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a preference by key."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM preferences WHERE key = ?",
                (key,)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_all_preferences(self) -> List[Dict[str, Any]]:
        """Get all user preferences ordered by confidence."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM preferences ORDER BY confidence DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_preference(self, key: str) -> bool:
        """Delete a preference by key. Returns True if a row was removed."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM preferences WHERE key = ?", (key,)
            )
            conn.commit()
            return cur.rowcount > 0

    # ==================== Personality Operations ====================

    def save_personality_trait(
        self,
        trait: str,
        value_float: float = 0.5,
        trait_id: Optional[str] = None,
    ) -> str:
        """
        Save or create a personality trait.

        Args:
            trait: Trait name (e.g. "warmth", "formality", "humor").
            value_float: Trait intensity (0.0-1.0).
            trait_id: Optional explicit ID; auto-generated if omitted.

        Returns:
            The trait ID.
        """
        tid = trait_id or self._generate_id()
        now = time.time()
        initial_history = json.dumps([{"value": value_float, "timestamp": now}])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO personality (
                    id, trait, value_float, history_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(trait) DO UPDATE SET
                    value_float = excluded.value_float,
                    updated_at = ?
            """, (
                tid, trait, value_float, initial_history, now, now,
            ))
            conn.commit()
        return tid

    def get_personality_trait(self, trait: str) -> Optional[Dict[str, Any]]:
        """Get a personality trait by name with deserialized history."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM personality WHERE trait = ?",
                (trait,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["history"] = json.loads(result.pop("history_json", "[]"))
            return result

    def get_all_personality_traits(self) -> List[Dict[str, Any]]:
        """Get all personality traits."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM personality ORDER BY trait"
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["history"] = json.loads(d.pop("history_json", "[]"))
                results.append(d)
            return results

    def evolve_personality(self, trait: str, new_value: float) -> str:
        """
        Evolve a personality trait, recording the change in its history.

        If the trait does not exist, it is created. The full history of
        value changes is preserved in history_json for trend analysis.

        Args:
            trait: Trait name to evolve.
            new_value: New trait intensity (0.0-1.0).

        Returns:
            The trait ID.
        """
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT * FROM personality WHERE trait = ?", (trait,)
            ).fetchone()

            if existing:
                history = json.loads(existing["history_json"] or "[]")
                history.append({"value": new_value, "timestamp": now})
                conn.execute("""
                    UPDATE personality
                    SET value_float = ?, history_json = ?, updated_at = ?
                    WHERE trait = ?
                """, (
                    new_value, json.dumps(history), now, trait,
                ))
                conn.commit()

                # Record as an evolution event
                old_value = existing["value_float"]
                self.save_evolution(
                    evolution_type="personality_shift",
                    description=f"Trait '{trait}' shifted from {old_value:.3f} to {new_value:.3f}",
                    metrics_before={"trait": trait, "value": old_value},
                    metrics_after={"trait": trait, "value": new_value},
                )
                return existing["id"]
            else:
                tid = self._generate_id()
                history = [{"value": new_value, "timestamp": now}]
                conn.execute("""
                    INSERT INTO personality (
                        id, trait, value_float, history_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    tid, trait, new_value, json.dumps(history), now,
                ))
                conn.commit()

                self.save_evolution(
                    evolution_type="personality_shift",
                    description=f"New trait '{trait}' initialized at {new_value:.3f}",
                    metrics_before=None,
                    metrics_after={"trait": trait, "value": new_value},
                )
                return tid

    def delete_personality_trait(self, trait: str) -> bool:
        """Delete a personality trait by name. Returns True if a row was removed."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM personality WHERE trait = ?", (trait,)
            )
            conn.commit()
            return cur.rowcount > 0

    # ==================== Behavior Rule Operations ====================

    def save_behavior_rule(self, rule_id: str, trigger: str, action: str, confidence: float, source: str, created_at: float, active: bool = True) -> None:
        """Save or update a behavior rule."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO behavior_rules
                   (rule_id, trigger, action, confidence, source, created_at, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (rule_id, trigger, action, confidence, source, created_at, 1 if active else 0),
            )
            conn.commit()

    def get_active_behavior_rules(self) -> List[Dict[str, Any]]:
        """Get all active behavior rules."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM behavior_rules WHERE active = 1 ORDER BY confidence DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def deactivate_behavior_rule(self, rule_id: str) -> None:
        """Deactivate a behavior rule."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE behavior_rules SET active = 0 WHERE rule_id = ?", (rule_id,))
            conn.commit()

    # ==================== Archive Operations ====================

    def get_archivable_sessions(self, age_seconds: int = 86400) -> List[Dict[str, Any]]:
        """Return sessions where ALL interactions are unarchived and older than age_seconds."""
        cutoff = time.time() - age_seconds
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    session_id,
                    source,
                    MIN(timestamp) AS first_ts,
                    MAX(timestamp) AS last_ts,
                    COUNT(*) AS msg_count,
                    MIN(user_input) AS first_message,
                    source_meta
                FROM interactions
                WHERE session_id IS NOT NULL
                  AND archived = 0
                  AND timestamp < ?
                GROUP BY session_id
                HAVING MAX(timestamp) < ?
                ORDER BY MAX(timestamp) DESC
            """, (cutoff, cutoff)).fetchall()
            return [dict(r) for r in rows]

    def mark_interactions_archived(self, interaction_ids: List[str]) -> int:
        """Mark a list of interactions as archived. Returns count updated."""
        if not interaction_ids:
            return 0
        with sqlite3.connect(self.db_path) as conn:
            placeholders = ",".join("?" for _ in interaction_ids)
            cur = conn.execute(
                f"UPDATE interactions SET archived = 1 WHERE id IN ({placeholders})",
                interaction_ids,
            )
            conn.commit()
            return cur.rowcount

    def save_archive(self, archive_data: Dict[str, Any]) -> str:
        """Insert a record into the archives table. Returns the archive_id."""
        aid = archive_data.get("archive_id") or self._generate_id()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO archives (
                    archive_id, batch_label, session_ids, interaction_ids,
                    interaction_count, time_range_start, time_range_end,
                    memory_entries_json, learning_records_json,
                    eidos_episode_id, distillation_ids_json,
                    mind_sync_status, narrative_summary, topics_json,
                    mood_summary, avg_sentiment, created_at,
                    source_breakdown_json, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                aid,
                archive_data.get("batch_label", ""),
                json.dumps(archive_data.get("session_ids", [])),
                json.dumps(archive_data.get("interaction_ids", [])),
                archive_data.get("interaction_count", 0),
                archive_data.get("time_range_start", 0.0),
                archive_data.get("time_range_end", 0.0),
                json.dumps(archive_data.get("memory_entries", [])),
                json.dumps(archive_data.get("learning_records", [])),
                archive_data.get("eidos_episode_id"),
                json.dumps(archive_data.get("distillation_ids", [])),
                archive_data.get("mind_sync_status", "pending"),
                archive_data.get("narrative_summary", ""),
                json.dumps(archive_data.get("topics", [])),
                archive_data.get("mood_summary", ""),
                archive_data.get("avg_sentiment", 0.0),
                time.time(),
                json.dumps(archive_data.get("source_breakdown", {})),
                archive_data.get("status", "complete"),
            ))
            conn.commit()
        return aid

    def get_archives(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return archives ordered by time_range_start descending."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM archives ORDER BY time_range_start DESC LIMIT ?",
                (limit,),
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                for key in ("session_ids", "interaction_ids", "memory_entries_json",
                            "learning_records_json", "distillation_ids_json",
                            "topics_json", "source_breakdown_json"):
                    if d.get(key):
                        try:
                            d[key] = json.loads(d[key])
                        except (json.JSONDecodeError, TypeError):
                            pass
                results.append(d)
            return results

    def get_archive(self, archive_id: str) -> Optional[Dict[str, Any]]:
        """Return a single archive record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM archives WHERE archive_id = ?", (archive_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for key in ("session_ids", "interaction_ids", "memory_entries_json",
                        "learning_records_json", "distillation_ids_json",
                        "topics_json", "source_breakdown_json"):
                if d.get(key):
                    try:
                        d[key] = json.loads(d[key])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return d

    def get_archive_interactions(self, archive_id: str) -> List[Dict[str, Any]]:
        """Fetch full interactions belonging to an archive by stored IDs."""
        archive = self.get_archive(archive_id)
        if not archive:
            return []
        ids = archive.get("interaction_ids", [])
        if isinstance(ids, str):
            try:
                ids = json.loads(ids)
            except (json.JSONDecodeError, TypeError):
                return []
        if not ids:
            return []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT * FROM interactions WHERE id IN ({placeholders}) ORDER BY timestamp ASC",
                ids,
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_sessions(
        self,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Like get_sessions() but only returns non-archived interactions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            clauses: List[str] = ["session_id IS NOT NULL", "archived = 0"]
            params: list = []
            if source:
                clauses.append("source = ?")
                params.append(source)
            where = f"WHERE {' AND '.join(clauses)}"
            params.append(limit)
            rows = conn.execute(f"""
                SELECT
                    session_id,
                    source,
                    MIN(timestamp) AS first_ts,
                    MAX(timestamp) AS last_ts,
                    COUNT(*) AS msg_count,
                    MIN(user_input) AS first_message,
                    source_meta
                FROM interactions
                {where}
                GROUP BY session_id
                ORDER BY MAX(timestamp) DESC
                LIMIT ?
            """, params).fetchall()
            return [dict(r) for r in rows]

    # ==================== Statistics ====================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive database statistics.

        Returns:
            Dict with counts, averages, and health indicators across all tables.
        """
        with sqlite3.connect(self.db_path) as conn:
            interaction_count = conn.execute(
                "SELECT COUNT(*) FROM interactions"
            ).fetchone()[0]
            context_count = conn.execute(
                "SELECT COUNT(*) FROM contexts"
            ).fetchone()[0]
            correction_count = conn.execute(
                "SELECT COUNT(*) FROM corrections"
            ).fetchone()[0]
            evolution_count = conn.execute(
                "SELECT COUNT(*) FROM evolutions"
            ).fetchone()[0]
            preference_count = conn.execute(
                "SELECT COUNT(*) FROM preferences"
            ).fetchone()[0]
            personality_count = conn.execute(
                "SELECT COUNT(*) FROM personality"
            ).fetchone()[0]
            behavior_rule_count = conn.execute(
                "SELECT COUNT(*) FROM behavior_rules"
            ).fetchone()[0]

            # Average sentiment across all interactions
            avg_sentiment_row = conn.execute(
                "SELECT AVG(sentiment_score) FROM interactions"
            ).fetchone()
            avg_sentiment = avg_sentiment_row[0] if avg_sentiment_row[0] is not None else 0.0

            # Average feedback score (only rated interactions)
            avg_feedback_row = conn.execute(
                "SELECT AVG(feedback_score) FROM interactions WHERE feedback_score IS NOT NULL"
            ).fetchone()
            avg_feedback = avg_feedback_row[0] if avg_feedback_row[0] is not None else 0.0

            # Total corrections applied
            total_applied_row = conn.execute(
                "SELECT SUM(applied_count) FROM corrections"
            ).fetchone()
            total_corrections_applied = total_applied_row[0] if total_applied_row[0] is not None else 0

            # High-confidence contexts
            high_conf_contexts = conn.execute(
                "SELECT COUNT(*) FROM contexts WHERE confidence >= 0.7"
            ).fetchone()[0]

            # Most accessed contexts (top 5)
            conn.row_factory = sqlite3.Row
            hot_contexts = conn.execute(
                """SELECT key, access_count FROM contexts
                   ORDER BY access_count DESC LIMIT 5"""
            ).fetchall()

            # Distinct sessions
            distinct_sessions = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM interactions WHERE session_id IS NOT NULL"
            ).fetchone()[0]

            return {
                "interactions": interaction_count,
                "contexts": context_count,
                "corrections": correction_count,
                "evolutions": evolution_count,
                "preferences": preference_count,
                "personality_traits": personality_count,
                "behavior_rules": behavior_rule_count,
                "avg_sentiment": round(avg_sentiment, 4),
                "avg_feedback": round(avg_feedback, 4),
                "total_corrections_applied": total_corrections_applied,
                "high_confidence_contexts": high_conf_contexts,
                "hot_contexts": [
                    {"key": r["key"], "access_count": r["access_count"]}
                    for r in hot_contexts
                ],
                "distinct_sessions": distinct_sessions,
                "db_path": self.db_path,
            }


# Singleton instance
_reasoning_bank: Optional[ReasoningBank] = None


def get_reasoning_bank(db_path: Optional[str] = None) -> ReasoningBank:
    """Get the singleton ReasoningBank instance."""
    global _reasoning_bank
    if _reasoning_bank is None or (db_path and _reasoning_bank.db_path != db_path):
        _reasoning_bank = ReasoningBank(db_path)
    return _reasoning_bank
