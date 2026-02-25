"""LLM cost tracking with local SQLite persistence.

Aggregates cost data from LLM observability and (optionally) LiteLLM proxy
spend logs. Provides per-model and per-period cost breakdowns.

Usage:
    from lib.sidekick.llm_cost_tracker import get_cost_tracker
    tracker = get_cost_tracker()
    summary = tracker.get_cost_summary(period="1h")
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.diagnostics import log_debug

_LOG_TAG = "llm_cost_tracker"
_DB_PATH = Path.home() / ".kait" / "llm_costs.db"
_ENABLED_VALUES = {"1", "true", "yes", "on"}


class LLMCostTracker:
    """Tracks and persists LLM usage costs."""

    def __init__(self) -> None:
        self._db_path = _DB_PATH
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create the cost tracking table if it doesn't exist."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS llm_costs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        input_tokens INTEGER DEFAULT 0,
                        output_tokens INTEGER DEFAULT 0,
                        cost_usd REAL DEFAULT 0.0,
                        latency_ms REAL DEFAULT 0.0,
                        success INTEGER DEFAULT 1
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_costs_timestamp
                    ON llm_costs (timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_costs_provider
                    ON llm_costs (provider)
                """)
        except Exception as exc:
            log_debug(_LOG_TAG, f"Failed to init cost DB: {exc}", exc)

    def record_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        success: bool = True,
    ) -> None:
        """Record a single LLM call cost entry."""
        with self._lock:
            try:
                with sqlite3.connect(str(self._db_path)) as conn:
                    conn.execute(
                        """INSERT INTO llm_costs
                           (timestamp, provider, model, input_tokens, output_tokens,
                            cost_usd, latency_ms, success)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (time.time(), provider, model, input_tokens, output_tokens,
                         cost_usd, latency_ms, 1 if success else 0),
                    )
            except Exception as exc:
                log_debug(_LOG_TAG, f"Failed to record cost: {exc}", exc)

    def sync_from_observer(self) -> int:
        """Pull recent records from the LLM observer into the cost DB.

        Returns the number of new records synced.
        """
        try:
            from lib.llm_observability import get_observer
            observer = get_observer()
            if not observer.enabled:
                return 0

            recent = observer.get_recent(limit=100)
            synced = 0
            for record in recent:
                self.record_cost(
                    provider=record.get("provider", "unknown"),
                    model=record.get("model", "unknown"),
                    input_tokens=record.get("input_tokens", 0),
                    output_tokens=record.get("output_tokens", 0),
                    cost_usd=record.get("estimated_cost_usd", 0.0),
                    latency_ms=record.get("latency_ms", 0.0),
                    success=record.get("error") is None,
                )
                synced += 1
            return synced
        except Exception as exc:
            log_debug(_LOG_TAG, f"Observer sync failed: {exc}", exc)
            return 0

    def get_cost_summary(self, period: str = "1h") -> Dict[str, Any]:
        """Get cost summary for a time period.

        Args:
            period: "1h", "24h", "7d", or "30d"

        Returns dict with total_cost, call_count, avg_cost, by_provider, by_model.
        """
        seconds_map = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}
        window = seconds_map.get(period, 3600)
        cutoff = time.time() - window

        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row

                # Total summary
                row = conn.execute(
                    """SELECT COUNT(*) as count, SUM(cost_usd) as total,
                              AVG(cost_usd) as avg, SUM(input_tokens) as inp,
                              SUM(output_tokens) as outp
                       FROM llm_costs WHERE timestamp > ?""",
                    (cutoff,),
                ).fetchone()

                # By provider
                provider_rows = conn.execute(
                    """SELECT provider, COUNT(*) as count, SUM(cost_usd) as total
                       FROM llm_costs WHERE timestamp > ?
                       GROUP BY provider ORDER BY total DESC""",
                    (cutoff,),
                ).fetchall()

                # By model
                model_rows = conn.execute(
                    """SELECT model, COUNT(*) as count, SUM(cost_usd) as total
                       FROM llm_costs WHERE timestamp > ?
                       GROUP BY model ORDER BY total DESC LIMIT 10""",
                    (cutoff,),
                ).fetchall()

                return {
                    "period": period,
                    "total_cost_usd": row["total"] or 0.0,
                    "call_count": row["count"] or 0,
                    "avg_cost_usd": row["avg"] or 0.0,
                    "total_input_tokens": row["inp"] or 0,
                    "total_output_tokens": row["outp"] or 0,
                    "by_provider": [
                        {"provider": r["provider"], "calls": r["count"], "cost_usd": r["total"] or 0.0}
                        for r in provider_rows
                    ],
                    "by_model": [
                        {"model": r["model"], "calls": r["count"], "cost_usd": r["total"] or 0.0}
                        for r in model_rows
                    ],
                }
        except Exception as exc:
            log_debug(_LOG_TAG, f"Cost summary query failed: {exc}", exc)
            return {"period": period, "total_cost_usd": 0.0, "call_count": 0}

    def get_breakdown_by_model(self, window_s: float = 3600) -> List[Dict[str, Any]]:
        """Return cost breakdown grouped by model."""
        cutoff = time.time() - window_s
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT model, provider, COUNT(*) as count,
                              SUM(cost_usd) as total, AVG(latency_ms) as avg_lat
                       FROM llm_costs WHERE timestamp > ?
                       GROUP BY model ORDER BY total DESC""",
                    (cutoff,),
                ).fetchall()
                return [
                    {
                        "model": r["model"],
                        "provider": r["provider"],
                        "calls": r["count"],
                        "cost_usd": r["total"] or 0.0,
                        "avg_latency_ms": r["avg_lat"] or 0.0,
                    }
                    for r in rows
                ]
        except Exception as exc:
            log_debug(_LOG_TAG, f"Model breakdown query failed: {exc}", exc)
            return []

    def cleanup_old_records(self, max_age_days: int = 30) -> int:
        """Remove cost records older than max_age_days."""
        cutoff = time.time() - (max_age_days * 86400)
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                cursor = conn.execute(
                    "DELETE FROM llm_costs WHERE timestamp < ?", (cutoff,),
                )
                return cursor.rowcount
        except Exception as exc:
            log_debug(_LOG_TAG, f"Cleanup failed: {exc}", exc)
            return 0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_instance: Optional[LLMCostTracker] = None


def get_cost_tracker() -> LLMCostTracker:
    """Return the shared LLMCostTracker singleton."""
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = LLMCostTracker()
        return _singleton_instance
