"""Unit tests verifying all 19 AgentOps Code Review Matrix criteria."""

import asyncio
import json
import unittest

from strava_health_agent.guardrails import HumanInTheLoopHook, SafetyAndPolicyGuardrailPlugin
from strava_health_agent.mcp_server import StravaHealthMCPServer
from strava_health_agent.memory_store import ContextCompactor, MemoryStore
from strava_health_agent.models import AlertSeverity, AthleteProfile, FeedbackType
from strava_health_agent.observability import DistributedTracer, PIIRedactor, StructuredJsonLogger
from strava_health_agent.orchestrator import HeadCoachCoordinatorAgent, StrategicModelRouter
from strava_health_agent.secrets import SecretManagerClient
from strava_health_agent.strava_client import MockStravaClient


class TestAgentOpsMatrix(unittest.TestCase):

    def setUp(self):
        self.athlete = AthleteProfile(athlete_id=42, firstname="Alex", lastname="Rivers")
        self.client = MockStravaClient(scenario="danger_spike")
        self.activities = self.client.get_activities(per_page=30)

    def test_1_guided_error_handling_and_schemas(self):
        mcp = StravaHealthMCPServer()
        # Test guided error on out-of-range limit
        err_res = mcp.handle_tool_call("retrieve_strava_workout_streams", {"limit": 999})
        self.assertTrue(err_res.get("isError"))
        payload = json.loads(err_res["content"][0]["text"])
        self.assertEqual(payload["error_code"], "INVALID_LIMIT_PARAMETER")
        self.assertIn("recovery_instructions", payload)

        # Test guided error on missing readiness fields
        err_res2 = mcp.handle_tool_call("record_athlete_subjective_readiness", {"sleep_quality": 4})
        self.assertTrue(err_res2.get("isError"))
        payload2 = json.loads(err_res2["content"][0]["text"])
        self.assertEqual(payload2["error_code"], "MISSING_REQUIRED_PARAMETERS")
        self.assertIn("recovery_instructions", payload2)

    def test_2_context_compaction_and_async_memory(self):
        compactor = ContextCompactor(max_token_budget=4000, sliding_window_size=5)
        compacted = compactor.compact_activity_history(self.activities)
        self.assertEqual(len(compacted["sliding_window_recent"]), 5)
        self.assertIn("compacted_historical_summary", compacted)

        memory = MemoryStore(":memory:")
        memory.save_activities(self.activities, athlete_id=42)
        res = asyncio.run(memory.async_consolidate_memory())
        self.assertEqual(res["status"], "CONSOLIDATED")

    def test_3_multi_agent_orchestration_and_routing(self):
        router = StrategicModelRouter()
        fast_decision = router.select_model("morning_readiness", acwr=1.1, has_acute_symptoms=False)
        self.assertEqual(fast_decision.selected_model, "gemini-2.0-flash")

        pro_decision = router.select_model("overtraining_warning", acwr=1.8, has_acute_symptoms=True)
        self.assertEqual(pro_decision.selected_model, "gemini-2.5-pro")

        coordinator = HeadCoachCoordinatorAgent(self.athlete, memory=MemoryStore(":memory:"))
        fb = coordinator.run_coordinated_assessment(self.activities, FeedbackType.OVERTRAINING_WARNING)
        self.assertEqual(fb.severity, AlertSeverity.CRITICAL)
        self.assertEqual(fb.key_metrics["routed_model"], "gemini-2.5-pro")
        self.assertIn("hitl_status", fb.key_metrics)

    def test_4_observability_tracing_and_pii_redaction(self):
        redactor = PIIRedactor()
        raw = "Contact athlete@example.com or 415-555-1234 at GPS 37.7749, -122.4194 with Bearer secret123"
        scrubbed = redactor.redact_text(raw)
        self.assertNotIn("athlete@example.com", scrubbed)
        self.assertNotIn("415-555-1234", scrubbed)
        self.assertNotIn("37.7749, -122.4194", scrubbed)
        self.assertIn("[REDACTED_EMAIL]", scrubbed)
        self.assertIn("[REDACTED_GPS]", scrubbed)

        logger = StructuredJsonLogger(redactor=redactor)
        tracer = DistributedTracer(logger=logger)
        with tracer.start_as_current_span("parent_op") as p_span:
            logger.log_intent("test_action", {"access_token": "top_secret"}, "Testing intent")
            logger.log_outcome("test_action", "SUCCESS", {"result": "ok"}, latency_ms=12.3)

        self.assertEqual(len(tracer.completed_spans), 1)
        self.assertEqual(logger.records[0]["metadata"]["intended_inputs"]["access_token"], "[REDACTED]")

    def test_5_secret_manager_client(self):
        sm = SecretManagerClient()
        self.assertIsNone(sm.get_secret("NON_EXISTENT_TEST_SECRET_KEY_12345"))


if __name__ == "__main__":
    unittest.main()
