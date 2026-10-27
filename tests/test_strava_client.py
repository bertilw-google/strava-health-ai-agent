"""Unit tests for Strava API client and mock fixtures."""

import unittest

from strava_health_agent.models import Activity, AthleteProfile
from strava_health_agent.strava_client import MockStravaClient


class TestMockStravaClient(unittest.TestCase):

    def test_mock_client_danger_spike(self):
        client = MockStravaClient(scenario="danger_spike")
        athlete = client.get_athlete()
        self.assertEqual(athlete.firstname, "Alex")
        self.assertEqual(athlete.primary_sport, "Run")

        activities = client.get_activities(per_page=30)
        self.assertGreater(len(activities), 5)
        # Check that activities have valid metrics
        act = activities[0]
        self.assertGreater(act.distance_meters, 0.0)
        self.assertGreater(act.moving_time_seconds, 0)
        self.assertIsNotNone(act.pace_min_per_km)

    def test_mock_client_scenarios(self):
        scenarios = ["danger_spike", "optimal_build", "taper_freshness"]
        for s in scenarios:
            client = MockStravaClient(scenario=s)
            acts = client.get_activities(per_page=30)
            self.assertTrue(len(acts) > 0, f"Scenario {s} produced empty activities")


if __name__ == "__main__":
    unittest.main()
