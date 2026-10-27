"""Sports Science & Physiological Analytics Engine.

Calculates:
- Training Impulse (TRIMP) from Heart Rate Reserve (HRR) or Perceived Effort
- Acute Training Load (ATL, ~7-day rolling fatigue)
- Chronic Training Load (CTL, ~42-day rolling fitness)
- Training Stress Balance (TSB = CTL - ATL, 'Form' / freshness)
- Acute:Chronic Workload Ratio (ACWR) and injury risk categorization
- Heart Rate Zone breakdown and recovery time calculations
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

from .models import Activity, AthleteProfile, TrainingLoadMetrics


class SportsScienceEngine:
    """Computes physiological stress, fatigue, and injury risk metrics."""

    def __init__(self, athlete: AthleteProfile):
        self.athlete = athlete

    def calculate_trimp(self, activity: Activity) -> float:
        """Calculates Banister's TRIMP (Training Impulse).

        TRIMP = Duration (min) * DeltaHR_ratio * y
        where y = 0.64 * exp(1.92 * DeltaHR_ratio) (male formula standard)
        DeltaHR_ratio = (HR_avg - HR_rest) / (HR_max - HR_rest)
        """
        duration_min = activity.moving_time_seconds / 60.0
        if duration_min <= 0:
            return 0.0

        # Case 1: Heart rate data is available
        if activity.average_heartrate and activity.average_heartrate > 0:
            hr_rest = self.athlete.resting_hr
            hr_max = self.athlete.max_hr
            hr_avg = max(float(activity.average_heartrate), float(hr_rest))
            hr_range = max(hr_max - hr_rest, 30.0)

            # Heart rate reserve ratio capped between 0.0 and 1.0
            delta_hr = min(max((hr_avg - hr_rest) / hr_range, 0.0), 1.0)
            weight_factor = 0.64 * math.exp(1.92 * delta_hr)
            trimp = duration_min * delta_hr * weight_factor
            return round(trimp, 1)

        # Case 2: Strava Suffer Score / Relative Effort is present
        if activity.suffer_score and activity.suffer_score > 0:
            return round(float(activity.suffer_score), 1)

        # Case 3: Fallback using speed, distance, elevation gain, and RPE
        rpe = activity.perceived_exertion or 6  # default moderate (6/10)
        elevation_factor = 1.0 + (activity.total_elevation_gain / 500.0)
        estimated_intensity = (rpe / 10.0) * min(elevation_factor, 1.5)
        fallback_trimp = duration_min * estimated_intensity * 0.9
        return round(fallback_trimp, 1)

    def calculate_hr_zones(self, avg_hr: Optional[float]) -> Dict[str, Any]:
        """Categorizes average heart rate into classic 5-zone model."""
        if not avg_hr or avg_hr <= 0:
            return {"primary_zone": "Unknown", "pct_max_hr": 0.0}

        hr_max = float(self.athlete.max_hr)
        pct = (avg_hr / hr_max) * 100.0

        if pct < 60.0:
            zone = "Zone 1 - Active Recovery (<60% HRmax)"
            desc = "Flushes lactic acid and promotes blood flow with minimal stress."
        elif pct < 70.0:
            zone = "Zone 2 - Aerobic Base (60-70% HRmax)"
            desc = "Builds mitochondrial density and fat oxidation capacity."
        elif pct < 80.0:
            zone = "Zone 3 - Aerobic Power / Tempo (70-80% HRmax)"
            desc = "Enhances glycogen storage and pace endurance."
        elif pct < 90.0:
            zone = "Zone 4 - Lactate Threshold (80-90% HRmax)"
            desc = "Increases lactate clearance and high-intensity sustained power."
        else:
            zone = "Zone 5 - Anaerobic / Neuromuscular (>90% HRmax)"
            desc = "Maximum cardiovascular output; causes acute neuromuscular fatigue."

        return {
            "primary_zone": zone,
            "pct_max_hr": round(pct, 1),
            "zone_description": desc,
        }

    def compute_training_load(
        self,
        activities: List[Activity],
        reference_date: Optional[datetime] = None,
        atl_days: int = 7,
        ctl_days: int = 42,
    ) -> TrainingLoadMetrics:
        """Computes ATL, CTL, TSB, and ACWR using Exponential Moving Averages (EMA).

        ATL: ~7-day fatigue constant (k_atl = 2 / (7 + 1) = 0.25)
        CTL: ~42-day fitness constant (k_ctl = 2 / (42 + 1) = 0.0465)
        TSB: Form = CTL - ATL
        ACWR: ATL / max(CTL, 1.0)
        """
        if not reference_date:
            reference_date = datetime.now(timezone.utc)

        # Build daily TRIMP dictionary for the past 60 days
        days_history = 60
        daily_trimp: Dict[str, float] = {}
        daily_km: Dict[str, float] = {}
        daily_seconds: Dict[str, float] = {}

        for i in range(days_history + 1):
            day_dt = reference_date - timedelta(days=days_history - i)
            day_key = day_dt.strftime("%Y-%m-%d")
            daily_trimp[day_key] = 0.0
            daily_km[day_key] = 0.0
            daily_seconds[day_key] = 0.0

        for act in activities:
            try:
                # Parse ISO date string (handle trailing Z or offset)
                date_str = act.start_date
                if date_str.endswith("Z"):
                    date_str = date_str[:-1] + "+00:00"
                act_dt = datetime.fromisoformat(date_str)
                # Normalize to date string (UTC date)
                key = act_dt.strftime("%Y-%m-%d")
                if key in daily_trimp:
                    trimp = self.calculate_trimp(act)
                    daily_trimp[key] += trimp
                    daily_km[key] += act.distance_km
                    daily_seconds[key] += act.moving_time_seconds
            except Exception:
                continue

        # EMA decay constants
        k_atl = 2.0 / (atl_days + 1.0)
        k_ctl = 2.0 / (ctl_days + 1.0)

        atl = 0.0
        ctl = 0.0

        sorted_days = sorted(daily_trimp.keys())
        for d in sorted_days:
            load = daily_trimp[d]
            atl = (load * k_atl) + (atl * (1.0 - k_atl))
            ctl = (load * k_ctl) + (ctl * (1.0 - k_ctl))

        tsb = ctl - atl
        acwr = atl / max(ctl, 5.0)

        # Assess injury risk zone based on Gabbett et al. ACWR research
        if acwr < 0.8:
            risk_zone = "Under-trained / Low Readiness"
        elif acwr <= 1.3:
            risk_zone = "Optimal 'Sweet Spot' (Low Injury Risk)"
        elif acwr <= 1.5:
            risk_zone = "Overreaching / Heightened Fatigue"
        else:
            risk_zone = "Danger Zone (High Injury & Overtraining Risk)"

        # Recent 7-day totals
        recent_7_days = sorted_days[-7:]
        weekly_km = sum(daily_km[d] for d in recent_7_days)
        weekly_hours = sum(daily_seconds[d] for d in recent_7_days) / 3600.0
        weekly_trimp = sum(daily_trimp[d] for d in recent_7_days)

        # Estimate recovery hours needed based on recent fatigue (ATL) and TSB
        if tsb < -20.0 or acwr > 1.5:
            rec_hours = 48
        elif tsb < -10.0 or acwr > 1.3:
            rec_hours = 24
        elif tsb < 0:
            rec_hours = 12
        else:
            rec_hours = 0

        return TrainingLoadMetrics(
            date=reference_date.strftime("%Y-%m-%d"),
            acute_training_load=round(atl, 1),
            chronic_training_load=round(ctl, 1),
            training_stress_balance=round(tsb, 1),
            acwr=round(acwr, 2),
            weekly_total_km=round(weekly_km, 1),
            weekly_total_hours=round(weekly_hours, 1),
            weekly_trimp=round(weekly_trimp, 1),
            risk_zone=risk_zone,
            rest_recommended_hours=rec_hours,
        )
