# DESIGN_SPEC.md — Strava Health AI Agent

## Overview
An autonomous, security-first AI health and endurance coaching agent built with the Google Agent Development Kit (ADK) and deployed on the Gemini Enterprise Agent Platform (Vertex AI Agent Runtime). The agent securely authenticates with the Strava V3 API using OAuth 2.0 (short-lived 6-hour access tokens with automatic refresh token rotation stored in Google Cloud Secret Manager), ingests running activities (distance, pace, heart rate, elevation, splits), computes clinical sports science metrics (Banister TRIMP, ATL, CTL, TSB, and Gabbett ACWR), and generates personalized, safety-guarded training recommendations for the athlete's next run.

## Example Use Cases
1. **Performance Summary & Next-Run Prescription**:
   - **Input**: `"Fetch my latest Strava runs, summarize my performance metrics, and give me a training recommendation for my next run."`
   - **Output**: Structured breakdown of recent runs (distance in km, pace in `/km`, avg/max HR, elevation gain, splits), current physiological load (ATL, CTL, TSB, ACWR risk zone), and a specific next-run prescription (recommended distance, target pace/HR zone, and post-run recovery protocol).
2. **Overtraining & Injury Prevention Guardrail**:
   - **Input**: Athlete requests a high-intensity workout when 7-day acute load spikes (`ACWR > 1.5`).
   - **Output**: Critical overtraining warning overriding high-intensity intervals in favor of Zone 1 active recovery or rest, gated by Human-in-the-Loop confirmation.

## Tools Required
1. `fetch_athlete_physiological_profile`: Retrieves authenticated athlete baselines (`GET /api/v3/athlete`) using Bearer token auth with automatic OAuth2 token refresh (`POST /oauth/token`).
2. `retrieve_strava_workout_streams`: Fetches recent running activities (`GET /api/v3/athlete/activities`), including distance, moving time, pace, heart rate, elevation gain, and splits.
3. `compute_acwr_training_load_metrics`: Computes Banister TRIMP, 7-day ATL, 42-day CTL, TSB, and Gabbett ACWR injury risk zone.
4. `generate_proactive_injury_prevention_plan`: Synthesizes recent performance trends into a concrete recommendation for the next run (distance, target HR zone/pace, recovery advice).
5. `record_athlete_subjective_readiness`: Persists sleep quality, muscle soreness, and stress ratings (1–5) with automatic PII redaction.

## Constraints & Safety Rules
1. **Zero Hardcoded Secrets**: Never store, log, or commit `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, `STRAVA_REFRESH_TOKEN`, or GCP keys in source code, `skill.md`, or Git history.
2. **PII & Token Redaction**: Scrub all Bearer tokens, API keys, emails, phone numbers, and raw GPS coordinates (`start_latlng`/`end_latlng`) via `PIIRedactor` before logging or storing state.
3. **Clinical & Medical Guardrails**: Enforce rest/Zone 1 recovery when `ACWR > 1.5` (Danger Zone) and mandate licensed physician evaluation if acute pain or cardiac symptoms are reported.
4. **Guided Error Recovery**: All tools must return structured recovery instructions to the LLM on API/validation errors rather than raising unhandled exceptions.

## Success Criteria
- 100% compliance (95/95 points) against the AgentOps Code Review Matrix (`rubrics.md` / `gradingrubic.md`).
- Zero leaked secrets verified by `git log -S` and pre-publish audit prior to pushing to `https://github.com/bertilw-google/strava-health-ai-agent`.
- Passing ADK evaluation suite (`agents-cli eval run`) across golden dataset scenarios.

## Reference Samples
- `adk-ae-oauth`: OAuth 2.0 token lifecycle management on Agent Runtime with Gemini Enterprise registration.
- `ambient-expense-agent`: Proactive scheduled/event-driven agent execution and Terraform IaC patterns.
- `safety-plugins`: Modular pre/post-execution guardrails and self-evaluation judge patterns.
- `memory-bank`: Cross-session state persistence and context compaction.
