# Cloud Run Job module for one-shot operational tasks such as Alembic
# migrations. Jobs share the same network, secrets, and service-account
# contract as the API service, but execute explicitly during deploy.

resource "google_cloud_run_v2_job" "job" {
  project             = var.project_id
  name                = var.job_name
  location            = var.region
  deletion_protection = var.deletion_protection

  dynamic "binary_authorization" {
    for_each = var.binary_authorization_enabled ? [1] : []
    content {
      use_default = true
    }
  }

  template {
    task_count  = var.task_count
    parallelism = var.parallelism

    template {
      service_account = var.service_account_email
      timeout         = var.task_timeout
      max_retries     = var.max_retries

      vpc_access {
        network_interfaces {
          network    = var.network_id
          subnetwork = var.subnetwork_id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image   = var.image
        command = var.command
        args    = var.args

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        dynamic "env" {
          for_each = var.env_vars
          content {
            name  = env.key
            value = env.value
          }
        }

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

        dynamic "volume_mounts" {
          for_each = var.cloudsql_connection_name != "" ? [1] : []
          content {
            name       = "cloudsql"
            mount_path = "/cloudsql"
          }
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
    }
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
    job         = var.job_name
  }

  lifecycle {
    precondition {
      condition = var.image == format(
        "%s@%s",
        var.approved_image_repository,
        var.required_image_digest,
      )
      error_message = "Cloud Run Job image must equal the approved API repository at the release-certified digest."
    }
  }
}
