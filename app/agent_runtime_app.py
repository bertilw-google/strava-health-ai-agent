"""Vertex AI Agent Runtime (`AdkApp`) Entrypoint for Strava Health AI Agent."""

from typing import Any, Dict

from .agent import root_agent

try:
    from vertexai.agent_engines.templates.adk import AdkApp  # type: ignore

    agent_runtime_app = AdkApp(agent=root_agent, enable_tracing=True)
except ImportError:
    class _StandaloneAgentRuntimeApp:
        def __init__(self, agent: Any):
            self.agent = agent

        def query(self, prompt: str) -> Dict[str, Any]:
            if hasattr(self.agent, "run_query"):
                return self.agent.run_query(prompt)
            return {"status": "OK", "prompt": prompt}

        def get_deployment_metadata(self) -> Dict[str, Any]:
            return {
                "app_name": "strava-health-ai-agent",
                "entrypoint": "app.agent_runtime_app:agent_runtime_app",
                "target": "agent_runtime",
                "project": "capsules-agents-1",
                "region": "us-central1",
                "enable_tracing": True,
                "secret_manager_secrets": [
                    "STRAVA_CLIENT_ID",
                    "STRAVA_CLIENT_SECRET",
                    "STRAVA_ACCESS_TOKEN",
                    "STRAVA_REFRESH_TOKEN",
                ],
            }

    agent_runtime_app = _StandaloneAgentRuntimeApp(agent=root_agent)
