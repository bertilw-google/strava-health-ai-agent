"""Strava Health AI Agent - Proactive health & fitness coaching agent powered by Google Gemini.

Built following the 5-Day AI Agent Intensive framework & AgentOps Code Review Matrix:
- Day 1: Foundations & Structured Outputs
- Day 2: Tools & Model Context Protocol (MCP)
- Day 3: Context Engineering, Compaction & Async Persistent Memory
- Day 4: Observability, Distributed Tracing, PII Redaction & LLM-as-a-Judge Evaluation
- Day 5: Multi-Agent Orchestration, Model Routing, Guardrails, HITL & IaC Deployment
"""

__version__ = "1.0.0"
__author__ = "Strava Health AI Agent Team"

from .models import (
    Activity,
    AthleteProfile,
    HealthFeedback,
    TrainingLoadMetrics,
    AlertSeverity,
    FeedbackType,
)
from .analytics import SportsScienceEngine
from .strava_client import StravaClient, MockStravaClient
from .memory_store import ContextCompactor, MemoryStore
from .agent import StravaHealthAgent
from .guardrails import HumanInTheLoopHook, SafetyAndPolicyGuardrailPlugin
from .observability import DistributedTracer, PIIRedactor, StructuredJsonLogger
from .orchestrator import (
    HeadCoachCoordinatorAgent,
    InjuryPreventionSpecialistAgent,
    NutritionAndRecoveryAgent,
    PhysiologyAnalystAgent,
    StrategicModelRouter,
)
from .proactive_scheduler import ProactiveScheduler
from .secrets import SecretManagerClient

__all__ = [
    "Activity",
    "AthleteProfile",
    "HealthFeedback",
    "TrainingLoadMetrics",
    "AlertSeverity",
    "FeedbackType",
    "SportsScienceEngine",
    "StravaClient",
    "MockStravaClient",
    "ContextCompactor",
    "MemoryStore",
    "StravaHealthAgent",
    "SafetyAndPolicyGuardrailPlugin",
    "HumanInTheLoopHook",
    "StructuredJsonLogger",
    "DistributedTracer",
    "PIIRedactor",
    "HeadCoachCoordinatorAgent",
    "PhysiologyAnalystAgent",
    "InjuryPreventionSpecialistAgent",
    "NutritionAndRecoveryAgent",
    "StrategicModelRouter",
    "ProactiveScheduler",
    "SecretManagerClient",
]
