# Single-Project Infrastructure as Code for Vertex AI Agent Platform (Agent Runtime)
# Provisions Google Cloud Secret Manager resources and binds least-privilege IAM roles.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "Target Google Cloud Project ID"
  type        = string
  default     = "capsules-agents-1"
}

variable "region" {
  description = "Google Cloud region for Vertex AI Agent Runtime"
  type        = string
  default     = "us-central1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Google Cloud Secret Manager Secrets (Zero Hardcoded Values)
resource "google_secret_manager_secret" "strava_client_id" {
  secret_id = "STRAVA_CLIENT_ID"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "strava_client_secret" {
  secret_id = "STRAVA_CLIENT_SECRET"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "strava_access_token" {
  secret_id = "STRAVA_ACCESS_TOKEN"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "strava_refresh_token" {
  secret_id = "STRAVA_REFRESH_TOKEN"
  replication {
    auto {}
  }
}

# 2. Dedicated Least-Privilege Agent Runtime Service Account
resource "google_service_account" "agent_runtime_sa" {
  account_id   = "strava-agent-runtime-sa"
  display_name = "Strava Health AI Agent Runtime Service Account"
}

# Least-privilege IAM bindings per secret
resource "google_secret_manager_secret_iam_member" "client_id_accessor" {
  secret_id = google_secret_manager_secret.strava_client_id.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "client_secret_accessor" {
  secret_id = google_secret_manager_secret.strava_client_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "access_token_accessor" {
  secret_id = google_secret_manager_secret.strava_access_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "refresh_token_accessor" {
  secret_id = google_secret_manager_secret.strava_refresh_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

# Least-privilege Vertex AI, Cloud Logging & Cloud Trace roles
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}
