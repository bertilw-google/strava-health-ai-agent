"""Unit tests for Sports Science & Physiological Analytics Engine."""

import unittest
from datetime import datetime, timezone, timedelta

from strava_health_agent.analytics import SportsScienceEngine
from strava_health_agent.models import Activity, AthleteProfile


class TestSportsScienceEngine(unittest.TestCase):

    def setUp(self):
        self.athlete = AthleteProfile(
            athlete_id=1,
            firstname="Jordan",
            lastname="Smith",
            resting_hr=50,
            max_hr=190,
            lactate_threshold_hr=170,
        )
        self.engine = SportsScienceEngine(self.athlete)

    def test_trimp_calculation_with_heart_rate(self):
        # 60 minute run at avg HR 155 bpm
        act = Activity(
            id=101,
            name="Tempo Run",
            type="Run",
            start_date="2026-10-20T08:00:00Z",
            distance_meters=10000.0,
            moving_time_seconds=3600,
            elapsed_time_seconds=3600,
            total_elevation_gain=50.0,
            average_speed_mps=2.78,
            max_speed_mps=3.5,
            average_heartrate=155.0,
            max_heartrate=175.0,
        )
        trimp = self.engine.calculate_trimp(act)
        self.assertGreater(trimp, 50.0)
        self.assertLess(trimp, 200.0)

    def test_trimp_fallback_without_heart_rate(self):
        # 45 minute run without HR data
        act = Activity(
            id=102,
            name="Run Without HR",
            type="Run",
            start_date="2026-10-20T08:00:00Z",
            distance_meters=8000.0,
            moving_time_seconds=2700,
            elapsed_time_seconds=2700,
            total_elevation_gain=20.0,
            average_speed_mps=2.96,
            max_speed_mps=3.6,
            average_heartrate=None,
            perceived_exertion=7,
        )
        trimp = self.engine.calculate_trimp(act)
        self.assertGreater(trimp, 0.0)

    def test_heart_rate_zones(self):
        zone1 = self.engine.calculate_hr_zones(100.0)
        self.assertIn("Zone 1", zone1["primary_zone"])

        zone2 = self.engine.calculate_hr_zones(125.0)
        self.assertIn("Zone 2", zone2["primary_zone"])

        zone4 = self.engine.calculate_hr_zones(165.0)
        self.assertIn("Zone 4", zone4["primary_zone"])

        zone5 = self.engine.calculate_hr_zones(180.0)
        self.assertIn("Zone 5", zone5["primary_zone"])

    def test_acwr_and_training_load_calculation(self):
        # Build 14 activities simulating steady training
        now = datetime.now(timezone.utc)
        activities = []
        for i in range(14):
            dt = (now - timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            activities.append(
                Activity(
                    id=200 + i,
                    name=f"Run {i}",
                    type="Run",
                    start_date=dt,
                    distance_meters=10000.0,
                    moving_time_seconds=3000,
                    elapsed_time_seconds=3000,
                    total_elevation_gain=50.0,
                    average_speed_mps=3.33,
                    max_speed_mps=4.0,
                    average_heartrate=150.0,
                    max_heartrate=165.0,
                )
            )

        metrics = self.engine.compute_training_load(activities, reference_date=now)
        self.assertGreater(metrics.acute_training_load, 0.0)
        self.assertGreater(metrics.chronic_training_load, 0.0)
        self.assertIsInstance(metrics.acwr, float)
        self.assertIn(metrics.risk_zone, [
            "Under-trained / Low Readiness",
            "Optimal 'Sweet Spot' (Low Injury Risk)",
            "Overreaching / Heightened Fatigue",
            "Danger Zone (High Injury & Overtraining Risk)",
        ])


if __name__ == "__main__":
    unittest.main()
