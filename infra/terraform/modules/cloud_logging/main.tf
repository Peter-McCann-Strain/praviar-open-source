# Cloud Logging — log buckets + audit archive sink with 7-year retention for SOC 2 evidence.

locals {
  # Data Access logs are opt-in. Keep the high-value data plane explicit so a
  # newly enabled, high-volume service cannot silently create an unbounded log
  # or privacy cost while storage, secrets, keys, SQL, analytics, and runtime
  # access remain covered.
  data_access_audit_services = toset([
    "bigquery.googleapis.com",
    "cloudkms.googleapis.com",
    "cloudsql.googleapis.com",
    "logging.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])
}

# 30-day operational log bucket (default for application logs).
resource "google_logging_project_bucket_config" "default" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = 30
}

# Dedicated destination for Cloud Storage server access logs. A logging bucket
# must not log to itself because that would recursively generate more access
# logs, so the scoped Checkov exception is intentional.
resource "google_storage_bucket" "access_logs" {
  # checkov:skip=CKV_GCP_62:Dedicated server-access-log destination; self-logging would recurse.
  project       = var.project_id
  name          = "${var.project_id}-storage-access-logs"
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 400
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "compliance"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Google Cloud Storage writes server access logs as this delivery group.
resource "google_storage_bucket_iam_member" "access_log_writer" {
  bucket = google_storage_bucket.access_logs.name
  role   = "roles/storage.objectCreator"
  member = "group:cloud-storage-analytics@google.com"
}

# 7-year audit archive bucket for Data Access logs.
resource "google_storage_bucket" "audit_archive" {
  project       = var.project_id
  name          = "${var.project_id}-audit-archive"
  location      = var.region
  storage_class = "ARCHIVE"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  retention_policy {
    retention_period = 220752000 # 7 years in seconds
    is_locked        = false     # Lock manually via gcloud after first apply.
  }

  versioning {
    enabled = true
  }

  logging {
    log_bucket        = google_storage_bucket.access_logs.name
    log_object_prefix = "audit-archive/"
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "compliance"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Project sinks cannot archive Data Access entries that the services never
# emit. Enable all three Data Access permission categories for the sensitive
# services above without exempting any principals.
resource "google_project_iam_audit_config" "data_access" {
  for_each = local.data_access_audit_services

  project = var.project_id
  service = each.value

  audit_log_config {
    log_type = "ADMIN_READ"
  }

  audit_log_config {
    log_type = "DATA_READ"
  }

  audit_log_config {
    log_type = "DATA_WRITE"
  }
}

# Sink: route Data Access logs to the audit archive bucket.
resource "google_logging_project_sink" "data_access" {
  project = var.project_id
  name    = "data-access-audit-archive"

  destination = "storage.googleapis.com/${google_storage_bucket.audit_archive.name}"

  filter = "logName:\"cloudaudit.googleapis.com%2Fdata_access\""

  unique_writer_identity = true
}

# Sink writer needs write access to the archive bucket.
resource "google_storage_bucket_iam_member" "sink_writer" {
  bucket = google_storage_bucket.audit_archive.name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.data_access.writer_identity
}
