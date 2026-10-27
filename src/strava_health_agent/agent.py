"""Core AI Agent: Proactive Health & Fitness Coach.

Integrates:
- Day 1: Gemini Prompt Engineering & Structured JSON Output
- Day 2: Tool execution & physiological context ingestion
- Day 3: Context Engineering with Memory & Session History
"""

import json
import logging
import os
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .analytics import SportsScienceEngine
from .models import (
    Activity,
    AlertSeverity,
    AthleteProfile,
    FeedbackType,
    HealthFeedback,
    ProactiveAction,
    TrainingLoadMetrics,
)
from .memory_store import MemoryStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an elite Sports Scientist, Preventive Health Physician, and Endurance Performance Coach.
Your mission is to proactively analyze an athlete's Strava fitness metrics, physiological training load,
and subjective recovery status to give timely, proactive, actionable, and safe health guidance.

CRITICAL COACHING & SAFETY PRINCIPLES:
1. ACUTE:CHRONIC WORKLOAD RATIO (ACWR) RULES (Gabbett et al. Framework):
   - ACWR < 0.8: Under-training. Recommend gradual progressive overload.
   - ACWR 0.8 - 1.3: "Sweet Spot". Optimal adaptation, lowest injury risk. Encourage current plan.
   - ACWR 1.3 - 1.5: "Overreaching". Caution athlete to monitor sleep, resting HR, and muscle soreness.
   - ACWR > 1.5: "Danger Zone". Soft-tissue injury risk increases significantly. Proactively INTERVENE:
     recommend substituting high-intensity workouts with Zone 1 active recovery or complete rest.

2. TRAINING STRESS BALANCE (TSB = CTL - ATL):
   - TSB < -25: Severe fatigue. High risk of overtraining syndrome. Deload needed.
   - TSB -20 to -10: Productive training phase, but needs adequate 7-9 hours sleep and nutritional support.
   - TSB -10 to +10: Neutral / balanced fitness.
   - TSB +10 to +25: Fresh / tapered. Ready for race or breakthrough performance.

3. MEDICAL & SAFETY GUARDRAILS:
   - Provide physiological, evidence-based training advice, not definitive medical diagnoses.
   - If severe pain, sharp asymmetrical joint pain, dizziness, or cardiac palpitations are detected,
     immediately advise consultation with a licensed healthcare provider.

4. ACTIONABILITY:
   - Every piece of feedback MUST contain concrete, realistic next steps (e.g. exact recovery duration,
     target heart rate zone, carbohydrate/protein replenishment timing, mobility targets).

Always output valid JSON adhering strictly to the requested schema.
"""


class StravaHealthAgent:
    """AI Health Coach orchestrating athlete context, analytics, and Gemini generation."""

    def __init__(
        self,
        athlete: AthleteProfile,
        memory: Optional[MemoryStore] = None,
        gemini_api_key: Optional[str] = None,
        model_name: str = "gemini-2.0-flash",
    ):
        self.athlete = athlete
        self.memory = memory or MemoryStore(":memory:")
        self.analytics = SportsScienceEngine(athlete)
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name

    def _call_gemini_api(self, prompt: str) -> Optional[str]:
        """Calls Google Gemini REST API using urllib (zero external package requirement)."""
        if not self.gemini_api_key:
            return None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent?key={self.gemini_api_key}"
        )

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts:
                        return parts[0].get("text")
        except Exception as e:
            logger.warning("Gemini API call failed, falling back to rule-based engine: %s", e)

        return None

    def evaluate_health_and_fitness(
        self,
        activities: List[Activity],
        feedback_type: FeedbackType = FeedbackType.MORNING_READINESS,
        latest_activity: Optional[Activity] = None,
    ) -> HealthFeedback:
        """Evaluates health & fitness metrics and generates proactive feedback."""
        # 1. Update Memory
        self.memory.save_activities(activities, athlete_id=self.athlete.athlete_id)

        # 2. Compute Sports Science Metrics
        metrics = self.analytics.compute_training_load(activities)
        self.memory.record_training_load(metrics)

        # 3. Fetch Subjective History & Past Feedback from Memory (Day 3 Context Engineering)
        subjective_logs = self.memory.get_recent_subjective_logs(limit=3)
        past_feedback = self.memory.get_recent_feedback(limit=2)

        # 4. Attempt Gemini LLM Generation
        llm_response = None
        if self.gemini_api_key:
            context_summary = {
                "athlete": self.athlete.to_dict(),
                "training_load_metrics": metrics.to_dict(),
                "latest_activity": latest_activity.to_dict() if latest_activity else None,
                "recent_activities_count": len(activities[:7]),
                "recent_subjective_logs": subjective_logs,
                "feedback_type": feedback_type.value,
            }

            prompt = f"""{SYSTEM_PROMPT}

ATHLETE CONTEXT & PHYSIOLOGICAL DATA:
{json.dumps(context_summary, indent=2)}

Generate proactive health coaching feedback formatted as a JSON object matching this schema:
{{
  "severity": "info" | "advisory" | "warning" | "critical",
  "summary_headline": "Concise 1-sentence punchy headline summarizing physical status",
  "detailed_feedback": "Detailed sports science analysis explaining fatigue, cardiovascular strain, and health impact",
  "suggested_today_workout": "Specific workout or rest recommendation for today",
  "suggested_recovery_protocol": "Hydration, nutrition, sleep, or mobility advice",
  "action_items": [
    {{
      "title": "Action title",
      "description": "Concrete step",
      "priority": 1,
      "action_type": "rest" | "nutrition" | "workout_mod" | "hydration" | "mobility"
    }}
  ]
}}
"""
            llm_response = self._call_gemini_api(prompt)

        # 5. Parse Gemini response or use intelligent fallback rule-based coach
        if llm_response:
            try:
                parsed = json.loads(llm_response)
                actions = [
                    ProactiveAction(
                        title=a.get("title", "Action"),
                        description=a.get("description", ""),
                        priority=a.get("priority", 1),
                        action_type=a.get("action_type", "workout_mod"),
                    )
                    for a in parsed.get("action_items", [])
                ]
                feedback = HealthFeedback(
                    feedback_id=f"fb_{uuid.uuid4().hex[:8]}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    feedback_type=feedback_type,
                    severity=AlertSeverity(parsed.get("severity", "advisory")),
                    summary_headline=parsed.get("summary_headline", "Fitness Status Update"),
                    detailed_feedback=parsed.get("detailed_feedback", ""),
                    key_metrics=metrics.to_dict(),
                    action_items=actions,
                    suggested_today_workout=parsed.get("suggested_today_workout"),
                    suggested_recovery_protocol=parsed.get("suggested_recovery_protocol"),
                )
                self.memory.save_feedback(feedback)
                return feedback
            except Exception as e:
                logger.warning("Error parsing Gemini JSON output: %s", e)

        # Fallback Deterministic Engine
        return self._rule_based_coach(metrics, feedback_type, latest_activity)

    def _rule_based_coach(
        self,
        metrics: TrainingLoadMetrics,
        feedback_type: FeedbackType,
        latest_activity: Optional[Activity] = None,
    ) -> HealthFeedback:
        """Deterministic sports science rules engine fallback."""
        actions: List[ProactiveAction] = []

        if metrics.acwr > 1.5:
            severity = AlertSeverity.CRITICAL
            headline = f"⚠️ High Injury Risk: ACWR reached {metrics.acwr} (Danger Zone)"
            detail = (
                f"Your acute workload ({metrics.acute_training_load} ATL) has outpaced your chronic fitness base "
                f"({metrics.chronic_training_load} CTL) by {metrics.acwr:.2f}x. Training studies indicate a 2-4x surge in soft-tissue "
                f"and overuse injuries when ACWR exceeds 1.5. Your Training Stress Balance is {metrics.training_stress_balance} (severe fatigue)."
            )
            workout = "Mandatory Rest Day or 30-min Zone 1 active recovery walk / gentle spin."
            recovery = "Prioritize 8+ hours of sleep, elevate legs, and consume 20-30g of protein to facilitate repair."
            actions.append(
                ProactiveAction(
                    title="Cancel High-Intensity Sessions",
                    description="Convert planned tempo/interval workouts today into gentle Zone 1 movement or rest.",
                    priority=1,
                    action_type="rest",
                )
            )
            actions.append(
                ProactiveAction(
                    title="Soft Tissue & Mobility Work",
                    description="Spend 15 minutes with a foam roller focusing on calves, quads, and hips.",
                    priority=2,
                    action_type="mobility",
                )
            )

        elif metrics.acwr > 1.3:
            severity = AlertSeverity.WARNING
            headline = f"Overreaching Alert: ACWR at {metrics.acwr} - Monitor Fatigue"
            detail = (
                f"You have accumulated substantial fatigue (ATL: {metrics.acute_training_load}). "
                f"While you are building fitness, you are near the upper threshold of sustainable overload. "
                f"TSB is currently {metrics.training_stress_balance}."
            )
            workout = "Easy Aerobic Base (Zone 2) under 45 minutes; keep heart rate below 70% HRmax."
            recovery = "Replenish glycogen stores with complex carbohydrates and stay hydrated with electrolytes."
            actions.append(
                ProactiveAction(
                    title="Cap Workout Heart Rate",
                    description=f"Keep heart rate strictly under {int(self.athlete.max_hr * 0.70)} bpm today.",
                    priority=1,
                    action_type="workout_mod",
                )
            )

        elif metrics.acwr < 0.8:
            severity = AlertSeverity.INFO
            headline = f"Fresh & Rested: ACWR at {metrics.acwr} - Ready for Training Stimulus"
            detail = (
                f"Your chronic load has declined or your recent training volume was light. "
                f"Your Training Stress Balance is positive ({metrics.training_stress_balance}), indicating fresh legs. "
                f"You are well-primed for quality workouts without acute fatigue drag."
            )
            workout = "Quality interval session, tempo progression, or long aerobic build."
            recovery = "Standard post-workout hydration and balanced meal within 60 minutes."
            actions.append(
                ProactiveAction(
                    title="Safe Volume Overload",
                    description="You can safely increase training stimulus by 5-10% this week.",
                    priority=2,
                    action_type="workout_mod",
                )
            )

        else:
            severity = AlertSeverity.ADVISORY
            headline = f"Optimal Sweet Spot: ACWR at {metrics.acwr} (Balanced Progress)"
            detail = (
                f"Your training stimulus ({metrics.weekly_total_km} km / {metrics.weekly_total_hours} hrs this week) "
                f"is perfectly proportioned to your fitness base (CTL {metrics.chronic_training_load}). "
                f"Injury risk is minimized while endurance adaptation is maximized."
            )
            workout = "Maintain current training block schedule as planned."
            recovery = "Consistent sleep routine and regular post-run stretching."
            actions.append(
                ProactiveAction(
                    title="Maintain Rhythm",
                    description="Continue following your current structured progression.",
                    priority=3,
                    action_type="workout_mod",
                )
            )

        feedback = HealthFeedback(
            feedback_id=f"fb_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            feedback_type=feedback_type,
            severity=severity,
            summary_headline=headline,
            detailed_feedback=detail,
            key_metrics=metrics.to_dict(),
            action_items=actions,
            suggested_today_workout=workout,
            suggested_recovery_protocol=recovery,
        )
        self.memory.save_feedback(feedback)
        return feedback
