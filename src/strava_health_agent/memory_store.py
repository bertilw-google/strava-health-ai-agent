"""Context Engineering: Persistent Session & Long-Term Memory Store.

Implements Day 3 (Context Engineering, Sessions & Memory) of the 5-Day AI Agent Intensive:
- Short-term session context tracking (recent workouts, daily check-ins)
- Long-term memory persistence (athlete physiological profile, historical ACWR trends,
  subjective athlete fatigue/injury logs, and past coaching feedback).
Uses SQLite for robust zero-dependency local persistence.
"""

import asyncio
import json
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import Activity, AthleteProfile, HealthFeedback, TrainingLoadMetrics
from .observability import PIIRedactor


class ContextCompactor:
    """Manages context bloat via sliding windows, token-budget truncation, and summarization.

    Compatible with Google ADK Context Compaction, Memory Bank, and Vertex AI Context Caching.
    """

    def __init__(self, max_token_budget: int = 4000, sliding_window_size: int = 7):
        self.max_token_budget = max_token_budget
        self.sliding_window_size = sliding_window_size

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Approximates LLM token count (~4 characters per token)."""
        return max(1, len(text) // 4)

    def compact_activity_history(self, activities: List[Activity]) -> Dict[str, Any]:
        """Applies a sliding window to recent activities and summarizes older history."""
        recent = activities[: self.sliding_window_size]
        older = activities[self.sliding_window_size :]

        older_summary = {
            "archived_workouts_count": len(older),
            "total_archived_km": round(sum(a.distance_km for a in older), 1),
            "total_archived_minutes": round(sum(a.duration_minutes for a in older), 1),
            "avg_archived_hr": (
                round(
                    sum(a.average_heartrate for a in older if a.average_heartrate)
                    / max(1, sum(1 for a in older if a.average_heartrate)),
                    1,
                )
                if older else None
            ),
        }

        payload = {
            "sliding_window_recent": [a.to_dict() for a in recent],
            "compacted_historical_summary": older_summary,
        }
        serialized = json.dumps(payload)
        if self.estimate_tokens(serialized) > self.max_token_budget:
            # Truncate sliding window further to fit strict token budget
            payload["sliding_window_recent"] = payload["sliding_window_recent"][:3]
            payload["token_truncated"] = True
        return payload


class MemoryStore:
    """Manages short-term session context and long-term agent memory."""

    def __init__(self, db_path: str = "strava_health_memory.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Athlete Profile table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS athlete_profile (
                    athlete_id INTEGER PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Activities cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    activity_id INTEGER PRIMARY KEY,
                    athlete_id INTEGER,
                    start_date TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Daily Physiological Load snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS training_load_history (
                    date TEXT PRIMARY KEY,
                    atl REAL,
                    ctl REAL,
                    tsb REAL,
                    acwr REAL,
                    risk_zone TEXT,
                    weekly_km REAL,
                    weekly_hours REAL,
                    data_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
            """)
            # Proactive Health Feedback history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            # Subjective Athlete Logs (soreness, sleep, illness, injuries)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subjective_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    sleep_quality INTEGER, -- 1-5
                    muscle_soreness INTEGER, -- 1-5 (5 = extreme)
                    stress_level INTEGER, -- 1-5
                    notes TEXT,
                    tags TEXT
                )
            """)
            conn.commit()

    def save_athlete_profile(self, profile: AthleteProfile) -> None:
        with self._get_connection() as conn:
            conn.cursor().execute(
                """
                INSERT INTO athlete_profile (athlete_id, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(athlete_id) DO UPDATE SET
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at
                """,
                (profile.athlete_id, json.dumps(profile.to_dict()), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    def get_athlete_profile(self, athlete_id: Optional[int] = None) -> Optional[AthleteProfile]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if athlete_id:
                cursor.execute("SELECT data_json FROM athlete_profile WHERE athlete_id=?", (athlete_id,))
            else:
                cursor.execute("SELECT data_json FROM athlete_profile LIMIT 1")
            row = cursor.fetchone()
            if row:
                return AthleteProfile.from_dict(json.loads(row["data_json"]))
            return None

    def save_activities(self, activities: List[Activity], athlete_id: int = 1) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for act in activities:
                cursor.execute(
                    """
                    INSERT INTO activities (activity_id, athlete_id, start_date, data_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(activity_id) DO UPDATE SET
                        data_json=excluded.data_json,
                        start_date=excluded.start_date
                    """,
                    (
                        act.id,
                        athlete_id,
                        act.start_date,
                        json.dumps(act.to_dict()),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            conn.commit()

    def get_recent_activities(self, limit: int = 50) -> List[Activity]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_json FROM activities ORDER BY start_date DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [Activity.from_dict(json.loads(r["data_json"])) for r in rows]

    def record_training_load(self, metrics: TrainingLoadMetrics) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO training_load_history
                (date, atl, ctl, tsb, acwr, risk_zone, weekly_km, weekly_hours, data_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    atl=excluded.atl,
                    ctl=excluded.ctl,
                    tsb=excluded.tsb,
                    acwr=excluded.acwr,
                    risk_zone=excluded.risk_zone,
                    weekly_km=excluded.weekly_km,
                    weekly_hours=excluded.weekly_hours,
                    data_json=excluded.data_json,
                    recorded_at=excluded.recorded_at
                """,
                (
                    metrics.date,
                    metrics.acute_training_load,
                    metrics.chronic_training_load,
                    metrics.training_stress_balance,
                    metrics.acwr,
                    metrics.risk_zone,
                    metrics.weekly_total_km,
                    metrics.weekly_total_hours,
                    json.dumps(metrics.to_dict()),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def save_feedback(self, feedback: HealthFeedback) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO health_feedback (feedback_id, timestamp, feedback_type, severity, headline, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(feedback_id) DO UPDATE SET
                    data_json=excluded.data_json
                """,
                (
                    feedback.feedback_id,
                    feedback.timestamp,
                    feedback.feedback_type.value,
                    feedback.severity.value,
                    feedback.summary_headline,
                    json.dumps(feedback.to_dict()),
                ),
            )
            conn.commit()

    def get_recent_feedback(self, limit: int = 10) -> List[HealthFeedback]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_json FROM health_feedback ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [HealthFeedback.from_dict(json.loads(r["data_json"])) for r in rows]

    def log_subjective_readiness(
        self,
        sleep_quality: int,
        muscle_soreness: int,
        stress_level: int,
        notes: str = "",
        tags: str = "",
    ) -> None:
        """Persists athlete readiness after scrubbing PII via PIIRedactor."""
        redactor = PIIRedactor()
        safe_notes = redactor.redact_text(notes)
        safe_tags = redactor.redact_text(tags)
        with self._get_connection() as conn:
            conn.cursor().execute(
                """
                INSERT INTO subjective_logs (timestamp, sleep_quality, muscle_soreness, stress_level, notes, tags)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    sleep_quality,
                    muscle_soreness,
                    stress_level,
                    safe_notes,
                    safe_tags,
                ),
            )
            conn.commit()

    def get_recent_subjective_logs(self, limit: int = 7) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM subjective_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def consolidate_memory_sync(self, max_keep_activities: int = 50) -> Dict[str, Any]:
        """Consolidates long-term memory and compactions older workout entries."""
        activities = self.get_recent_activities(limit=200)
        compactor = ContextCompactor()
        compacted = compactor.compact_activity_history(activities)
        return {
            "status": "CONSOLIDATED",
            "retained_recent_count": len(compacted["sliding_window_recent"]),
            "archived_summary": compacted["compacted_historical_summary"],
        }

    async def async_consolidate_memory(self, max_keep_activities: int = 50) -> Dict[str, Any]:
        """Asynchronously runs expensive memory compaction in a background thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.consolidate_memory_sync, max_keep_activities)

    def submit_background_consolidation(self, max_keep_activities: int = 50) -> Future:
        """Submits non-blocking background memory consolidation task."""
        executor = ThreadPoolExecutor(max_workers=1)
        return executor.submit(self.consolidate_memory_sync, max_keep_activities)
