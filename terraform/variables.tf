variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region for Cloud Run and Scheduler"
  type        = string
  default     = "us-central1"
}

variable "container_image" {
  description = "Artifact Registry container image URI for Strava Health AI Agent"
  type        = string
  default     = "gcr.io/my-project/strava-health-ai-agent:latest"
}
