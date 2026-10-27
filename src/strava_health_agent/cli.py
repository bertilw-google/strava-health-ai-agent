"""Command Line Interface for Strava Health AI Agent."""

import argparse
import json
import os
import sys
from typing import Any, Optional, Tuple

from .agent import StravaHealthAgent
from .analytics import SportsScienceEngine
from .models import AthleteProfile, FeedbackType
from .memory_store import MemoryStore
from .proactive_scheduler import NotificationDispatcher, ProactiveScheduler
from .strava_client import MockStravaClient, StravaClient


def get_configured_agent(
    use_mock: bool = False,
    scenario: str = "danger_spike",
    db_path: str = "strava_health_memory.db",
) -> tuple[StravaHealthAgent, Any, MemoryStore]:
    memory = MemoryStore(db_path)

    # Check for live Strava environment variables
    has_live_creds = all(
        os.environ.get(k)
        for k in ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"]
    )

    if not use_mock and has_live_creds:
        client = StravaClient(
            client_id=os.environ["STRAVA_CLIENT_ID"],
            client_secret=os.environ["STRAVA_CLIENT_SECRET"],
            refresh_token=os.environ["STRAVA_REFRESH_TOKEN"],
        )
        try:
            athlete = client.get_athlete()
            memory.save_athlete_profile(athlete)
        except Exception:
            athlete = memory.get_athlete_profile() or MockStravaClient().get_athlete()
    else:
        client = MockStravaClient(scenario=scenario)
        athlete = client.get_athlete()
        memory.save_athlete_profile(athlete)

    agent = StravaHealthAgent(
        athlete=athlete,
        memory=memory,
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
    )
    return agent, client, memory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strava Health AI Agent - Proactive Health & Fitness Coach (AI in 5 Days)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: check (Morning Readiness)
    check_parser = subparsers.add_parser("check", help="Run proactive morning readiness check")
    check_parser.add_argument("--mock", action="store_true", help="Use mock Strava data")
    check_parser.add_argument("--scenario", default="danger_spike", choices=["danger_spike", "optimal_build", "taper_freshness"])

    # Command: triage (Post-Activity)
    triage_parser = subparsers.add_parser("triage", help="Run post-activity recovery triage")
    triage_parser.add_argument("--mock", action="store_true", help="Use mock Strava data")

    # Command: watchdog (Overtraining Scan)
    watchdog_parser = subparsers.add_parser("watchdog", help="Run continuous overtraining risk watchdog")
    watchdog_parser.add_argument("--mock", action="store_true", help="Use mock Strava data")

    # Command: metrics (Physiological status)
    metrics_parser = subparsers.add_parser("metrics", help="Print current sports science metrics (ATL, CTL, TSB, ACWR)")
    metrics_parser.add_argument("--scenario", default="danger_spike", choices=["danger_spike", "optimal_build", "taper_freshness"])

    # Command: log (Subjective inputs)
    log_parser = subparsers.add_parser("log", help="Log subjective athlete readiness to agent memory")
    log_parser.add_argument("--sleep", type=int, required=True, choices=[1, 2, 3, 4, 5], help="Sleep quality (1=poor, 5=excellent)")
    log_parser.add_argument("--soreness", type=int, required=True, choices=[1, 2, 3, 4, 5], help="Muscle soreness (1=none, 5=extreme)")
    log_parser.add_argument("--stress", type=int, required=True, choices=[1, 2, 3, 4, 5], help="Life stress level (1=low, 5=high)")
    log_parser.add_argument("--notes", type=str, default="", help="Notes on pain, soreness, or fatigue")

    # Command: demo
    demo_parser = subparsers.add_parser("demo", help="Run interactive 5-Day Agent scenario walkthrough")
    demo_parser.add_argument("--scenario", default="danger_spike", choices=["danger_spike", "optimal_build", "taper_freshness"])

    args = parser.parse_args()

    if not args.command or args.command == "demo":
        scenario = getattr(args, "scenario", "danger_spike")
        print("\n" + "#" * 68)
        print("🏃 STRAVA HEALTH AI AGENT: 5-DAY AI AGENTS INTENSIVE DEMO")
        print(f"Scenario: {scenario.upper()}")
        print("#" * 68)
        agent, client, memory = get_configured_agent(use_mock=True, scenario=scenario)
        scheduler = ProactiveScheduler(agent, client, NotificationDispatcher())
        scheduler.run_morning_readiness_check()
        return

    if args.command == "check":
        use_mock = args.mock or not os.environ.get("STRAVA_CLIENT_ID")
        scenario = getattr(args, "scenario", "danger_spike")
        agent, client, _ = get_configured_agent(use_mock=use_mock, scenario=scenario)
        scheduler = ProactiveScheduler(agent, client, NotificationDispatcher())
        scheduler.run_morning_readiness_check()

    elif args.command == "triage":
        use_mock = args.mock or not os.environ.get("STRAVA_CLIENT_ID")
        agent, client, _ = get_configured_agent(use_mock=use_mock)
        scheduler = ProactiveScheduler(agent, client, NotificationDispatcher())
        scheduler.run_post_activity_triage()

    elif args.command == "watchdog":
        use_mock = args.mock or not os.environ.get("STRAVA_CLIENT_ID")
        agent, client, _ = get_configured_agent(use_mock=use_mock)
        scheduler = ProactiveScheduler(agent, client, NotificationDispatcher())
        res = scheduler.run_overtraining_watchdog()
        if not res:
            print("✅ Watchdog check complete: No acute overtraining risk detected (ACWR in safe zone).")

    elif args.command == "metrics":
        agent, client, _ = get_configured_agent(use_mock=True, scenario=args.scenario)
        activities = client.get_activities(per_page=30)
        metrics = agent.analytics.compute_training_load(activities)
        print("\n" + "=" * 50)
        print("📊 PHYSIOLOGICAL TRAINING LOAD & READINESS")
        print("=" * 50)
        print(f"Athlete:                 {agent.athlete.firstname} {agent.athlete.lastname}")
        print(f"Acute Training Load (ATL):  {metrics.acute_training_load} (7-day fatigue)")
        print(f"Chronic Training Load (CTL): {metrics.chronic_training_load} (42-day fitness)")
        print(f"Training Stress Balance (TSB): {metrics.training_stress_balance} (Form)")
        print(f"Acute:Chronic Ratio (ACWR):    {metrics.acwr} -> {metrics.risk_zone}")
        print(f"Weekly Volume:           {metrics.weekly_total_km} km ({metrics.weekly_total_hours} hrs)")
        print(f"Weekly TRIMP Stress:     {metrics.weekly_trimp}")
        print(f"Recommended Recovery:    {metrics.rest_recommended_hours} hours")
        print("=" * 50 + "\n")

    elif args.command == "log":
        memory = MemoryStore()
        memory.log_subjective_readiness(
            sleep_quality=args.sleep,
            muscle_soreness=args.soreness,
            stress_level=args.stress,
            notes=args.notes,
        )
        print("✅ Logged athlete subjective metrics into agent memory store.")


if __name__ == "__main__":
    main()
