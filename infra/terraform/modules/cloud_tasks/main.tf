# Cloud Tasks — async job queue for the pipeline. Replaces Celery+Redis for long-running tasks.
# GCP infrastructure module.
# Attempts must span the export worker processing lease so active duplicate deliveries
# can retry after the lease becomes reclaimable.

resource "google_cloud_tasks_queue" "pipeline" {
  project  = var.project_id
  location = var.region
  name     = var.queue_name

  rate_limits {
    max_concurrent_dispatches = var.max_concurrent_dispatches
    max_dispatches_per_second = var.max_dispatches_per_second
  }

  retry_config {
    max_attempts       = 17
    min_backoff        = "30s"
    max_backoff        = "300s"
    max_doublings      = 4
    max_retry_duration = "4500s"
  }
}

resource "google_cloud_tasks_queue_iam_member" "enqueuer" {
  for_each = toset(var.enqueuer_service_account_emails)

  project  = var.project_id
  location = var.region
  name     = google_cloud_tasks_queue.pipeline.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${each.value}"
}
