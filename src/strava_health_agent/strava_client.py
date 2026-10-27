"""Strava API Client with OAuth2 refresh and realistic mock fixtures.

Implements standard REST calls to the Strava V3 API using Python standard library
(urllib.request) to eliminate heavy third-party dependency requirements.
Includes a complete `MockStravaClient` for immediate testing and evaluation.
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Activity, AthleteProfile
from .secrets import SecretManagerClient

logger = logging.getLogger(__name__)


def load_local_dotenv(dotenv_path: Optional[str] = None) -> None:
    """Loads untracked local .env variables into os.environ without external deps."""
    candidates = [
        Path(dotenv_path) if dotenv_path else None,
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for path in candidates:
        if path and path.is_file():
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            break


class StravaClient:
    """Production client connecting to the Strava v3 REST API with OAuth2 auto-refresh."""

    BASE_URL = "https://www.strava.com/api/v3"
    OAUTH_URL = "https://www.strava.com/oauth/token"
    REVOKE_URL = "https://www.strava.com/oauth/revoke"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        access_token: Optional[str] = None,
        secret_manager: Optional[SecretManagerClient] = None,
    ):
        load_local_dotenv()
        sm = secret_manager or SecretManagerClient()
        self.client_id = client_id or sm.get_secret("STRAVA_CLIENT_ID")
        self.client_secret = client_secret or sm.get_secret("STRAVA_CLIENT_SECRET")
        self.refresh_token = refresh_token or sm.get_secret("STRAVA_REFRESH_TOKEN")
        self.access_token = access_token or sm.get_secret("STRAVA_ACCESS_TOKEN")
        # If an initial access_token was provided, assume valid until 401 or 6h window
        self.token_expires_at: int = int(time.time()) + 21600 if self.access_token else 0

    def refresh_access_token(self) -> str:
        """Exchanges refresh_token for a fresh 6-hour access_token via Strava OAuth."""
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise ValueError(
                "Missing Strava OAuth credentials. Ensure STRAVA_CLIENT_ID, "
                "STRAVA_CLIENT_SECRET, and STRAVA_REFRESH_TOKEN are configured in "
                "Google Cloud Secret Manager or local .env."
            )

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(self.OAUTH_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                self.access_token = result.get("access_token")
                # Persist rotated refresh token per Strava OAuth2 spec
                self.refresh_token = result.get("refresh_token", self.refresh_token)
                self.token_expires_at = result.get("expires_at", int(time.time()) + 21600)
                logger.info("Successfully refreshed Strava OAuth access token.")
                return str(self.access_token)
        except Exception as e:
            logger.error("Failed to refresh Strava OAuth token: %s", e)
            raise

    def revoke_token(self, token: Optional[str] = None) -> bool:
        """Revokes an access or refresh token via POST https://www.strava.com/oauth/revoke."""
        target_token = token or self.access_token or self.refresh_token
        if not (self.client_id and self.client_secret and target_token):
            raise ValueError("client_id, client_secret, and token are required for revocation.")
        basic_creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        data = urllib.parse.urlencode({"token": target_token}).encode("utf-8")
        req = urllib.request.Request(self.REVOKE_URL, data=data, method="POST")
        req.add_header("Authorization", f"Basic {basic_creds}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200

    def _ensure_token(self) -> str:
        if not self.access_token or time.time() > (self.token_expires_at - 3600):
            if self.refresh_token and self.client_id and self.client_secret:
                return self.refresh_access_token()
        if not self.access_token:
            raise ValueError("No valid Strava access token available.")
        return self.access_token

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        token = self._ensure_token()
        url = f"{self.BASE_URL}{endpoint}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            # Automatic 6-hour access token expiration recovery via refresh_token
            if err.code == 401 and self.refresh_token and self.client_id and self.client_secret:
                new_token = self.refresh_access_token()
                retry_req = urllib.request.Request(url, method="GET")
                retry_req.add_header("Authorization", f"Bearer {new_token}")
                retry_req.add_header("Accept", "application/json")
                with urllib.request.urlopen(retry_req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise

    def get_athlete(self) -> AthleteProfile:
        """Fetches the authenticated athlete profile."""
        data = self._get("/athlete")
        return AthleteProfile(
            athlete_id=data.get("id", 1),
            firstname=data.get("firstname", "Athlete"),
            lastname=data.get("lastname", ""),
            weight_kg=float(data.get("weight") or 70.0),
        )

    def get_activities(
        self,
        before: Optional[int] = None,
        after: Optional[int] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> List[Activity]:
        """Fetches a list of activities for the authenticated athlete."""
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if before:
            params["before"] = before
        if after:
            params["after"] = after

        raw_list = self._get("/athlete/activities", params)
        activities: List[Activity] = []
        for raw in raw_list:
            act = Activity(
                id=raw.get("id"),
                name=raw.get("name", "Activity"),
                type=raw.get("type", "Run"),
                start_date=raw.get("start_date", datetime.now(timezone.utc).isoformat()),
                distance_meters=float(raw.get("distance", 0.0)),
                moving_time_seconds=int(raw.get("moving_time", 0)),
                elapsed_time_seconds=int(raw.get("elapsed_time", 0)),
                total_elevation_gain=float(raw.get("total_elevation_gain", 0.0)),
                average_speed_mps=float(raw.get("average_speed", 0.0)),
                max_speed_mps=float(raw.get("max_speed", 0.0)),
                average_heartrate=float(raw["average_heartrate"]) if "average_heartrate" in raw and raw["average_heartrate"] else None,
                max_heartrate=float(raw["max_heartrate"]) if "max_heartrate" in raw and raw["max_heartrate"] else None,
                suffer_score=float(raw["suffer_score"]) if "suffer_score" in raw and raw["suffer_score"] else None,
                calories=float(raw["calories"]) if "calories" in raw and raw["calories"] else None,
                splits_metric=raw.get("splits_metric"),
            )
            activities.append(act)
        return activities


def _generate_splits(dist_m: float, moving_sec: int, hr_avg: float, elev_m: float) -> List[Dict[str, Any]]:
    """Generates realistic 1km splits for running workouts."""
    num_km = max(1, int(dist_m // 1000))
    sec_per_km = moving_sec / max(1.0, dist_m / 1000.0)
    elev_per_km = round(elev_m / num_km, 1)
    splits = []
    for k in range(1, min(num_km + 1, 6)):  # Cap preview at first 5 splits for compactness
        split_sec = int(sec_per_km * (1.02 - 0.01 * k))
        splits.append({
            "split": k,
            "distance": 1000.0,
            "moving_time": split_sec,
            "pace_min_per_km": f"{split_sec // 60}:{split_sec % 60:02d} /km",
            "elevation_difference": elev_per_km,
            "average_heartrate": round(hr_avg + (k - 2) * 1.5, 1),
        })
    return splits


class MockStravaClient:
    """Mock client simulating realistic athlete scenarios for testing and demos."""

    def __init__(self, scenario: str = "danger_spike"):
        """Scenario options:

        - 'danger_spike': Sudden mileage/intensity jump (ACWR > 1.6, overreaching)
        - 'optimal_build': Consistent, healthy progressive overload (ACWR ~1.15)
        - 'taper_freshness': Deload/taper week with positive TSB ready for race
        """
        self.scenario = scenario
        self.athlete = AthleteProfile(
            athlete_id=987654,
            firstname="Alex",
            lastname="Rivers",
            weight_kg=68.5,
            resting_hr=52,
            max_hr=188,
            lactate_threshold_hr=170,
            primary_sport="Run",
            weekly_target_hours=7.0,
        )

    def get_athlete(self) -> AthleteProfile:
        return self.athlete

    def get_activities(
        self,
        before: Optional[int] = None,
        after: Optional[int] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> List[Activity]:
        """Generates 4 weeks of synthetic activity history matching the scenario."""
        activities: List[Activity] = []
        now = datetime.now(timezone.utc)

        if self.scenario == "danger_spike":
            # Baseline: Weeks 2-4 had moderate load (30 km/wk)
            # Recent Week: Spiked to 75 km with back-to-back hard threshold runs
            for days_ago in range(28, 7, -1):
                if days_ago % 2 == 0:  # Every other day
                    date_str = (now - timedelta(days=days_ago, hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    activities.append(
                        Activity(
                            id=1000 + days_ago,
                            name=f"Easy Aerobic Run - Day {days_ago}",
                            type="Run",
                            start_date=date_str,
                            distance_meters=8000.0,
                            moving_time_seconds=2700,  # 45 min
                            elapsed_time_seconds=2850,
                            total_elevation_gain=45.0,
                            average_speed_mps=2.96,
                            max_speed_mps=3.8,
                            average_heartrate=142.0,
                            max_heartrate=158.0,
                            suffer_score=35.0,
                        )
                    )

            # Week 1 (Last 7 days): Heavy spike!
            spike_schedule = [
                (6, "Long Run Spike", 24000.0, 7800, 156.0, 178.0, 180.0),   # 24km
                (5, "Tempo Repeats", 14000.0, 4200, 168.0, 184.0, 140.0),    # 14km
                (4, "Intervals 8x800m", 12000.0, 3900, 172.0, 186.0, 155.0), # 12km
                (2, "Mid-week Hill Repeats", 15000.0, 4800, 165.0, 182.0, 160.0), # 15km
                (1, "Aggressive Fast Finish Run", 16000.0, 5100, 166.0, 185.0, 175.0), # 16km
            ]
            for days_ago, name, dist, moving_sec, hr_avg, hr_max, suffer in spike_schedule:
                date_str = (now - timedelta(days=days_ago, hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                activities.append(
                    Activity(
                        id=2000 + days_ago,
                        name=name,
                        type="Run",
                        start_date=date_str,
                        distance_meters=dist,
                        moving_time_seconds=moving_sec,
                        elapsed_time_seconds=moving_sec + 180,
                        total_elevation_gain=120.0,
                        average_speed_mps=dist / moving_sec,
                        max_speed_mps=(dist / moving_sec) * 1.3,
                        average_heartrate=hr_avg,
                        max_heartrate=hr_max,
                        suffer_score=suffer,
                    )
                )

        elif self.scenario == "optimal_build":
            # Progressive, steady overload (~8% increase week-over-week)
            for days_ago in range(28, 0, -1):
                if days_ago % 2 == 1:
                    date_str = (now - timedelta(days=days_ago, hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    dist = 9000.0 + (28 - days_ago) * 100.0
                    activities.append(
                        Activity(
                            id=3000 + days_ago,
                            name=f"Progressive Zone 2 Base Run",
                            type="Run",
                            start_date=date_str,
                            distance_meters=dist,
                            moving_time_seconds=int(dist / 2.9),
                            elapsed_time_seconds=int(dist / 2.9) + 120,
                            total_elevation_gain=50.0,
                            average_speed_mps=2.9,
                            max_speed_mps=3.7,
                            average_heartrate=145.0,
                            max_heartrate=162.0,
                            suffer_score=48.0,
                        )
                    )

        else:  # taper_freshness
            # High baseline early on, past 5 days very low volume
            for days_ago in range(28, 6, -1):
                if days_ago % 2 == 0:
                    date_str = (now - timedelta(days=days_ago, hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    activities.append(
                        Activity(
                            id=4000 + days_ago,
                            name="Pre-Race Block Workout",
                            type="Run",
                            start_date=date_str,
                            distance_meters=14000.0,
                            moving_time_seconds=4500,
                            elapsed_time_seconds=4650,
                            total_elevation_gain=60.0,
                            average_speed_mps=3.1,
                            max_speed_mps=4.1,
                            average_heartrate=152.0,
                            max_heartrate=174.0,
                            suffer_score=85.0,
                        )
                    )
            # Last 5 days: gentle shakeouts
            for days_ago in [4, 2]:
                date_str = (now - timedelta(days=days_ago, hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                activities.append(
                    Activity(
                        id=4500 + days_ago,
                        name="Easy Shakeout & Strides",
                        type="Run",
                        start_date=date_str,
                        distance_meters=4500.0,
                        moving_time_seconds=1500,
                        elapsed_time_seconds=1600,
                        total_elevation_gain=15.0,
                        average_speed_mps=3.0,
                        max_speed_mps=4.5,
                        average_heartrate=128.0,
                        max_heartrate=155.0,
                        suffer_score=15.0,
                    )
                )

        for act in activities:
            if not act.splits_metric:
                act.splits_metric = _generate_splits(
                    act.distance_meters,
                    act.moving_time_seconds,
                    act.average_heartrate or 145.0,
                    act.total_elevation_gain,
                )
        return sorted(activities, key=lambda a: a.start_date, reverse=True)
