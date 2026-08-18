# Artifact Registry — Docker images for Cloud Run.
# Single repository for all images: api, workers, ocsr-cascade.

resource "google_artifact_registry_repository" "containers" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "Praviar container images"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  vulnerability_scanning_config {
    enablement_config = "INHERITED"
  }

  cleanup_policies {
    id     = "keep-last-30-tagged"
    action = "KEEP"

    most_recent_versions {
      keep_count = 30
    }
  }

  cleanup_policies {
    id     = "delete-untagged-after-14d"
    action = "DELETE"

    condition {
      tag_state  = "UNTAGGED"
      older_than = "1209600s" # 14 days
    }
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
  }
}

# Cloud Build SA can push images.
resource "google_artifact_registry_repository_iam_member" "cloudbuild_writer" {
  project    = var.project_id
  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${var.cloudbuild_service_account}"
}
