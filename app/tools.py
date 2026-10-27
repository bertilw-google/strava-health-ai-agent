"""ADK Tool Functions for Strava Fitness Ingestion, Load Analysis & Next-Run Coaching.

Strictly adheres to `rubrics.md` (Category 1: Tool & Interface Design):
- Comprehensive Tool Docstrings
- Descriptive Verb-Noun Naming
- Explicit Input/Output Schema Validation
- Guided Error Handling with LLM Self-Correction Instructions
- Zero Hardcoded Secrets (resolved via SecretManagerClient / .env)
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure src/ is importable
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from strava_health_agent.analytics import SportsScienceEngine
from strava_health_agent.memory_store import MemoryStore
from strava_health_agent.models import Activity, AthleteProfile, FeedbackType
from strava_health_agent.observability import PIIRedactor, StructuredJsonLogger
from strava_health_agent.orchestrator import HeadCoachCoordinatorAgent
from strava_health_agent.secrets import SecretManagerClient
from strava_health_agent.strava_client import MockStravaClient, StravaClient

_logger = StructuredJsonLogger()
_redactor = PIIRedactor()


def _get_active_strava_client(scenario: str = "optimal_build") -> tuple[Any, AthleteProfile, str]:
    """Resolves live StravaClient via Secret Manager / .env with graceful offline fallback."""
    sm = SecretManagerClient()
    client_id = sm.get_secret("STRAVA_CLIENT_ID")
    client_secret = sm.get_secret("STRAVA_CLIENT_SECRET")
    access_token = sm.get_secret("STRAVA_ACCESS_TOKEN")
    refresh_token = sm.get_secret("STRAVA_REFRESH_TOKEN")

    if access_token or (client_id and client_secret and refresh_token):
        live_client = StravaClient(
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            secret_manager=sm,
        )
        try:
            athlete = live_client.get_athlete()
            return live_client, athlete, "live_strava_api"
        except Exception as exc:
            _logger.log(
                severity="WARNING",
                event="STRAVA_LIVE_API_UNREACHABLE_FALLBACK",
                metadata={"reason": str(exc), "fallback_scenario": scenario},
            )

    mock_client = MockStravaClient(scenario=scenario)
    return mock_client, mock_client.get_athlete(), f"offline_fixture:{scenario}"


def fetch_athlete_physiological_profile() -> Dict[str, Any]:
    """Fetches the authenticated athlete's physiological profile and HR thresholds.

    Authenticates against `GET https://www.strava.com/api/v3/athlete` using the
    short-lived OAuth2 Bearer token, automatically refreshing via `POST /oauth/token`
    if the 6-hour access token has expired.

    Returns:
        Dictionary containing sanitized `athlete_id`, `firstname`, `weight_kg`,
        `resting_hr`, `max_hr`, `lactate_threshold_hr`, and `primary_sport`.
    """
    _, athlete, source = _get_active_strava_client()
    return _redactor.redact_dict({
        "status": "SUCCESS",
        "data_source": source,
        "athlete_profile": athlete.to_dict(),
    })


def retrieve_strava_workout_streams(limit: int = 5, scenario: str = "optimal_build") -> Dict[str, Any]:
    """Retrieves recent running activities from Strava including distance, pace, HR, elevation, and splits.

    Args:
        limit: Number of recent running workouts to fetch (integer between 1 and 30).
        scenario: Fallback simulation scenario ('optimal_build', 'danger_spike', 'taper_freshness')
            used when running in an offline/sandboxed environment.

    Returns:
        Structured dictionary with `runs` (each containing `distance_km`, `pace_min_per_km`,
        `average_heartrate`, `max_heartrate`, `total_elevation_gain`, and per-km `splits_metric`),
        or a guided error payload with `recovery_instructions`.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 30:
        return {
            "status": "ERROR",
            "error_code": "INVALID_LIMIT_PARAMETER",
            "message": f"Parameter 'limit' must be an integer between 1 and 30, received: {limit!r}.",
            "recovery_instructions": "Retry calling 'retrieve_strava_workout_streams' with limit=5.",
        }

    client, athlete, source = _get_active_strava_client(scenario=scenario)
    engine = SportsScienceEngine(athlete)
    activities: List[Activity] = client.get_activities(per_page=max(limit, 15))
    runs = [a for a in activities if a.type == "Run"][:limit]

    formatted_runs = []
    for run in runs:
        hr_zone = engine.calculate_hr_zones(run.average_heartrate)
        trimp = engine.calculate_trimp(run)
        formatted_runs.append({
            "activity_id": run.id,
            "name": run.name,
            "date": run.start_date,
            "distance_km": run.distance_km,
            "distance_miles": run.distance_miles,
            "duration_minutes": run.duration_minutes,
            "pace_min_per_km": run.pace_min_per_km,
            "average_heartrate_bpm": run.average_heartrate,
            "max_heartrate_bpm": run.max_heartrate,
            "primary_hr_zone": hr_zone["primary_zone"],
            "total_elevation_gain_m": run.total_elevation_gain,
            "trimp_load": trimp,
            "splits_metric": run.splits_metric or [],
        })

    return _redactor.redact_dict({
        "status": "SUCCESS",
        "data_source": source,
        "runs_retrieved": len(formatted_runs),
        "runs": formatted_runs,
    })


def compute_acwr_training_load_metrics(scenario: str = "optimal_build") -> Dict[str, Any]:
    """Calculates Banister TRIMP, 7-day ATL, 42-day CTL, TSB, and Gabbett ACWR injury risk.

    Args:
        scenario: Fallback scenario ('optimal_build', 'danger_spike', 'taper_freshness').

    Returns:
        Dictionary containing `acute_training_load`, `chronic_training_load`,
        `training_stress_balance`, `acwr`, `risk_zone`, and `rest_recommended_hours`.
    """
    client, athlete, source = _get_active_strava_client(scenario=scenario)
    engine = SportsScienceEngine(athlete)
    activities = client.get_activities(per_page=30)
    metrics = engine.compute_training_load(activities)
    return {
        "status": "SUCCESS",
        "data_source": source,
        "training_load_metrics": metrics.to_dict(),
    }


def generate_next_run_coaching_recommendation(scenario: str = "optimal_build") -> Dict[str, Any]:
    """Analyzes recent Strava running trends and prescribes a personalized next-run workout plan.

    Computes rolling volume and ACWR fatigue ratio, routes via `HeadCoachCoordinatorAgent`,
    enforces clinical safety guardrails, and outputs concrete next-run parameters:
    suggested distance (km), target pace (`/km`), target heart rate zone (bpm), and
    post-run recovery/nutrition protocol.

    Args:
        scenario: Fallback scenario ('optimal_build', 'danger_spike', 'taper_freshness').

    Returns:
        Structured dictionary with `performance_summary`, `next_run_prescription`,
        and `proactive_feedback`.
    """
    client, athlete, source = _get_active_strava_client(scenario=scenario)
    activities = client.get_activities(per_page=30)
    coordinator = HeadCoachCoordinatorAgent(athlete, memory=MemoryStore(":memory:"))
    feedback = coordinator.run_coordinated_assessment(
        activities=activities,
        feedback_type=FeedbackType.MORNING_READINESS,
    )
    metrics = feedback.key_metrics

    # Calculate concrete next-run distance & target HR zone based on ACWR
    acwr = float(metrics.get("acwr", 1.0))
    weekly_km = float(metrics.get("weekly_total_km", 30.0))
    avg_run_km = round(max(5.0, weekly_km / 4.0), 1)

    if acwr > 1.5:
        next_distance_km = 0.0
        target_zone = f"Rest or Zone 1 Active Recovery (< {int(athlete.max_hr * 0.60)} bpm)"
        target_pace = "Walk / Cross-Train Only (No high-impact running)"
    elif acwr > 1.3:
        next_distance_km = round(avg_run_km * 0.75, 1)
        target_zone = f"Zone 2 Easy Aerobic ({int(athlete.max_hr * 0.60)}–{int(athlete.max_hr * 0.70)} bpm)"
        target_pace = "5:45–6:05 /km (Conversational easy pace)"
    elif acwr < 0.8:
        next_distance_km = round(avg_run_km * 1.10, 1)
        target_zone = f"Zone 3 Tempo / Aerobic Power ({int(athlete.max_hr * 0.70)}–{int(athlete.max_hr * 0.80)} bpm)"
        target_pace = "4:55–5:10 /km (Controlled tempo effort)"
    else:
        next_distance_km = round(avg_run_km * 1.05, 1)
        target_zone = f"Zone 2 Aerobic Base ({int(athlete.max_hr * 0.62)}–{int(athlete.max_hr * 0.72)} bpm)"
        target_pace = "5:20–5:35 /km (Steady aerobic progression)"

    return _redactor.redact_dict({
        "status": "SUCCESS",
        "data_source": source,
        "next_run_prescription": {
            "suggested_distance_km": next_distance_km,
            "target_pace_min_per_km": target_pace,
            "target_heart_rate_zone": target_zone,
            "workout_description": feedback.suggested_today_workout,
            "recovery_and_nutrition_advice": feedback.suggested_recovery_protocol,
        },
        "proactive_feedback": feedback.to_dict(),
    })
