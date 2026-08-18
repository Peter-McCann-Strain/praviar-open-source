# Cloud SQL Postgres 16 — primary OLTP for the API.
# GCP infrastructure module.
# Database name: praviar (fresh per execution plan §8 — no migration from praviar).

resource "google_sql_database_instance" "primary" {
  # checkov:skip=CKV_GCP_6:ENCRYPTED_ONLY rejects plaintext; Cloud Run connects through the TLS 1.3 Cloud SQL Auth Proxy rather than direct client-certificate authentication.
  # checkov:skip=CKV_GCP_108:Auth Proxy and Cloud Audit logs provide workload identity; reverse-DNS hostname logging adds latency without stronger attribution.
  # checkov:skip=CKV_GCP_111:pgaudit records DDL, role, and write activity without indiscriminately logging sensitive read statements.
  # checkov:skip=CKV2_GCP_13:Query Insights captures duration telemetry without the volume of logging every completed statement.
  project          = var.project_id
  name             = var.instance_name
  region           = var.region
  database_version = "POSTGRES_16"

  # deletion_protection is set to true in prod and false in staging/dev.
  # This is a GCP API-level guard (blocks DELETE regardless of who calls it),
  # which is more robust than the Terraform-only prevent_destroy meta-argument.
  # prevent_destroy is intentionally absent from this module so staging/dev
  # can be torn down; prod relies on deletion_protection=true instead.
  deletion_protection = var.deletion_protection

  settings {
    tier                  = var.tier
    edition               = var.edition
    availability_type     = var.availability_type
    disk_type             = "PD_SSD"
    disk_size             = var.disk_size_gb
    disk_autoresize       = true
    disk_autoresize_limit = var.disk_max_size_gb

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = var.vpc_id
      enable_private_path_for_google_cloud_services = true
      # Cloud Run uses the Cloud SQL Auth Proxy (TLS 1.3), and this also rejects
      # any future direct plaintext database connection.
      ssl_mode = "ENCRYPTED_ONLY"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 6 # 6am UTC
      update_track = "stable"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "off"
    }

    # Record security-relevant changes without logging query parameters or all
    # reads, both of which could expose customer patent material.
    database_flags {
      name  = "cloudsql.enable_pgaudit"
      value = "on"
    }

    database_flags {
      name  = "pgaudit.log"
      value = "ddl,role,write"
    }

    database_flags {
      name  = "pgaudit.log_parameter"
      value = "off"
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }

    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }

    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }

    database_flags {
      name  = "log_min_messages"
      value = "error"
    }

    database_flags {
      name  = "log_min_error_statement"
      value = "error"
    }

    user_labels = {
      env         = var.env
      owner       = "praviar"
      cost-center = "engineering"
    }
  }
}

# The application database — name fixed as "praviar" per execution plan §8.
resource "google_sql_database" "praviar" {
  project   = var.project_id
  instance  = google_sql_database_instance.primary.name
  name      = var.database_name
  charset   = "UTF8"
  collation = "en_US.UTF8"
}

# Bootstrap user — runs the one-shot role/grant bootstrap job before Alembic.
resource "google_sql_user" "bootstrap" {
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  name     = var.bootstrap_user
  password = var.bootstrap_user_password
}

# API user — password stored in Secret Manager (see secret_manager module).
resource "google_sql_user" "api" {
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  name     = var.app_user
  password = var.app_user_password
}

# Worker user — used by queue-owned background jobs with explicit org binding.
resource "google_sql_user" "worker" {
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  name     = var.worker_user
  password = var.worker_user_password
}

resource "google_sql_user" "epo_checkpoint_writer" {
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  name     = var.epo_checkpoint_writer_user
  password = var.epo_checkpoint_writer_user_password
}

# Migration user — connects for Alembic and must SET ROLE alembic_runner.
resource "google_sql_user" "migrator" {
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  name     = var.migration_user
  password = var.migration_user_password
}

resource "google_sql_user" "claimed_use_writer" {
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  name     = var.claimed_use_writer_user
  password = var.claimed_use_writer_user_password
}

resource "google_sql_user" "global_erasure" {
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  name     = var.global_erasure_user
  password = var.global_erasure_user_password
}
