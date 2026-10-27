# Category 5: Infrastructure as Code (Terraform)
# Provisions Google Cloud Secret Manager, Cloud Run Service, and Cloud Scheduler
# triggers for the Proactive Strava Health AI Agent.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Secure Secret Manager Resources
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "GEMINI_API_KEY"
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

resource "google_secret_manager_secret" "strava_refresh_token" {
  secret_id = "STRAVA_REFRESH_TOKEN"
  replication {
    auto {}
  }
}

# 2. Dedicated Agent Service Account
resource "google_service_account" "strava_agent_sa" {
  account_id   = "strava-health-agent-sa"
  display_name = "Strava Health AI Agent Service Account"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.strava_agent_sa.email}"
}

resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.strava_agent_sa.email}"
}

# 3. Cloud Run v2 Service hosting the Agent & MCP Endpoint
resource "google_cloud_run_v2_service" "strava_health_agent" {
  name     = "strava-health-ai-agent"
  location = var.region

  template {
    service_account = google_service_account.strava_agent_sa.email

    containers {
      image = var.container_image

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "STRAVA_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.strava_client_secret.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "STRAVA_REFRESH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.strava_refresh_token.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}

# 4. Cloud Scheduler Proactive Trigger (7:00 AM Daily Morning Readiness Briefing)
resource "google_cloud_scheduler_job" "morning_readiness_trigger" {
  name             = "strava-morning-readiness-briefing"
  description      = "Triggers proactive 7:00 AM daily athlete readiness and ACWR evaluation"
  schedule         = "0 7 * * *"
  time_zone        = "UTC"
  attempt_deadline = "180s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.strava_health_agent.uri}/triggers/morning-readiness"

    oidc_token {
      service_account_email = google_service_account.strava_agent_sa.email
    }
  }
}
