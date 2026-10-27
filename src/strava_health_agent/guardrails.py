"""Category 3: Guardrails, Self-Evaluation Policy Plugins & Human-in-the-Loop (HITL) Hooks.

Implements:
- `SafetyAndPolicyGuardrailPlugin`: Pre-execution and post-generation self-evaluation guardrails
  ensuring medical disclaimers and ACWR injury prevention compliance.
- `HumanInTheLoopHook`: Explicit code stops requiring human confirmation before executing
  high-stakes actions (such as modifying training schedules or cancelling key workouts).
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import AlertSeverity, HealthFeedback, ProactiveAction, TrainingLoadMetrics


@dataclass
class GuardrailValidationResult:
    """Result of a policy or self-evaluation guardrail check."""
    passed: bool
    policy_name: str
    violations: List[str]
    remediated_feedback: Optional[HealthFeedback] = None


class SafetyAndPolicyGuardrailPlugin:
    """ADK-style Guardrail & Self-Evaluation Plugin for clinical and sports science safety."""

    FORBIDDEN_HIGH_INTENSITY_TERMS = [
        "all-out sprint",
        "vo2max intervals",
        "max effort",
        "100% effort",
        "race pace",
        "heavy plyometrics",
    ]

    ACUTE_MEDICAL_SYMPTOMS = [
        "chest pain",
        "heart palpitations",
        "fainting",
        "syncope",
        "sharp stabbing pain",
        "numbness",
        "shortness of breath at rest",
    ]

    def validate_and_self_evaluate(
        self,
        feedback: HealthFeedback,
        metrics: TrainingLoadMetrics,
        subjective_notes: str = "",
    ) -> GuardrailValidationResult:
        """Executes self-evaluation and safety guardrails on generated coaching advice.

        Enforces:
        1. ACWR > 1.5 Danger Zone Policy: Prohibits high-intensity prescriptions.
        2. Acute Medical Symptom Policy: Enforces mandatory physician referral.
        3. Actionability Self-Eval: Ensures concrete action items are attached.
        """
        violations: List[str] = []
        workout_lower = (feedback.suggested_today_workout or "").lower()
        notes_lower = subjective_notes.lower()

        # Policy 1: ACWR > 1.5 Overtraining Guardrail
        if metrics.acwr > 1.5:
            for term in self.FORBIDDEN_HIGH_INTENSITY_TERMS:
                if term in workout_lower:
                    violations.append(
                        f"ACWR Danger Zone Violation: Prescribed '{term}' while ACWR={metrics.acwr} (>1.5)."
                    )
                    # Auto-remediate unsafe LLM output
                    feedback.suggested_today_workout = (
                        "[GUARDRAIL OVERRIDE] Mandatory Rest Day or 30-min Zone 1 Active Recovery."
                    )
                    feedback.severity = AlertSeverity.CRITICAL

        # Policy 2: Medical Boundary & Red Flag Symptom Guardrail
        detected_symptoms = [s for s in self.ACUTE_MEDICAL_SYMPTOMS if s in notes_lower]
        if detected_symptoms:
            disclaimer = (
                "MEDICAL SAFETY NOTICE: You reported acute symptoms "
                f"({', '.join(detected_symptoms)}). Cease training immediately and consult a licensed physician."
            )
            if "physician" not in feedback.detailed_feedback.lower() and "doctor" not in feedback.detailed_feedback.lower():
                violations.append("Missing mandatory medical referral for acute symptoms.")
                feedback.detailed_feedback = f"{disclaimer}\n\n{feedback.detailed_feedback}"
                feedback.severity = AlertSeverity.CRITICAL
                feedback.suggested_today_workout = "Complete Rest & Medical Evaluation."

        # Policy 3: Self-Evaluation of Actionability
        if not feedback.action_items:
            violations.append("Self-Eval Violation: Output lacked concrete action items.")
            feedback.action_items.append(
                ProactiveAction(
                    title="Monitor Readiness",
                    description="Log resting heart rate and sleep quality tomorrow morning.",
                    priority=2,
                    action_type="rest",
                )
            )

        return GuardrailValidationResult(
            passed=len(violations) == 0,
            policy_name="ClinicalAndSportsScienceSafetyGuardrail",
            violations=violations,
            remediated_feedback=feedback,
        )


class HumanInTheLoopHook:
    """Explicit Human-in-the-Loop (HITL) gate for high-stakes agent actions.

    High-stakes actions (such as overriding an athlete's race-week schedule, pushing
    urgent medical/critical alerts to external webhooks, or deleting training blocks)
    pause execution and require explicit human approval.
    """

    HIGH_STAKES_ACTIONS = {
        "modify_training_plan_calendar",
        "cancel_scheduled_workout",
        "dispatch_critical_health_escalation",
        "purge_athlete_memory",
    }

    def __init__(
        self,
        interactive: bool = False,
        approval_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    ):
        self.interactive = interactive
        self.approval_callback = approval_callback
        self.approval_audit_log: List[Dict[str, Any]] = []

    def require_confirmation(
        self,
        action_name: str,
        payload: Dict[str, Any],
        severity: AlertSeverity,
    ) -> Tuple[bool, str]:
        """Pauses execution to verify human approval for high-stakes actions."""
        is_high_stakes = (
            action_name in self.HIGH_STAKES_ACTIONS
            or severity == AlertSeverity.CRITICAL
        )

        if not is_high_stakes:
            return True, "Auto-approved (low-stakes operation)."

        if self.approval_callback is not None:
            approved = self.approval_callback(action_name, payload)
            reason = "Approved via HITL callback." if approved else "Rejected by human operator."
        elif self.interactive:
            prompt_msg = (
                f"[HITL CONFIRMATION REQUIRED] Action '{action_name}' "
                f"(Severity: {severity.value}). Approve execution? [y/N]: "
            )
            user_input = input(prompt_msg).strip().lower()
            approved = user_input in ("y", "yes")
            reason = "Approved interactively by user." if approved else "Aborted by user."
        else:
            # Non-interactive safe default: stage action as pending human confirmation
            approved = False
            reason = (
                f"Execution paused: High-stakes action '{action_name}' staged for "
                "Human-in-the-Loop confirmation."
            )

        self.approval_audit_log.append({
            "action_name": action_name,
            "severity": severity.value,
            "approved": approved,
            "reason": reason,
        })
        return approved, reason
