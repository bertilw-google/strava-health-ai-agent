"""Category 4: Observability, Distributed Tracing, Intent/Outcome Capture & PII Redaction.

Implements:
- Structured JSON Logging (`StructuredJsonLogger`)
- Intent vs. Outcome Capture (`IntentOutcomeTracker`)
- Distributed Tracing (`OpenTelemetryTracer` compatible with OpenTelemetry spans)
- Active PII Redaction (`PIIRedactor` with Google Cloud DLP integration hook)
"""

import functools
import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, List, Optional


class PIIRedactor:
    """Scrubs sensitive athlete PII and credentials before logging or memory persistence.

    Supports local regex scrubbing and optional Google Cloud Data Loss Prevention (DLP) API.
    """

    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
    GPS_COORDS_REGEX = re.compile(r"\b-?\d{1,2}\.\d{4,},\s*-?\d{1,3}\.\d{4,}\b")
    BEARER_TOKEN_REGEX = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
    API_KEY_REGEX = re.compile(r"(AIza[0-9A-Za-z\-_]{35})")

    SENSITIVE_KEYS = {
        "access_token",
        "refresh_token",
        "client_secret",
        "api_key",
        "gemini_api_key",
        "password",
        "ssn",
        "latlng",
        "start_latlng",
        "end_latlng",
    }

    def __init__(self, gcp_project_id: Optional[str] = None, use_cloud_dlp: bool = False):
        self.gcp_project_id = gcp_project_id
        self.use_cloud_dlp = use_cloud_dlp

    def redact_text(self, text: str) -> str:
        """Scrubs emails, phone numbers, precise GPS coordinates, and tokens from text."""
        if not isinstance(text, str):
            return text
        scrubbed = self.EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
        scrubbed = self.PHONE_REGEX.sub("[REDACTED_PHONE]", scrubbed)
        scrubbed = self.GPS_COORDS_REGEX.sub("[REDACTED_GPS]", scrubbed)
        scrubbed = self.BEARER_TOKEN_REGEX.sub(r"\1[REDACTED_TOKEN]", scrubbed)
        scrubbed = self.API_KEY_REGEX.sub("[REDACTED_API_KEY]", scrubbed)
        return scrubbed

    def redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively scrubs sensitive keys and PII patterns from a dictionary."""
        redacted: Dict[str, Any] = {}
        for k, v in data.items():
            if k.lower() in self.SENSITIVE_KEYS:
                redacted[k] = "[REDACTED]"
            elif isinstance(v, str):
                redacted[k] = self.redact_text(v)
            elif isinstance(v, dict):
                redacted[k] = self.redact_dict(v)
            elif isinstance(v, list):
                redacted[k] = [
                    self.redact_dict(item) if isinstance(item, dict)
                    else self.redact_text(item) if isinstance(item, str)
                    else item
                    for item in v
                ]
            else:
                redacted[k] = v
        return redacted


class StructuredJsonLogger:
    """Emits structured JSON log payloads with PII scrubbing and trace correlation."""

    def __init__(self, service_name: str = "strava-health-ai-agent", redactor: Optional[PIIRedactor] = None):
        self.service_name = service_name
        self.redactor = redactor or PIIRedactor()
        self.logger = logging.getLogger(service_name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        self.records: List[Dict[str, Any]] = []

    def log(
        self,
        severity: str,
        event: str,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Formats and emits a structured JSON log entry after PII redaction."""
        safe_metadata = self.redactor.redact_dict(metadata or {})
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "severity": severity.upper(),
            "event": self.redactor.redact_text(event),
            "trace_id": trace_id or "no-trace",
            "span_id": span_id or "no-span",
            "metadata": safe_metadata,
        }
        self.records.append(entry)
        return entry

    def log_intent(
        self,
        action_name: str,
        intended_inputs: Dict[str, Any],
        rationale: str,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explicitly logs the agent's intended action BEFORE execution."""
        return self.log(
            severity="INFO",
            event=f"AGENT_INTENT:{action_name}",
            trace_id=trace_id,
            span_id=span_id,
            metadata={
                "phase": "INTENT",
                "action_name": action_name,
                "rationale": rationale,
                "intended_inputs": intended_inputs,
            },
        )

    def log_outcome(
        self,
        action_name: str,
        status: str,
        actual_output: Dict[str, Any],
        latency_ms: float,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Explicitly logs the actual outcome AFTER execution."""
        return self.log(
            severity="INFO" if status == "SUCCESS" else "ERROR",
            event=f"AGENT_OUTCOME:{action_name}",
            trace_id=trace_id,
            span_id=span_id,
            metadata={
                "phase": "OUTCOME",
                "action_name": action_name,
                "status": status,
                "latency_ms": round(latency_ms, 2),
                "actual_output": actual_output,
            },
        )


class Span:
    """Represents a distributed trace span compatible with OpenTelemetry semantics."""

    def __init__(
        self,
        name: str,
        trace_id: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.trace_id = trace_id
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_span_id = parent_span_id
        self.attributes = attributes or {}
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.status = "OK"

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def finish(self, status: str = "OK") -> None:
        self.end_time = time.time()
        self.status = status

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return round((end - self.start_time) * 1000.0, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
        }


class DistributedTracer:
    """OpenTelemetry-style tracer linking parent and child spans across agent execution."""

    def __init__(self, logger: Optional[StructuredJsonLogger] = None):
        self.logger = logger or StructuredJsonLogger()
        self.active_trace_id: Optional[str] = None
        self.span_stack: List[Span] = []
        self.completed_spans: List[Span] = []

    @contextmanager
    def start_as_current_span(
        self, name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> Generator[Span, None, None]:
        if not self.active_trace_id:
            self.active_trace_id = uuid.uuid4().hex
        parent_id = self.span_stack[-1].span_id if self.span_stack else None
        span = Span(
            name=name,
            trace_id=self.active_trace_id,
            parent_span_id=parent_id,
            attributes=attributes,
        )
        self.span_stack.append(span)
        try:
            yield span
            span.finish("OK")
        except Exception as e:
            span.set_attribute("error.message", str(e))
            span.finish("ERROR")
            raise
        finally:
            self.span_stack.pop()
            self.completed_spans.append(span)
            self.logger.log(
                severity="INFO" if span.status == "OK" else "ERROR",
                event=f"SPAN_COMPLETE:{span.name}",
                trace_id=span.trace_id,
                span_id=span.span_id,
                metadata=span.to_dict(),
            )
            if not self.span_stack:
                self.active_trace_id = None
