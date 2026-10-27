"""Unit tests for Proactive Scheduler & Notification Dispatcher."""

import unittest

from strava_health_agent.agent import StravaHealthAgent
from strava_health_agent.memory_store import MemoryStore
from strava_health_agent.models import AthleteProfile, FeedbackType
from strava_health_agent.proactive_scheduler import NotificationDispatcher, ProactiveScheduler
from strava_health_agent.strava_client import MockStravaClient


class DummyDispatcher(NotificationDispatcher):
    def __init__(self):
        super().__init__()
        self.dispatched = []

    def dispatch(self, feedback):
        self.dispatched.append(feedback)


class TestProactiveScheduler(unittest.TestCase):

    def setUp(self):
        self.athlete = AthleteProfile(athlete_id=1, firstname="Sam", lastname="Taylor")
        self.agent = StravaHealthAgent(self.athlete, memory=MemoryStore(":memory:"))
        self.client = MockStravaClient(scenario="danger_spike")
        self.dispatcher = DummyDispatcher()
        self.scheduler = ProactiveScheduler(
            self.agent,
            strava_client=self.client,
            dispatcher=self.dispatcher,
        )

    def test_morning_readiness_dispatch(self):
        fb = self.scheduler.run_morning_readiness_check()
        self.assertEqual(len(self.dispatcher.dispatched), 1)
        self.assertEqual(fb.feedback_type, FeedbackType.MORNING_READINESS)

    def test_watchdog_dispatch_on_spike(self):
        fb = self.scheduler.run_overtraining_watchdog()
        self.assertIsNotNone(fb)
        self.assertEqual(fb.feedback_type, FeedbackType.OVERTRAINING_WARNING)
        self.assertEqual(len(self.dispatcher.dispatched), 1)


if __name__ == "__main__":
    unittest.main()
