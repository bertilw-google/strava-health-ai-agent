"""Category 3: Multi-Agent Orchestration Patterns & Strategic Model Routing.

Implements:
- `ModelRouter`: Routes fast operational tasks to `gemini-2.0-flash` and complex
  periodization / multi-factor injury synthesis to `gemini-2.5-pro`.
- Multi-Agent Coordinator & Sequential Pipeline Pattern (ADK architecture):
  1. `PhysiologyAnalystAgent`: Computes and interprets TRIMP, ATL, CTL, TSB.
  2. `InjuryPreventionSpecialistAgent`: Evaluates Gabbett ACWR and musculoskeletal risk.
  3. `NutritionAndRecoveryAgent`: Calculates glycogen, protein, and sleep protocols.
  4. `HeadCoachCoordinatorAgent`: Orchestrates specialist sub-agents, enforces
     guardrails, and synthesizes the final `HealthFeedback`.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .agent import StravaHealthAgent
from .analytics import SportsScienceEngine
from .guardrails import HumanInTheLoopHook, SafetyAndPolicyGuardrailPlugin
from .memory_store import MemoryStore
from .models import (
    Activity,
    AlertSeverity,
    AthleteProfile,
    FeedbackType,
    HealthFeedback,
    TrainingLoadMetrics,
)
from .observability import DistributedTracer, StructuredJsonLogger


@dataclass
class RoutingDecision:
    """Represents a strategic model selection decision."""
    task_type: str
    selected_model: str
    complexity_tier: str
    rationale: str


class StrategicModelRouter:
    """Routes requests between Flash (low-latency) and Pro (deep reasoning) models."""

    FAST_MODEL = "gemini-2.0-flash"
    REASONING_MODEL = "gemini-2.5-pro"

    HIGH_COMPLEXITY_TASKS = {
        FeedbackType.OVERTRAINING_WARNING.value,
        FeedbackType.WEEKLY_RETROSPECTIVE.value,
        "multi_week_periodization",
        "injury_root_cause_synthesis",
    }

    def select_model(
        self,
        task_type: str,
        acwr: float = 1.0,
        has_acute_symptoms: bool = False,
    ) -> RoutingDecision:
        """Selects the optimal Gemini model based on task complexity and risk profile."""
        if has_acute_symptoms or acwr > 1.5 or task_type in self.HIGH_COMPLEXITY_TASKS:
            return RoutingDecision(
                task_type=task_type,
                selected_model=self.REASONING_MODEL,
                complexity_tier="HIGH_COMPLEXITY_REASONING",
                rationale=(
                    f"Routed to {self.REASONING_MODEL} due to high clinical/periodization "
                    f"complexity (task={task_type}, ACWR={acwr})."
                ),
            )
        return RoutingDecision(
            task_type=task_type,
            selected_model=self.FAST_MODEL,
            complexity_tier="LOW_LATENCY_OPERATIONAL",
            rationale=(
                f"Routed to {self.FAST_MODEL} for low-latency routine readiness check "
                f"(task={task_type}, ACWR={acwr})."
            ),
        )


class PhysiologyAnalystAgent:
    """Sub-Agent 1: Specializes in cardiovascular load (TRIMP, ATL, CTL, TSB)."""

    def __init__(self, athlete: AthleteProfile):
        self.engine = SportsScienceEngine(athlete)

    def analyze(self, activities: List[Activity]) -> Dict[str, Any]:
        metrics = self.engine.compute_training_load(activities)
        latest_hr_zone = (
            self.engine.calculate_hr_zones(activities[0].average_heartrate)
            if activities else {"primary_zone": "Unknown"}
        )
        return {
            "agent": "PhysiologyAnalystAgent",
            "metrics": metrics,
            "latest_hr_zone": latest_hr_zone,
            "aerobic_status": (
                "Productive Overload" if -20 <= metrics.training_stress_balance <= 0
                else "Fatigued" if metrics.training_stress_balance < -20
                else "Fresh / Tapered"
            ),
        }


class InjuryPreventionSpecialistAgent:
    """Sub-Agent 2: Specializes in Gabbett ACWR thresholds and musculoskeletal strain."""

    def evaluate_risk(
        self,
        metrics: TrainingLoadMetrics,
        subjective_logs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        max_soreness = max((log.get("muscle_soreness", 1) for log in subjective_logs), default=1)
        notes = " ".join(log.get("notes", "") for log in subjective_logs)

        if metrics.acwr > 1.5 or max_soreness >= 5:
            risk_level = "CRITICAL"
            directive = "Immediate deload required; substitute high-impact running with rest or Zone 1."
        elif metrics.acwr > 1.3 or max_soreness == 4:
            risk_level = "WARNING"
            directive = "Cap volume and avoid back-to-back threshold sessions."
        else:
            risk_level = "LOW"
            directive = "Musculoskeletal load within safe progression corridor."

        return {
            "agent": "InjuryPreventionSpecialistAgent",
            "risk_level": risk_level,
            "acwr": metrics.acwr,
            "max_soreness": max_soreness,
            "combined_notes": notes,
            "clinical_directive": directive,
        }


class NutritionAndRecoveryAgent:
    """Sub-Agent 3: Formulates evidence-based refueling, hydration, and sleep protocols."""

    def __init__(self, athlete: AthleteProfile):
        self.athlete = athlete

    def prescribe_recovery(self, metrics: TrainingLoadMetrics) -> Dict[str, Any]:
        carbs_g = round(self.athlete.weight_kg * (1.2 if metrics.acwr > 1.3 else 0.8), 0)
        protein_g = round(self.athlete.weight_kg * 0.4, 0)
        hydration_ml = round(metrics.weekly_total_hours * 150 + 500, 0)
        return {
            "agent": "NutritionAndRecoveryAgent",
            "post_workout_carbs_g": carbs_g,
            "post_workout_protein_g": protein_g,
            "target_hydration_ml": hydration_ml,
            "sleep_target_hours": 8.5 if metrics.acwr > 1.3 else 7.5,
        }


class HeadCoachCoordinatorAgent:
    """ADK-style Coordinator Agent orchestrating specialist sub-agents, model routing, and guardrails."""

    def __init__(
        self,
        athlete: AthleteProfile,
        memory: Optional[MemoryStore] = None,
        logger: Optional[StructuredJsonLogger] = None,
        tracer: Optional[DistributedTracer] = None,
        hitl_hook: Optional[HumanInTheLoopHook] = None,
    ):
        self.athlete = athlete
        self.memory = memory or MemoryStore(":memory:")
        self.logger = logger or StructuredJsonLogger()
        self.tracer = tracer or DistributedTracer(self.logger)
        self.router = StrategicModelRouter()
        self.guardrail = SafetyAndPolicyGuardrailPlugin()
        self.hitl_hook = hitl_hook or HumanInTheLoopHook(interactive=False)

        # Sub-agents
        self.physiology_agent = PhysiologyAnalystAgent(athlete)
        self.injury_agent = InjuryPreventionSpecialistAgent()
        self.nutrition_agent = NutritionAndRecoveryAgent(athlete)
        self.core_agent = StravaHealthAgent(athlete, memory=self.memory)

    def run_coordinated_assessment(
        self,
        activities: List[Activity],
        feedback_type: FeedbackType = FeedbackType.MORNING_READINESS,
    ) -> HealthFeedback:
        """Executes the sequential/parallel multi-agent workflow with full tracing."""
        start_ts = time.time()
        with self.tracer.start_as_current_span(
            "HeadCoachCoordinatorAgent.run_coordinated_assessment",
            attributes={"athlete_id": self.athlete.athlete_id, "feedback_type": feedback_type.value},
        ) as root_span:
            # 1. Log Intent before execution
            self.logger.log_intent(
                action_name="run_coordinated_assessment",
                intended_inputs={"activities_count": len(activities), "feedback_type": feedback_type.value},
                rationale="Orchestrate specialist sub-agents to evaluate athlete readiness and prevent injury.",
                trace_id=root_span.trace_id,
                span_id=root_span.span_id,
            )

            # 2. Sub-Agent 1: Physiology Analysis
            with self.tracer.start_as_current_span("PhysiologyAnalystAgent.analyze"):
                physio_report = self.physiology_agent.analyze(activities)
                metrics: TrainingLoadMetrics = physio_report["metrics"]

            # 3. Sub-Agent 2: Injury Risk Evaluation
            with self.tracer.start_as_current_span("InjuryPreventionSpecialistAgent.evaluate_risk"):
                subjective_logs = self.memory.get_recent_subjective_logs(limit=5)
                injury_report = self.injury_agent.evaluate_risk(metrics, subjective_logs)

            # 4. Sub-Agent 3: Nutrition & Recovery Prescription
            with self.tracer.start_as_current_span("NutritionAndRecoveryAgent.prescribe_recovery"):
                recovery_report = self.nutrition_agent.prescribe_recovery(metrics)

            # 5. Strategic Model Routing
            with self.tracer.start_as_current_span("StrategicModelRouter.select_model") as route_span:
                routing = self.router.select_model(
                    task_type=feedback_type.value,
                    acwr=metrics.acwr,
                    has_acute_symptoms=(injury_report["risk_level"] == "CRITICAL"),
                )
                self.core_agent.model_name = routing.selected_model
                route_span.set_attribute("selected_model", routing.selected_model)
                route_span.set_attribute("complexity_tier", routing.complexity_tier)

            # 6. Synthesize via Core Agent
            with self.tracer.start_as_current_span("StravaHealthAgent.evaluate_health_and_fitness"):
                feedback = self.core_agent.evaluate_health_and_fitness(
                    activities=activities,
                    feedback_type=feedback_type,
                )
                feedback.key_metrics["routed_model"] = routing.selected_model
                feedback.key_metrics["nutrition_target"] = recovery_report

            # 7. Guardrail & Policy Self-Evaluation
            with self.tracer.start_as_current_span("SafetyAndPolicyGuardrailPlugin.validate"):
                validation = self.guardrail.validate_and_self_evaluate(
                    feedback=feedback,
                    metrics=metrics,
                    subjective_notes=injury_report["combined_notes"],
                )
                if validation.remediated_feedback:
                    feedback = validation.remediated_feedback

            # 8. Human-in-the-Loop Gate for Critical Escalations
            if feedback.severity == AlertSeverity.CRITICAL:
                with self.tracer.start_as_current_span("HumanInTheLoopHook.require_confirmation"):
                    approved, reason = self.hitl_hook.require_confirmation(
                        action_name="modify_training_plan_calendar",
                        payload={"acwr": metrics.acwr, "workout": feedback.suggested_today_workout},
                        severity=feedback.severity,
                    )
                    feedback.key_metrics["hitl_approved"] = approved
                    feedback.key_metrics["hitl_status"] = reason

            # 9. Log Outcome after completion
            latency_ms = (time.time() - start_ts) * 1000.0
            self.logger.log_outcome(
                action_name="run_coordinated_assessment",
                status="SUCCESS",
                actual_output={
                    "feedback_id": feedback.feedback_id,
                    "severity": feedback.severity.value,
                    "routed_model": routing.selected_model,
                    "acwr": metrics.acwr,
                },
                latency_ms=latency_ms,
                trace_id=root_span.trace_id,
                span_id=root_span.span_id,
            )

            return feedback
