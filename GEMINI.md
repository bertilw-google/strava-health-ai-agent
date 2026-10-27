# GEMINI.md — Strava Health AI Agent (ADK Project Guidance)

## Project Structure
- **Agent Directory**: `app/`
  - `app/agent.py`: Root ADK `Agent` and `HeadCoachCoordinatorAgent` wiring.
  - `app/tools.py`: ADK `FunctionTool` definitions wrapping Strava V3 API and Sports Science Engine.
  - `app/agent_runtime_app.py`: Vertex AI Agent Runtime (`AdkApp`) entrypoint.
- **Core Domain Package**: `src/strava_health_agent/`
  - `strava_client.py`: Strava V3 OAuth2 client with 6-hour token auto-refresh & Secret Manager resolution.
  - `analytics.py`: Banister TRIMP, ATL, CTL, TSB, and Gabbett ACWR calculations.
  - `orchestrator.py`: Multi-agent Coordinator, specialist sub-agents, and `StrategicModelRouter`.
  - `guardrails.py`: Clinical safety guardrails and Human-in-the-Loop confirmation hooks.
  - `observability.py`: Structured JSON logging, Intent vs. Outcome tracking, OpenTelemetry spans, and `PIIRedactor`.
  - `memory_store.py`: Persistent SQLite session state, `ContextCompactor`, and async memory consolidation.
- **Custom Skill**: `skill.md` and `skills/strava_analysis/SKILL.md`
- **IaC & Deployment**: `deployment/terraform/` and `terraform/`
- **Rubrics & Specs**: `DESIGN_SPEC.md`, `rubrics.md`, `gradingrubic.md`

## Mandatory Security Rules
- Never hardcode or commit `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, or `STRAVA_REFRESH_TOKEN`.
- Always resolve secrets via `SecretManagerClient` (Google Cloud Secret Manager in production, untracked `.env` locally).
