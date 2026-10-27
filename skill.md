---
name: strava-health-analysis
description: >-
  Authenticates securely with the Strava V3 API via OAuth 2.0 (with automatic
  6-hour access token refresh and Google Cloud Secret Manager integration),
  ingests recent running activities (distance, pace, heart rate, elevation gain,
  and splits), computes physiological training load (Banister TRIMP, ATL, CTL,
  TSB, Gabbett ACWR), displays structured workout summaries, and prescribes
  personalized, safety-guarded coaching recommendations for the athlete's next run.
metadata:
  author: Strava Health AI Agent Team
  license: MIT
  version: 1.0.0
---

# Strava Fitness & Health Analysis Skill

## 🔒 Mandatory Security & Secret Management Rules (CRITICAL)

1. **Zero Hardcoded Credentials**: Never hardcode, print, or commit `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_ACCESS_TOKEN`, or `STRAVA_REFRESH_TOKEN` in any source file, skill definition, test fixture, or Git commit.
2. **Secret Resolution Hierarchy**:
   - **Deployed Environment (Vertex AI Agent Runtime / Cloud Run)**: Retrieve credentials exclusively from **Google Cloud Secret Manager** (`projects/$GOOGLE_CLOUD_PROJECT/secrets/<SECRET_NAME>/versions/latest`) via `SecretManagerClient`.
   - **Local Development**: Load credentials from an untracked `.env` file (excluded via `.gitignore`).
3. **PII & Token Scrubbing**: Always pass logs and state payloads through `PIIRedactor` to scrub `Authorization: Bearer ...` headers, tokens, email addresses, and raw GPS coordinates (`start_latlng` / `end_latlng`).

---

## 🔑 Strava V3 OAuth 2.0 Authentication Lifecycle

Strava V3 uses three-legged OAuth 2.0. Short-lived access tokens expire **6 hours (21,600 seconds)** after creation.

### 1. Required OAuth Scopes
- `read`: Read public profile and segment data.
- `activity:read` / `activity:read_all`: Read athlete running activities, heart rate streams, elevation, and splits (including `Only You` visibility).

### 2. Accessing the API Using an Access Token
Pass the unexpired short-lived access token in the `Authorization` header:

```bash
curl -G https://www.strava.com/api/v3/athlete/activities \
  -H "Authorization: Bearer $STRAVA_ACCESS_TOKEN" \
  -d per_page=10
```

### 3. Refreshing Expired Access Tokens (Every 6 Hours)
Before issuing an API call—or immediately upon receiving a `401 Unauthorized` response—check if the access token is expired (or within 1 hour of `expires_at`) and exchange `$STRAVA_REFRESH_TOKEN` for a new short-lived access token:

```bash
curl -X POST https://www.strava.com/oauth/token \
  -d client_id="$STRAVA_CLIENT_ID" \
  -d client_secret="$STRAVA_CLIENT_SECRET" \
  -d grant_type=refresh_token \
  -d refresh_token="$STRAVA_REFRESH_TOKEN"
```

**Response Schema**:
```json
{
  "token_type": "Bearer",
  "access_token": "<REDACTED_SHORT_LIVED_ACCESS_TOKEN>",
  "expires_at": 1793067900,
  "expires_in": 21600,
  "refresh_token": "<REDACTED_ROTATED_REFRESH_TOKEN>"
}
```
> **Token Rotation Rule**: Always persist the newest `refresh_token` returned by `POST https://www.strava.com/oauth/token`, as issuing a new refresh token immediately invalidates the prior one.

### 4. Token Revocation / Deauthorization
To revoke a token (recommended endpoint effective June 1, 2026+):
```bash
curl -X POST "https://www.strava.com/oauth/revoke" \
  -H "Authorization: Basic $(printf '%s:%s' "$STRAVA_CLIENT_ID" "$STRAVA_CLIENT_SECRET" | base64 -w0)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$STRAVA_ACCESS_TOKEN"
```

---

## 🏃 Core Workflow: Ingest, Display, and Coach

### Step 1: Ingest Running Activity Data
Invoke `retrieve_strava_workout_streams(limit=10)` (backed by `StravaClient.get_activities()` and `get_activity_detail()`):
- Filter/prioritize `type == "Run"`.
- Extract per-run metrics:
  - **Distance**: `distance_km` ($\text{meters} / 1000$) and `distance_miles`
  - **Pace**: `pace_min_per_km` ($\text{moving\_time} / \text{distance\_km}$)
  - **Heart Rate**: `average_heartrate` (bpm), `max_heartrate` (bpm), and 5-zone distribution (`SportsScienceEngine.calculate_hr_zones()`)
  - **Elevation**: `total_elevation_gain` (meters)
  - **Splits**: Per-kilometer split paces and elevation delta (`splits_metric`)

### Step 2: Display Structured Performance Summary
Present a clean Markdown table summarizing the athlete's recent runs and physiological training load:
- **Recent Runs Table**: Date | Run Name | Distance (km) | Pace (`/km`) | Avg / Max HR (bpm) | Elevation Gain (m) | TRIMP Load
- **Physiological Readiness Snapshot**:
  - **Acute Training Load (ATL, 7-day fatigue)**
  - **Chronic Training Load (CTL, 42-day fitness)**
  - **Training Stress Balance ($\text{TSB} = \text{CTL} - \text{ATL}$)**
  - **Acute:Chronic Workload Ratio ($\text{ACWR} = \text{ATL} / \text{CTL}$)** & Injury Risk Zone

### Step 3: Generate Actionable Next-Run Coaching Recommendation
Invoke `generate_proactive_injury_prevention_plan()` and `HeadCoachCoordinatorAgent.run_coordinated_assessment()` to synthesize a personalized prescription for the **next run**:
1. **Suggested Distance (km)** tailored to current 7-day rolling volume and ACWR corridor (`0.8 - 1.3` Sweet Spot).
2. **Target Pace & Heart Rate Zone** (e.g., Zone 2 Aerobic Base at `60-70% HRmax` vs. Zone 1 Active Recovery if `ACWR > 1.5`).
3. **Recovery & Refueling Protocol**: Post-run carbohydrate-to-protein replenishment (`3:1` ratio), hydration target (ml), mobility work, and sleep target hours.
