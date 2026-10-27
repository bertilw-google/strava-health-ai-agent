"""Day 5: Prototype to Production - Proactive Scheduling & Triggers.

Implements the proactive push loop that transforms a reactive chatbot into an
autonomous health agent:
- Morning Readiness Briefing (proactively guides daily training decisions)
- Post-Activity Triage (immediate recovery & refueling guidance after new uploads)
- Overtraining Watchdog (continuous check for dangerous ACWR spikes > 1.5)
- Multi-channel notification dispatcher (Console, Webhook, Email, File)
"""

import json
import logging
import time
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .agent import StravaHealthAgent
from .models import AlertSeverity, FeedbackType, HealthFeedback
from .strava_client import MockStravaClient, StravaClient

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches proactive health feedback across notification channels."""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    def dispatch(self, feedback: HealthFeedback) -> None:
        """Sends feedback to active notification targets."""
        # 1. Console / CLI display
        self._print_console(feedback)

        # 2. Webhook (Slack, Discord, custom HTTP endpoint)
        if self.webhook_url:
            self._send_webhook(feedback)

    def _print_console(self, fb: HealthFeedback) -> None:
        prefix = {
            AlertSeverity.INFO: "ℹ️ [INFO]",
            AlertSeverity.ADVISORY: "💡 [ADVISORY]",
            AlertSeverity.WARNING: "⚠️ [WARNING]",
            AlertSeverity.CRITICAL: "🚨 [CRITICAL ALERT]",
        }.get(fb.severity, "[UPDATE]")

        print("\n" + "=" * 68)
        print(f"{prefix} PROACTIVE HEALTH COACH NOTIFICATION")
        print(f"Timestamp: {fb.timestamp}")
        print(f"Type:      {fb.feedback_type.value}")
        print("-" * 68)
        print(f"HEADLINE:  {fb.summary_headline}\n")
        print(f"ANALYSIS:\n{fb.detailed_feedback}\n")
        if fb.suggested_today_workout:
            print(f"TODAY'S WORKOUT RECOMMENDATION:\n  -> {fb.suggested_today_workout}\n")
        if fb.suggested_recovery_protocol:
            print(f"RECOVERY PROTOCOL:\n  -> {fb.suggested_recovery_protocol}\n")
        if fb.action_items:
            print("ACTION ITEMS:")
            for item in fb.action_items:
                print(f"  [{item.priority}] {item.title}: {item.description}")
        print("=" * 68 + "\n")

    def _send_webhook(self, fb: HealthFeedback) -> None:
        if not self.webhook_url:
            return
        payload = json.dumps(fb.to_dict()).encode("utf-8")
        req = urllib.request.Request(self.webhook_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info("Webhook dispatched successfully: %s", resp.status)
        except Exception as e:
            logger.warning("Failed to dispatch webhook: %s", e)


class ProactiveScheduler:
    """Manages scheduled health checks and trigger evaluations."""

    def __init__(
        self,
        agent: StravaHealthAgent,
        strava_client: Optional[Any] = None,
        dispatcher: Optional[NotificationDispatcher] = None,
    ):
        self.agent = agent
        self.strava_client = strava_client or MockStravaClient()
        self.dispatcher = dispatcher or NotificationDispatcher()

    def run_morning_readiness_check(self) -> HealthFeedback:
        """Evaluates overnight readiness and prescribes today's training intensity."""
        activities = self.strava_client.get_activities(per_page=30)
        feedback = self.agent.evaluate_health_and_fitness(
            activities=activities,
            feedback_type=FeedbackType.MORNING_READINESS,
        )
        self.dispatcher.dispatch(feedback)
        return feedback

    def run_post_activity_triage(self, activity_id: Optional[int] = None) -> HealthFeedback:
        """Triggered immediately following a completed Strava upload."""
        activities = self.strava_client.get_activities(per_page=30)
        latest = activities[0] if activities else None
        feedback = self.agent.evaluate_health_and_fitness(
            activities=activities,
            feedback_type=FeedbackType.POST_ACTIVITY_TRIAGE,
            latest_activity=latest,
        )
        self.dispatcher.dispatch(feedback)
        return feedback

    def run_overtraining_watchdog(self) -> Optional[HealthFeedback]:
        """Runs a safety scan; only dispatches if fatigue is in Warning or Critical zone."""
        activities = self.strava_client.get_activities(per_page=30)
        metrics = self.agent.analytics.compute_training_load(activities)
        if metrics.acwr > 1.3 or metrics.training_stress_balance < -20.0:
            feedback = self.agent.evaluate_health_and_fitness(
                activities=activities,
                feedback_type=FeedbackType.OVERTRAINING_WARNING,
            )
            self.dispatcher.dispatch(feedback)
            return feedback
        return None

    def run_weekly_retrospective(self) -> HealthFeedback:
        """Comprehensive Sunday evening review of microcycle training load."""
        activities = self.strava_client.get_activities(per_page=30)
        feedback = self.agent.evaluate_health_and_fitness(
            activities=activities,
            feedback_type=FeedbackType.WEEKLY_RETROSPECTIVE,
        )
        self.dispatcher.dispatch(feedback)
        return feedback
