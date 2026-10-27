"""Data models for Strava Health AI Agent.

Defines schemas for Strava activities, athlete profiles, physiological metrics,
and proactive health feedback notifications.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any


class AlertSeverity(str, Enum):
    """Urgency / severity level of proactive health notifications."""
    INFO = "info"
    ADVISORY = "advisory"
    WARNING = "warning"
    CRITICAL = "critical"


class FeedbackType(str, Enum):
    """Categories of proactive health feedback."""
    MORNING_READINESS = "morning_readiness"
    POST_ACTIVITY_TRIAGE = "post_activity_triage"
    OVERTRAINING_WARNING = "overtraining_warning"
    RECOVERY_RECOMMENDATION = "recovery_recommendation"
    WEEKLY_RETROSPECTIVE = "weekly_retrospective"


class TrainingZone(str, Enum):
    """Heart rate training zones."""
    ZONE_1_RECOVERY = "Zone 1 (Active Recovery, <60% HRmax)"
    ZONE_2_AEROBIC = "Zone 2 (Aerobic Base, 60-70% HRmax)"
    ZONE_3_TEMPO = "Zone 3 (Aerobic Power / Tempo, 70-80% HRmax)"
    ZONE_4_THRESHOLD = "Zone 4 (Lactate Threshold, 80-90% HRmax)"
    ZONE_5_ANAEROBIC = "Zone 5 (Neuromuscular / Anaerobic, >90% HRmax)"


@dataclass
class AthleteProfile:
    """Athlete baseline profile and physiological thresholds."""
    athlete_id: int
    firstname: str
    lastname: str
    weight_kg: float = 70.0
    resting_hr: int = 55
    max_hr: int = 185
    lactate_threshold_hr: int = 168
    ftp_watts: Optional[int] = 250
    primary_sport: str = "Run"  # "Run", "Ride", "Swim", "Triathlon", "CrossFit"
    weekly_target_hours: float = 6.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AthleteProfile":
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class Activity:
    """Normalized Strava activity record."""
    id: int
    name: str
    type: str  # Run, Ride, Swim, WeightTraining, Walk, etc.
    start_date: str  # ISO 8601
    distance_meters: float
    moving_time_seconds: int
    elapsed_time_seconds: int
    total_elevation_gain: float
    average_speed_mps: float
    max_speed_mps: float
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    suffer_score: Optional[float] = None
    calories: Optional[float] = None
    perceived_exertion: Optional[int] = None  # 1-10 RPE
    description: Optional[str] = None
    splits_metric: Optional[List[Dict[str, Any]]] = None

    @property
    def distance_km(self) -> float:
        return round(self.distance_meters / 1000.0, 2)

    @property
    def distance_miles(self) -> float:
        return round(self.distance_meters / 1609.34, 2)

    @property
    def duration_minutes(self) -> float:
        return round(self.moving_time_seconds / 60.0, 1)

    @property
    def pace_min_per_km(self) -> Optional[str]:
        if self.distance_meters <= 0 or self.moving_time_seconds <= 0:
            return None
        sec_per_km = self.moving_time_seconds / (self.distance_meters / 1000.0)
        minutes = int(sec_per_km // 60)
        seconds = int(sec_per_km % 60)
        return f"{minutes}:{seconds:02d} /km"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["distance_km"] = self.distance_km
        d["distance_miles"] = self.distance_miles
        d["duration_minutes"] = self.duration_minutes
        d["pace_min_per_km"] = self.pace_min_per_km
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Activity":
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class TrainingLoadMetrics:
    """Calculated sports science training load and fatigue indicators."""
    date: str
    acute_training_load: float      # ATL (Fatigue) ~ 7-day exponentially weighted load
    chronic_training_load: float    # CTL (Fitness) ~ 42-day exponentially weighted load
    training_stress_balance: float  # TSB (Form / Readiness) = CTL - ATL
    acwr: float                     # Acute:Chronic Workload Ratio = ATL / max(CTL, 1.0)
    weekly_total_km: float
    weekly_total_hours: float
    weekly_trimp: float
    risk_zone: str                  # "Under-trained", "Optimal / Sweet Spot", "Overreaching", "Danger Zone"
    rest_recommended_hours: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingLoadMetrics":
        return cls(**data)


@dataclass
class ProactiveAction:
    """Specific, concrete recommendation for the athlete."""
    title: str
    description: str
    priority: int  # 1 (Highest) to 3 (Lowest)
    action_type: str  # "rest", "nutrition", "workout_mod", "hydration", "mobility"


@dataclass
class HealthFeedback:
    """Proactive feedback generated by the agent."""
    feedback_id: str
    timestamp: str
    feedback_type: FeedbackType
    severity: AlertSeverity
    summary_headline: str
    detailed_feedback: str
    key_metrics: Dict[str, Any]
    action_items: List[ProactiveAction]
    suggested_today_workout: Optional[str] = None
    suggested_recovery_protocol: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["feedback_type"] = self.feedback_type.value if isinstance(self.feedback_type, Enum) else self.feedback_type
        d["severity"] = self.severity.value if isinstance(self.severity, Enum) else self.severity
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HealthFeedback":
        data_copy = dict(data)
        if isinstance(data_copy.get("feedback_type"), str):
            data_copy["feedback_type"] = FeedbackType(data_copy["feedback_type"])
        if isinstance(data_copy.get("severity"), str):
            data_copy["severity"] = AlertSeverity(data_copy["severity"])
        if "action_items" in data_copy and data_copy["action_items"]:
            data_copy["action_items"] = [
                item if isinstance(item, ProactiveAction) else ProactiveAction(**item)
                for item in data_copy["action_items"]
            ]
        return cls(**data_copy)
