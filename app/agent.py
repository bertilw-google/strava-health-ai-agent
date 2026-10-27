"""ADK Root Agent Definition for Strava Health AI Agent.

Integrates Google ADK (`google.adk.agents.Agent` & `google.adk.apps.App`) with
graceful standalone fallback when executed in minimal Python environments.
"""

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from strava_health_agent.agent import SYSTEM_PROMPT
from .tools import (
    compute_acwr_training_load_metrics,
    fetch_athlete_physiological_profile,
    generate_next_run_coaching_recommendation,
    retrieve_strava_workout_streams,
)

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

AGENT_TOOLS: List[Callable[..., Any]] = [
    fetch_athlete_physiological_profile,
    retrieve_strava_workout_streams,
    compute_acwr_training_load_metrics,
    generate_next_run_coaching_recommendation,
]

try:
    from google.adk.agents import Agent  # type: ignore
    from google.adk.apps import App  # type: ignore

    root_agent = Agent(
        name="strava_health_ai_agent",
        model="gemini-2.0-flash",
        instruction=SYSTEM_PROMPT,
        tools=AGENT_TOOLS,
    )
    app = App(
        root_agent=root_agent,
        name="app",
    )
except ImportError:
    class _StandaloneADKAgent:
        """Lightweight ADK-compatible Agent wrapper for zero-dependency execution."""

        def __init__(self, name: str, model: str, instruction: str, tools: List[Callable[..., Any]]):
            self.name = name
            self.model = model
            self.instruction = instruction
            self.tools = tools

        def run_query(self, prompt: str, scenario: str = "optimal_build") -> Dict[str, Any]:
            profile = fetch_athlete_physiological_profile()
            workouts = retrieve_strava_workout_streams(limit=5, scenario=scenario)
            load = compute_acwr_training_load_metrics(scenario=scenario)
            coaching = generate_next_run_coaching_recommendation(scenario=scenario)
            return {
                "prompt": prompt,
                "agent": self.name,
                "model": coaching["proactive_feedback"]["key_metrics"].get("routed_model", self.model),
                "athlete_profile": profile["athlete_profile"],
                "recent_runs": workouts["runs"],
                "training_load_metrics": load["training_load_metrics"],
                "next_run_prescription": coaching["next_run_prescription"],
                "proactive_feedback": coaching["proactive_feedback"],
            }

    class _StandaloneADKApp:
        def __init__(self, root_agent: _StandaloneADKAgent, name: str = "app"):
            self.root_agent = root_agent
            self.name = name

    root_agent = _StandaloneADKAgent(
        name="strava_health_ai_agent",
        model="gemini-2.0-flash",
        instruction=SYSTEM_PROMPT,
        tools=AGENT_TOOLS,
    )
    app = _StandaloneADKApp(root_agent=root_agent, name="app")
