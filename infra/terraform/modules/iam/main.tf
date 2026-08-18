# Runtime service accounts for Cloud Run services (least-privilege).
# GCP infrastructure module.

# API runtime SA — running the FastAPI service.
resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = var.api_sa_id
  display_name = "Praviar API runtime"
  description  = "Runtime identity for Cloud Run api service"
}

# Workers runtime SA — running the pipeline workers.
resource "google_service_account" "workers" {
  project      = var.project_id
  account_id   = var.workers_sa_id
  display_name = "Praviar workers runtime"
  description  = "Runtime identity for Cloud Run workers service + Cloud Run Jobs"
}

# DB bootstrap job SA — only runs the one-shot role/grant bootstrap job.
resource "google_service_account" "db_bootstrap" {
  project      = var.project_id
  account_id   = var.db_bootstrap_sa_id
  display_name = "Praviar database bootstrap job"
  description  = "Least-privilege identity for the database role/grant bootstrap Cloud Run Job"
}

# DB migration job SA — only runs Alembic with the migration DSN.
resource "google_service_account" "db_migration" {
  project      = var.project_id
  account_id   = var.db_migration_sa_id
  display_name = "Praviar database migration job"
  description  = "Least-privilege identity for the Alembic Cloud Run Job"
}

# Tasks invoker SA — Cloud Tasks signs OIDC tokens with this identity when calling
# the workers HTTP target. Only this SA can be `--oidc-service-account-email`.
resource "google_service_account" "tasks_invoker" {
  project      = var.project_id
  account_id   = var.tasks_invoker_sa_id
  display_name = "Praviar Cloud Tasks invoker"
}

# API role bindings — least privilege.
resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/bigquery.user",
    "roles/bigquery.dataViewer",
    "roles/cloudtrace.agent",
    "roles/monitoring.metricWriter",
    "roles/logging.logWriter",
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Workers role bindings — broader BigQuery, plus permission to be invoked by Cloud Tasks.
resource "google_project_iam_member" "workers_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/cloudkms.publicKeyViewer",
    "roles/bigquery.user",
    "roles/bigquery.dataEditor",
    "roles/cloudtrace.agent",
    "roles/monitoring.metricWriter",
    "roles/logging.logWriter",
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.workers.email}"
}

# DB bootstrap job role bindings. Secret access is granted per secret by the
# Secret Manager module, not at project scope.
resource "google_project_iam_member" "db_bootstrap_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.db_bootstrap.email}"
}

# DB migration job role bindings. Secret access is granted only to
# migration-database-url by the Secret Manager module.
resource "google_project_iam_member" "db_migration_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.db_migration.email}"
}

# Scoped GCS access — api and workers can only read/write the report-exports bucket.
# Project-level storage.objectAdmin is intentionally absent; this prevents either SA
# from reaching the audit-archive or Terraform state buckets.
resource "google_storage_bucket_iam_member" "api_report_exports" {
  bucket = var.report_exports_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "workers_report_exports" {
  bucket = var.report_exports_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.workers.email}"
}

# API and workers create Cloud Tasks carrying OIDC tokens for the dedicated
# tasks-invoker identity. Scope iam.serviceAccounts.actAs to that one service
# account; queue-level enqueuer permissions are owned by the Cloud Tasks module.
resource "google_service_account_iam_member" "runtime_can_act_as_tasks_invoker" {
  for_each = {
    api     = google_service_account.api.email
    workers = google_service_account.workers.email
  }

  service_account_id = google_service_account.tasks_invoker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${each.value}"
}
