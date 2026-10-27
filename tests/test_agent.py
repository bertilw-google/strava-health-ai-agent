"""Unit tests for Strava Health AI Agent core logic and guardrails."""

import unittest

from strava_health_agent.agent import StravaHealthAgent
from strava_health_agent.memory_store import MemoryStore
from strava_health_agent.models import (
    AlertSeverity,
    AthleteProfile,
    FeedbackType,
)
from strava_health_agent.strava_client import MockStravaClient


class TestStravaHealthAgent(unittest.TestCase):

    def setUp(self):
        self.athlete = AthleteProfile(
            athlete_id=1,
            firstname="Morgan",
            lastname="Lee",
            resting_hr=50,
            max_hr=185,
        )
        self.memory = MemoryStore(":memory:")
        self.agent = StravaHealthAgent(self.athlete, memory=self.memory)

    def test_overtraining_spike_guardrail(self):
        client = MockStravaClient(scenario="danger_spike")
        activities = client.get_activities(per_page=30)
        feedback = self.agent.evaluate_health_and_fitness(
            activities,
            feedback_type=FeedbackType.MORNING_READINESS,
        )
        # Should be flagged as CRITICAL severity due to ACWR > 1.5
        self.assertEqual(feedback.severity, AlertSeverity.CRITICAL)
        self.assertIn("Danger Zone", feedback.summary_headline)
        # Verify recommended workout prioritizes rest/recovery
        self.assertTrue(
            "Rest" in feedback.suggested_today_workout or "Zone 1" in feedback.suggested_today_workout
        )
        # Verify action items include cancelling high-intensity
        action_titles = [a.title for a in feedback.action_items]
        self.assertTrue(any("Cancel" in t or "Rest" in t for t in action_titles))

    def test_optimal_progression(self):
        client = MockStravaClient(scenario="optimal_build")
        activities = client.get_activities(per_page=30)
        feedback = self.agent.evaluate_health_and_fitness(
            activities,
            feedback_type=FeedbackType.MORNING_READINESS,
        )
        self.assertEqual(feedback.severity, AlertSeverity.ADVISORY)
        self.assertIn("Sweet Spot", feedback.summary_headline)


if __name__ == "__main__":
    unittest.main()
