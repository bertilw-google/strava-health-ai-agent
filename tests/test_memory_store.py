"""Unit tests for Context Engineering & Memory Store."""

import unittest

from strava_health_agent.memory_store import MemoryStore
from strava_health_agent.models import (
    Activity,
    AthleteProfile,
    AlertSeverity,
    FeedbackType,
    HealthFeedback,
    TrainingLoadMetrics,
)


class TestMemoryStore(unittest.TestCase):

    def setUp(self):
        self.memory = MemoryStore(":memory:")

    def test_athlete_profile_crud(self):
        profile = AthleteProfile(
            athlete_id=123,
            firstname="Taylor",
            lastname="Swift",
            weight_kg=62.0,
            resting_hr=48,
            max_hr=182,
        )
        self.memory.save_athlete_profile(profile)
        retrieved = self.memory.get_athlete_profile(123)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.firstname, "Taylor")
        self.assertEqual(retrieved.resting_hr, 48)

    def test_activities_persistence(self):
        act = Activity(
            id=999,
            name="Test Run",
            type="Run",
            start_date="2026-10-25T10:00:00Z",
            distance_meters=5000.0,
            moving_time_seconds=1500,
            elapsed_time_seconds=1550,
            total_elevation_gain=30.0,
            average_speed_mps=3.33,
            max_speed_mps=4.0,
        )
        self.memory.save_activities([act], athlete_id=123)
        recent = self.memory.get_recent_activities(limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].id, 999)

    def test_subjective_logs(self):
        self.memory.log_subjective_readiness(
            sleep_quality=4,
            muscle_soreness=3,
            stress_level=2,
            notes="Felt good, slight hamstring tightness",
        )
        logs = self.memory.get_recent_subjective_logs(limit=5)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["sleep_quality"], 4)
        self.assertIn("hamstring", logs[0]["notes"])


if __name__ == "__main__":
    unittest.main()
