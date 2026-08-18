# Cloud Run service module — reused for `api` and `workers`.
# GCP infrastructure module.

resource "google_cloud_run_v2_service" "service" {
  project             = var.project_id
  name                = var.service_name
  location            = var.region
  deletion_protection = false

  # INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER for API (fronted by HTTPS LB).
  # INGRESS_TRAFFIC_INTERNAL_ONLY for workers (Cloud Tasks OIDC only).
  ingress = var.ingress

  dynamic "binary_authorization" {
    for_each = var.binary_authorization_enabled ? [1] : []
    content {
      use_default = true
    }
  }

  template {
    service_account                  = var.service_account_email
    max_instance_request_concurrency = var.max_instance_request_concurrency

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    vpc_access {
      network_interfaces {
        network    = var.network_id
        subnetwork = var.subnetwork_id
      }
      egress = var.vpc_egress
    }

    timeout = var.request_timeout

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = !var.cpu_always_on
        startup_cpu_boost = var.startup_cpu_boost
      }

      ports {
        container_port = var.container_port
      }

      # Static env vars (non-sensitive).
      dynamic "env" {
        for_each = var.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secret env vars — pulled from Secret Manager at startup (no app code change).
      dynamic "env" {
        for_each = var.secret_env_vars
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = env.value.version
            }
          }
        }
      }

      # Cloud SQL Auth Proxy unix socket — DSN: postgresql+asyncpg://user:pass@/db?host=/cloudsql/<conn>
      dynamic "volume_mounts" {
        for_each = var.cloudsql_connection_name != "" ? [1] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      startup_probe {
        http_get {
          path = var.health_path
        }
        initial_delay_seconds = 0
        period_seconds        = 5
        timeout_seconds       = 5
        failure_threshold     = 30
      }

      liveness_probe {
        http_get {
          path = var.health_path
        }
        initial_delay_seconds = 30
        period_seconds        = 30
        timeout_seconds       = 10
        failure_threshold     = 3
      }
    }

    dynamic "volumes" {
      for_each = var.cloudsql_connection_name != "" ? [1] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [var.cloudsql_connection_name]
        }
      }
    }

    labels = {
      env         = var.env
      owner       = "praviar"
      cost-center = "engineering"
      service     = var.service_name
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    # CI may add provider annotations, but the certified image remains a
    # Terraform-managed contract and must never drift out-of-band.
    ignore_changes = [
      client,
      client_version,
      template[0].annotations,
    ]

    precondition {
      condition = (
        var.required_image_digest == "" ||
        endswith(var.image, "@${var.required_image_digest}")
      )
      error_message = "Cloud Run image must equal the exact certified OCI image digest."
    }
  }
}

# Optional unauthenticated invocation. If a service uses load-balancer-only
# ingress, Terraform and deploy probes must route through the managed perimeter.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count = var.allow_public_invocation ? 1 : 0

  project  = google_cloud_run_v2_service.service.project
  location = google_cloud_run_v2_service.service.location
  name     = google_cloud_run_v2_service.service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# OIDC-authenticated invoker (workers — only Cloud Tasks can call).
resource "google_cloud_run_v2_service_iam_member" "oidc_invoker" {
  for_each = toset(var.oidc_invoker_sa_emails)

  project  = google_cloud_run_v2_service.service.project
  location = google_cloud_run_v2_service.service.location
  name     = google_cloud_run_v2_service.service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.key}"
}
