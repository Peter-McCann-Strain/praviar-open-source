# Dedicated private Cloud Run Job for the production vision runtime preflight.
# The runtime gets its own service account, routes all traffic through Direct
# VPC egress, and is tagged with an egress-deny firewall rule. No invoker IAM
# binding is created.

resource "google_service_account" "vision" {
  project      = var.project_id
  account_id   = "${var.env}-vision-job"
  display_name = "${var.env} vision preflight runtime"
  description  = "No-network runtime identity for the digest-bound vision release preflight."
}

resource "google_service_account_iam_member" "deployer_can_act_as" {
  service_account_id = google_service_account.vision.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${var.deployer_service_account_email}"
}

resource "google_compute_firewall" "deny_runtime_egress" {
  project     = var.project_id
  name        = "${var.env}-vision-runtime-deny-egress"
  network     = var.network_id
  direction   = "EGRESS"
  priority    = 100
  target_tags = ["${var.env}-vision-offline"]

  destination_ranges = ["0.0.0.0/0"]

  deny {
    protocol = "all"
  }
}

resource "google_cloud_run_v2_job" "vision" {
  project             = var.project_id
  name                = var.job_name
  location            = var.region
  deletion_protection = var.deletion_protection

  binary_authorization {
    use_default = true
  }

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.vision.email
      timeout         = var.task_timeout
      max_retries     = 0

      vpc_access {
        network_interfaces {
          network    = var.network_id
          subnetwork = var.subnetwork_id
          tags       = ["${var.env}-vision-offline"]
        }
        egress = "ALL_TRAFFIC"
      }

      containers {
        image   = var.image
        command = ["python", "-m", "praviar_pipeline.vision_production"]
        args    = ["preflight", "--production"]

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        env {
          name  = "APP_ENV"
          value = "prod"
        }
        env {
          name  = "DEPLOYMENT_ENV"
          value = var.env
        }
        env {
          name  = "HF_HUB_OFFLINE"
          value = "1"
        }
        env {
          name  = "TRANSFORMERS_OFFLINE"
          value = "1"
        }
        env {
          name  = "PIP_NO_INDEX"
          value = "1"
        }
        env {
          name  = "PYTHONNOUSERSITE"
          value = "1"
        }
        env {
          name  = "PRAVIAR_VISION_RUNTIME_ROOT"
          value = "/app/praviar_pipeline"
        }
        env {
          name  = "PRAVIAR_VISION_ROSTER_PATH"
          value = "/app/praviar_pipeline/src/praviar_pipeline/data/vision-production-roster.v2.json"
        }
        env {
          name  = "PRAVIAR_ML_BOM_PATH"
          value = "/app/docs/trust/evidence/supply-chain/ml-bom-local-2026-05-25.json"
        }
        env {
          name  = "PRAVIAR_VISION_ROSTER_SHA256"
          value = var.roster_sha256
        }
        env {
          name  = "PRAVIAR_ML_BOM_SHA256"
          value = var.ml_bom_sha256
        }
      }
    }
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
    job         = "vision-preflight"
  }

  lifecycle {
    precondition {
      condition = var.image == format(
        "%s@%s",
        var.approved_image_repository,
        var.required_image_digest,
      )
      error_message = "Vision job image must equal the approved vision-worker repository at the release-certified digest."
    }
  }

  depends_on = [
    google_compute_firewall.deny_runtime_egress,
    google_service_account_iam_member.deployer_can_act_as,
  ]
}
