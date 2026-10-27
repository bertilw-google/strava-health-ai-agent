"""Day 2: Model Context Protocol (MCP) Server for Strava Health.

Implements Category 1 (Tool & Interface Design) of the AgentOps Code Review Matrix:
- Comprehensive Tool Docstrings (purpose, parameters, return types, recovery paths)
- Descriptive Naming (domain-specific action verbs)
- Explicit Input & Output JSON Schemas (strict argument validation)
- Guided Error Handling (returns actionable recovery instructions to the LLM on failure)
"""

import json
import logging
import sys
from typing import Any, Dict, List, Optional

from .agent import StravaHealthAgent
from .memory_store import MemoryStore
from .models import AthleteProfile, FeedbackType
from .strava_client import MockStravaClient, StravaClient

logger = logging.getLogger(__name__)


class StravaHealthMCPServer:
    """Standardized MCP Server exposing Strava Health tools with strict schemas and guided errors."""

    TOOLS = [
        {
            "name": "fetch_athlete_physiological_profile",
            "description": (
                "Fetches the authenticated athlete's physiological baseline profile, including "
                "resting heart rate, maximum heart rate, lactate threshold heart rate, functional "
                "threshold power (FTP), body weight in kg, and weekly training volume targets."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "required": ["athlete_id", "firstname", "resting_hr", "max_hr", "primary_sport"],
                "properties": {
                    "athlete_id": {"type": "integer"},
                    "firstname": {"type": "string"},
                    "lastname": {"type": "string"},
                    "weight_kg": {"type": "number"},
                    "resting_hr": {"type": "integer"},
                    "max_hr": {"type": "integer"},
                    "lactate_threshold_hr": {"type": "integer"},
                    "primary_sport": {"type": "string"},
                },
            },
        },
        {
            "name": "retrieve_strava_workout_streams",
            "description": (
                "Retrieves recent normalized Strava workout records including distance (km/miles), "
                "moving duration, elevation gain, average/max heart rate, pace, and suffer score."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 10,
                        "description": "Maximum number of recent Strava workouts to return (1-100).",
                    }
                },
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "name", "type", "start_date", "distance_km", "duration_minutes"],
                },
            },
        },
        {
            "name": "compute_acwr_training_load_metrics",
            "description": (
                "Calculates clinical sports science load metrics: Banister TRIMP, 7-day Acute Training "
                "Load (ATL), 42-day Chronic Training Load (CTL), Training Stress Balance (TSB), and "
                "Gabbett Acute:Chronic Workload Ratio (ACWR) with injury risk categorization."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "required": ["acute_training_load", "chronic_training_load", "training_stress_balance", "acwr", "risk_zone"],
                "properties": {
                    "acute_training_load": {"type": "number"},
                    "chronic_training_load": {"type": "number"},
                    "training_stress_balance": {"type": "number"},
                    "acwr": {"type": "number"},
                    "risk_zone": {"type": "string"},
                    "rest_recommended_hours": {"type": "integer"},
                },
            },
        },
        {
            "name": "generate_proactive_injury_prevention_plan",
            "description": (
                "Executes the AI Health Coach reasoning loop over physiological training loads and "
                "subjective readiness logs to generate a proactive workout modification and recovery protocol."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "feedback_type": {
                        "type": "string",
                        "enum": [
                            "morning_readiness",
                            "post_activity_triage",
                            "overtraining_warning",
                            "weekly_retrospective",
                        ],
                        "description": "Coaching trigger mode to execute.",
                    }
                },
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "required": ["feedback_id", "severity", "summary_headline", "detailed_feedback", "action_items"],
            },
        },
        {
            "name": "record_athlete_subjective_readiness",
            "description": (
                "Persists athlete subjective wellness indicators (sleep quality, muscle soreness, "
                "life stress, and clinical pain notes) into long-term SQLite memory with automatic PII scrubbing."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sleep_quality": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "Overnight sleep quality score from 1 (very poor) to 5 (restorative).",
                    },
                    "muscle_soreness": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "Perceived delayed-onset muscle soreness (DOMS) from 1 (fresh) to 5 (severe).",
                    },
                    "stress_level": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "Autonomic / life stress score from 1 (low) to 5 (extreme).",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Free-text notes on localized tightness, joint discomfort, or energy levels.",
                    },
                },
                "required": ["sleep_quality", "muscle_soreness", "stress_level"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "required": ["status", "message"],
            },
        },
    ]

    # Backward-compatible tool name aliases
    ALIASES = {
        "get_athlete_profile": "fetch_athlete_physiological_profile",
        "get_recent_activities": "retrieve_strava_workout_streams",
        "get_training_load_metrics": "compute_acwr_training_load_metrics",
        "generate_proactive_health_feedback": "generate_proactive_injury_prevention_plan",
        "log_subjective_readiness": "record_athlete_subjective_readiness",
    }

    def __init__(self, agent: Optional[StravaHealthAgent] = None):
        if not agent:
            client = MockStravaClient(scenario="danger_spike")
            athlete = client.get_athlete()
            memory = MemoryStore(":memory:")
            self.agent = StravaHealthAgent(athlete, memory=memory)
            self.strava_client = client
        else:
            self.agent = agent
            self.strava_client = MockStravaClient()

    @staticmethod
    def _guided_error_response(
        error_code: str,
        message: str,
        recovery_instructions: str,
        valid_examples: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Constructs a structured error payload with LLM self-correction guidance."""
        payload = {
            "status": "ERROR",
            "error_code": error_code,
            "message": message,
            "recovery_instructions": recovery_instructions,
            "valid_examples": valid_examples or {},
        }
        return {
            "isError": True,
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
        }

    def fetch_athlete_physiological_profile(self) -> Dict[str, Any]:
        """Fetches the athlete's physiological threshold baselines.

        Returns:
            MCP content dictionary containing serialized `AthleteProfile` JSON.
        """
        return {"content": [{"type": "text", "text": json.dumps(self.agent.athlete.to_dict(), indent=2)}]}

    def retrieve_strava_workout_streams(self, limit: int = 10) -> Dict[str, Any]:
        """Retrieves recent normalized Strava workouts with input bounds checking.

        Args:
            limit: Number of workouts to fetch (must be an integer between 1 and 100).

        Returns:
            MCP content dictionary containing a JSON list of `Activity` records, or a guided error.
        """
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            return self._guided_error_response(
                error_code="INVALID_LIMIT_PARAMETER",
                message=f"Parameter 'limit' must be an integer between 1 and 100, got: {limit!r}.",
                recovery_instructions="Retry calling 'retrieve_strava_workout_streams' with 'limit' set to an integer between 1 and 30.",
                valid_examples={"limit": 10},
            )
        acts = self.strava_client.get_activities(per_page=limit)
        return {"content": [{"type": "text", "text": json.dumps([a.to_dict() for a in acts[:limit]], indent=2)}]}

    def compute_acwr_training_load_metrics(self) -> Dict[str, Any]:
        """Computes ATL, CTL, TSB, and ACWR physiological load indicators.

        Returns:
            MCP content dictionary with `TrainingLoadMetrics` JSON.
        """
        acts = self.strava_client.get_activities(per_page=30)
        metrics = self.agent.analytics.compute_training_load(acts)
        return {"content": [{"type": "text", "text": json.dumps(metrics.to_dict(), indent=2)}]}

    def generate_proactive_injury_prevention_plan(
        self, feedback_type_str: str = "morning_readiness"
    ) -> Dict[str, Any]:
        """Generates proactive coaching feedback for the specified trigger mode.

        Args:
            feedback_type_str: One of 'morning_readiness', 'post_activity_triage',
                'overtraining_warning', or 'weekly_retrospective'.

        Returns:
            MCP content dictionary containing `HealthFeedback` JSON, or a guided error.
        """
        valid_types = [t.value for t in FeedbackType]
        if feedback_type_str not in valid_types:
            return self._guided_error_response(
                error_code="INVALID_FEEDBACK_TYPE",
                message=f"Unsupported feedback_type '{feedback_type_str}'.",
                recovery_instructions=f"Retry with one of the allowed enum values: {valid_types}.",
                valid_examples={"feedback_type": "morning_readiness"},
            )
        fb_type = FeedbackType(feedback_type_str)
        acts = self.strava_client.get_activities(per_page=30)
        feedback = self.agent.evaluate_health_and_fitness(acts, feedback_type=fb_type)
        return {"content": [{"type": "text", "text": json.dumps(feedback.to_dict(), indent=2)}]}

    def record_athlete_subjective_readiness(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validates and logs subjective readiness scores (1-5) into persistent memory.

        Args:
            arguments: Dictionary containing 'sleep_quality', 'muscle_soreness',
                'stress_level' (integers 1-5), and optional 'notes' string.

        Returns:
            MCP confirmation payload or guided recovery instructions if validation fails.
        """
        required = ["sleep_quality", "muscle_soreness", "stress_level"]
        missing = [k for k in required if k not in arguments]
        if missing:
            return self._guided_error_response(
                error_code="MISSING_REQUIRED_PARAMETERS",
                message=f"Missing required readiness fields: {missing}.",
                recovery_instructions=(
                    "Provide all three required integer ratings ('sleep_quality', 'muscle_soreness', "
                    "'stress_level') on a 1 to 5 scale."
                ),
                valid_examples={"sleep_quality": 4, "muscle_soreness": 2, "stress_level": 2, "notes": "Feeling fresh"},
            )

        for field_name in required:
            val = arguments[field_name]
            if not isinstance(val, int) or val < 1 or val > 5:
                return self._guided_error_response(
                    error_code="OUT_OF_RANGE_SCORE",
                    message=f"Field '{field_name}' must be an integer between 1 and 5, got: {val!r}.",
                    recovery_instructions=f"Adjust '{field_name}' to an integer in [1, 2, 3, 4, 5] and retry.",
                    valid_examples={field_name: 3},
                )

        self.agent.memory.log_subjective_readiness(
            sleep_quality=arguments["sleep_quality"],
            muscle_soreness=arguments["muscle_soreness"],
            stress_level=arguments["stress_level"],
            notes=str(arguments.get("notes", "")),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Subjective readiness successfully saved to agent memory.",
                }
            ]
        }

    def handle_tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an MCP tool call with schema validation and guided error recovery."""
        canonical_name = self.ALIASES.get(name, name)

        try:
            if canonical_name == "fetch_athlete_physiological_profile":
                return self.fetch_athlete_physiological_profile()
            elif canonical_name == "retrieve_strava_workout_streams":
                return self.retrieve_strava_workout_streams(limit=arguments.get("limit", 10))
            elif canonical_name == "compute_acwr_training_load_metrics":
                return self.compute_acwr_training_load_metrics()
            elif canonical_name == "generate_proactive_injury_prevention_plan":
                return self.generate_proactive_injury_prevention_plan(
                    feedback_type_str=arguments.get("feedback_type", "morning_readiness")
                )
            elif canonical_name == "record_athlete_subjective_readiness":
                return self.record_athlete_subjective_readiness(arguments)
            else:
                available = [t["name"] for t in self.TOOLS]
                return self._guided_error_response(
                    error_code="UNKNOWN_TOOL",
                    message=f"Unknown tool: '{name}'.",
                    recovery_instructions=f"Select one of the registered MCP tools: {available}.",
                )
        except Exception as exc:
            return self._guided_error_response(
                error_code="TOOL_EXECUTION_EXCEPTION",
                message=str(exc),
                recovery_instructions="Inspect parameter types against inputSchema and retry.",
            )

    def run_stdio(self) -> None:
        """Runs the MCP server over standard input/output (JSON-RPC)."""
        logger.info("Strava Health MCP Server running on stdio...")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                method = req.get("method")
                req_id = req.get("id")

                if method == "tools/list":
                    res = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self.TOOLS}}
                elif method == "tools/call":
                    params = req.get("params", {})
                    name = params.get("name")
                    args = params.get("arguments", {})
                    tool_result = self.handle_tool_call(name, args)
                    res = {"jsonrpc": "2.0", "id": req_id, "result": tool_result}
                else:
                    res = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_res = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
                sys.stdout.write(json.dumps(err_res) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = StravaHealthMCPServer()
    server.run_stdio()
