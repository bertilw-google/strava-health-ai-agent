"""Category 5: Secure Secret Management via Google Cloud Secret Manager.

Ensures zero hardcoded API keys or OAuth tokens in source code. Fetches secrets
dynamically from Google Cloud Secret Manager (`projects/*/secrets/*/versions/latest`)
with graceful fallback to secure environment variable injection.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class SecretManagerClient:
    """Retrieves API credentials from Google Cloud Secret Manager or environment."""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")

    def get_secret(self, secret_id: str, version_id: str = "latest") -> Optional[str]:
        """Resolves a secret by checking Google Cloud Secret Manager first, then env vars.

        Args:
            secret_id: Secret identifier (e.g., 'GEMINI_API_KEY', 'STRAVA_CLIENT_SECRET').
            version_id: Secret version (defaults to 'latest').

        Returns:
            Resolved secret string or None if unavailable.
        """
        # 1. Attempt Google Cloud Secret Manager SDK if project_id is configured
        if self.project_id:
            try:
                from google.cloud import secretmanager  # type: ignore
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version_id}"
                response = client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as exc:
                logger.debug(
                    "Cloud Secret Manager lookup skipped for %s (falling back to env): %s",
                    secret_id,
                    exc,
                )

        # 2. Secure environment variable injection fallback
        return os.environ.get(secret_id)
