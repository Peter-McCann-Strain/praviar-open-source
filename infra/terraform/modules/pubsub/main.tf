# Pub/Sub module — job lifecycle event bus.
#
# Topics:
#   job-events  — pipeline job completion / failure events.
#                 Subscriptions:
#                   (a) BigQuery streaming ingest into the analytics dataset.
#                   (b) Optional push subscription to an internal webhook.
#   job-dlq     — dead-letter destination for Cloud Tasks failed jobs.
#                 No subscriptions — operators pull manually.
#
# The Pub/Sub service agent requires bigquery.dataEditor on the analytics
# dataset so it can stream rows. That IAM binding is also managed here.

# ---------------------------------------------------------------------------
# Pub/Sub service agent — project-level SA managed by GCP.
# We reference it by convention; it is not a user-managed SA.
# ---------------------------------------------------------------------------
data "google_project" "project" {
  project_id = var.project_id
}

locals {
  pubsub_sa = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  common_labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
  }
}

# ---------------------------------------------------------------------------
# Topic: job-events
# ---------------------------------------------------------------------------
resource "google_pubsub_topic" "job_events" {
  project = var.project_id
  name    = "job-events"

  # 7 days — long enough to replay a weekend outage without data loss.
  message_retention_duration = "604800s"

  labels = local.common_labels
}

# ---------------------------------------------------------------------------
# Topic: job-dlq (dead-letter for Cloud Tasks)
# ---------------------------------------------------------------------------
resource "google_pubsub_topic" "job_dlq" {
  project = var.project_id
  name    = "job-dlq"

  message_retention_duration = "604800s"

  labels = local.common_labels
}

# ---------------------------------------------------------------------------
# IAM: Pub/Sub SA → BigQuery dataEditor on the analytics dataset.
# Required for the BigQuery subscription to write rows.
# ---------------------------------------------------------------------------
resource "google_bigquery_dataset_iam_member" "pubsub_bq_editor" {
  project    = var.project_id
  dataset_id = var.bq_dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = local.pubsub_sa
}

# ---------------------------------------------------------------------------
# Subscription (a): BigQuery ingest for job_events analytics.
# Streams every message into <project>:<bq_dataset_id>.job_events.
# write_metadata=true adds message_id, publish_time, attributes columns.
# drop_unknown_fields=true avoids failures when schema is extended.
# ---------------------------------------------------------------------------
resource "google_pubsub_subscription" "job_events_bq" {
  project = var.project_id
  name    = "job-events-bq"
  topic   = google_pubsub_topic.job_events.name

  # BigQuery subscriptions do not use ack_deadline / retain_acked_messages.
  bigquery_config {
    table               = "${var.project_id}:${var.bq_dataset_id}.job_events"
    write_metadata      = true
    drop_unknown_fields = true
  }

  labels = local.common_labels

  depends_on = [google_bigquery_dataset_iam_member.pubsub_bq_editor]
}

# ---------------------------------------------------------------------------
# Subscription (b): Push webhook (optional).
# Only created when var.job_webhook_url is non-empty.
# ---------------------------------------------------------------------------
resource "google_pubsub_subscription" "job_events_webhook" {
  count = var.job_webhook_url != "" ? 1 : 0

  project = var.project_id
  name    = "job-events-webhook"
  topic   = google_pubsub_topic.job_events.name

  ack_deadline_seconds       = 60
  message_retention_duration = "600s"

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  push_config {
    push_endpoint = var.job_webhook_url

    # Attach OIDC token so the receiving service can verify the caller.
    # The Pub/Sub SA is used as the OIDC service account.
    oidc_token {
      service_account_email = trimsuffix(trimprefix(local.pubsub_sa, "serviceAccount:"), "")
      audience              = var.job_webhook_url
    }
  }

  labels = local.common_labels
}
