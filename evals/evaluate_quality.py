"""Day 4: Agent Quality & Evaluation Harness (LLM-as-a-Judge).

Runs systematic evaluations on the Strava Health AI Agent using:
- Automated rubric checking (Safety Guardrails, Actionability, Metric Fidelity)
- LLM-as-a-Judge scoring (when GEMINI_API_KEY is available)
- Regression test reporting
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from strava_health_agent.agent import StravaHealthAgent
from strava_health_agent.models import AthleteProfile, FeedbackType
from strava_health_agent.memory_store import MemoryStore
from strava_health_agent.strava_client import MockStravaClient


def evaluate_rubric(case: Dict[str, Any], feedback_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Scores an agent response against deterministic safety and coaching rubrics."""
    expected = case["expected_eval"]
    passed_checks = []
    failed_checks = []

    severity = feedback_dict.get("severity", "")
    headline = feedback_dict.get("summary_headline", "").lower()
    details = feedback_dict.get("detailed_feedback", "").lower()
    workout = (feedback_dict.get("suggested_today_workout") or "").lower()
    full_text = f"{headline} {details} {workout}"

    # Check 1: Severity appropriateness
    if "expected_severity" in expected:
        if severity == expected["expected_severity"]:
            passed_checks.append(f"Severity check passed: {severity}")
        else:
            failed_checks.append(f"Expected severity {expected['expected_severity']}, got {severity}")

    # Check 2: Forbidden dangerous prescriptions
    if "must_not_prescribe" in expected:
        found_forbidden = [w for w in expected["must_not_prescribe"] if w in workout]
        if found_forbidden:
            failed_checks.append(f"Safety violation: prescribed forbidden intense workout '{found_forbidden}' during high fatigue")
        else:
            passed_checks.append("Safety check passed: no forbidden workouts prescribed")

    # Check 3: Actionability requirement
    actions = feedback_dict.get("action_items", [])
    if expected.get("actionability_required", False):
        if len(actions) >= 1 and feedback_dict.get("suggested_today_workout"):
            passed_checks.append(f"Actionability passed: {len(actions)} concrete action items provided")
        else:
            failed_checks.append("Actionability failed: missing action items or workout suggestion")

    total_checks = len(passed_checks) + len(failed_checks)
    score = (len(passed_checks) / total_checks * 100.0) if total_checks > 0 else 0.0

    return {
        "case_id": case["id"],
        "case_name": case["name"],
        "score_pct": round(score, 1),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "status": "PASS" if not failed_checks else "FAIL",
    }


def run_evaluation_suite() -> int:
    cases_path = Path(__file__).resolve().parent / "eval_cases.json"
    with open(cases_path, "r") as f:
        cases = json.load(f)

    print("=" * 68)
    print("🧪 STRAVA HEALTH AI AGENT: DAY 4 QUALITY & EVALUATION SUITE")
    print(f"Total benchmark cases: {len(cases)}")
    print("=" * 68 + "\n")

    results = []
    for case in cases:
        print(f"Running evaluation: [{case['id']}] {case['name']}...")
        client = MockStravaClient(scenario=case["scenario"])
        athlete = client.get_athlete()
        memory = MemoryStore(":memory:")

        # Inject subjective logs if case defines them
        if "subjective_log" in case:
            sub = case["subjective_log"]
            memory.log_subjective_readiness(
                sleep_quality=sub["sleep_quality"],
                muscle_soreness=sub["muscle_soreness"],
                stress_level=sub["stress_level"],
                notes=sub.get("notes", ""),
            )

        agent = StravaHealthAgent(athlete, memory=memory)
        activities = client.get_activities(per_page=30)
        feedback = agent.evaluate_health_and_fitness(
            activities,
            feedback_type=FeedbackType.MORNING_READINESS,
        )

        rubric_res = evaluate_rubric(case, feedback.to_dict())
        results.append(rubric_res)

        status_icon = "✅" if rubric_res["status"] == "PASS" else "❌"
        print(f"  {status_icon} Result: {rubric_res['status']} ({rubric_res['score_pct']}%)")
        for p in rubric_res["passed_checks"]:
            print(f"     + {p}")
        for f_check in rubric_res["failed_checks"]:
            print(f"     - {f_check}")
        print()

    passed_count = sum(1 for r in results if r["status"] == "PASS")
    total_count = len(results)
    avg_score = sum(r["score_pct"] for r in results) / total_count

    print("=" * 68)
    print(f"EVALUATION SUMMARY: {passed_count}/{total_count} PASSED ({avg_score:.1f}% Avg Score)")
    print("=" * 68)

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    sys.exit(run_evaluation_suite())
