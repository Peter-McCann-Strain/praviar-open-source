# Cloud Monitoring module — core SLO alert policies for Praviar.
#
# Alert policies:
#   1. api_error_rate        — Cloud Run API 5xx rate > 1 % over 5 min
#   2. worker_failure_rate   — Cloud Run workers 5xx rate > 5 % over 10 min
#   3. api_p99_latency       — Cloud Run API p99 latency > 5 000 ms over 5 min
#   4. cloudsql_cpu          — Cloud SQL CPU utilisation > 80 % for 5 min
#   5. cloudsql_connections  — Cloud SQL connection count > 200
#   6. memorystore_memory    — Redis memory usage ratio > 80 %
#   7. stale_sweep_liveness  — no successful stale-analysis sweep for 30 min
#   8. stale_recovery_health — expired RUNNING age, reclaim burst, or redrive failure
#
# An optional email notification channel is created when var.alert_email is set.

# ---------------------------------------------------------------------------
# Optional email notification channel
# ---------------------------------------------------------------------------
resource "google_monitoring_notification_channel" "email" {
  count = var.alert_email != "" ? 1 : 0

  project      = var.project_id
  display_name = "Praviar alerts — ${var.alert_email}"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  user_labels = {
    env   = var.env
    owner = "praviar"
  }
}

# Merge the auto-created channel (if any) with the caller-supplied list so all
# policies can reference a single local.
locals {
  all_channels = concat(
    var.notification_channel_ids,
    [for ch in google_monitoring_notification_channel.email : ch.name],
  )
}

# ---------------------------------------------------------------------------
# 1. API error rate — Cloud Run 5xx > 1 % over 5 minutes
# ---------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "api_error_rate" {
  project      = var.project_id
  display_name = "[${var.env}] API error rate > 1%"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "critical"
    service  = "api"
  }

  conditions {
    display_name = "API 5xx request rate > 1%"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_revision\"",
        "metric.type = \"run.googleapis.com/request_count\"",
        "metric.labels.response_code_class = \"5xx\"",
        "resource.labels.service_name = \"${var.api_service_name}\"",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 0.01
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

# ---------------------------------------------------------------------------
# 2. Worker job failure rate — Cloud Run workers 5xx > 5 % over 10 minutes
# ---------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "worker_failure_rate" {
  project      = var.project_id
  display_name = "[${var.env}] Worker failure rate > 5%"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "critical"
    service  = "workers"
  }

  conditions {
    display_name = "Workers 5xx request rate > 5%"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_revision\"",
        "metric.type = \"run.googleapis.com/request_count\"",
        "metric.labels.response_code_class = \"5xx\"",
        "resource.labels.service_name = \"${var.workers_service_name}\"",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      duration        = "600s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "3600s"
  }
}

# ---------------------------------------------------------------------------
# 3. API p99 latency > 5 000 ms over 5 minutes
# ---------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "api_p99_latency" {
  project      = var.project_id
  display_name = "[${var.env}] API p99 latency > 5000ms"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "warning"
    service  = "api"
  }

  conditions {
    display_name = "API p99 request latency > 5000ms"

    condition_threshold {
      # request_latencies is a distribution metric; use ALIGN_PERCENTILE_99.
      filter = join(" AND ", [
        "resource.type = \"cloud_run_revision\"",
        "metric.type = \"run.googleapis.com/request_latencies\"",
        "resource.labels.service_name = \"${var.api_service_name}\"",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 5000
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
        cross_series_reducer = "REDUCE_PERCENTILE_99"
        group_by_fields      = ["resource.labels.service_name"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

# ---------------------------------------------------------------------------
# 4. Cloud SQL CPU utilisation > 80 % for 5 minutes
# ---------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "cloudsql_cpu" {
  project      = var.project_id
  display_name = "[${var.env}] Cloud SQL CPU > 80%"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "warning"
    service  = "cloudsql"
  }

  conditions {
    display_name = "Cloud SQL CPU utilisation > 80%"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloudsql_database\"",
        "metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\"",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields      = ["resource.labels.database_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

# ---------------------------------------------------------------------------
# 5. Cloud SQL connection count > 200 (approaching pool limits)
# ---------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "cloudsql_connections" {
  project      = var.project_id
  display_name = "[${var.env}] Cloud SQL connections > 200"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "warning"
    service  = "cloudsql"
  }

  conditions {
    display_name = "Cloud SQL PostgreSQL backend count > 200"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloudsql_database\"",
        "metric.type = \"cloudsql.googleapis.com/database/postgresql/num_backends\"",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 200
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.database_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

# ---------------------------------------------------------------------------
# 6. Memorystore (Redis) memory usage ratio > 80 %
# ---------------------------------------------------------------------------
resource "google_monitoring_alert_policy" "memorystore_memory" {
  project      = var.project_id
  display_name = "[${var.env}] Redis memory usage > 80%"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "warning"
    service  = "memorystore"
  }

  conditions {
    display_name = "Redis memory usage ratio > 80%"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"redis_instance\"",
        "metric.type = \"redis.googleapis.com/stats/memory/usage_ratio\"",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields      = ["resource.labels.instance_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

# ---------------------------------------------------------------------------
# Stale-analysis recovery log metrics
#
# These mirror the application's low-cardinality Prometheus metrics but use
# structured Cloud Run logs as the Cloud Monitoring ingestion path. This keeps
# production alerts live even when a Managed Prometheus scraper is unavailable.
# ---------------------------------------------------------------------------

resource "google_logging_metric" "stale_analysis_sweep_success" {
  project     = var.project_id
  name        = "praviar_${var.env}_stale_analysis_sweep_success"
  description = "Successful stale-analysis reconciliation sweeps."
  filter = join(" AND ", [
    "resource.type = \"cloud_run_revision\"",
    "resource.labels.service_name = \"${var.workers_service_name}\"",
    "jsonPayload.event = \"stale_analysis_sweep.complete\"",
    "jsonPayload.error_count = 0",
  ])

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "stale_analysis_expired_running_age" {
  project         = var.project_id
  name            = "praviar_${var.env}_stale_analysis_expired_running_age"
  description     = "Age in seconds of expired RUNNING analyses reclaimed by the sweep."
  value_extractor = "EXTRACT(jsonPayload.expired_running_age_seconds)"
  filter = join(" AND ", [
    "resource.type = \"cloud_run_revision\"",
    "resource.labels.service_name = \"${var.workers_service_name}\"",
    "jsonPayload.event = \"stale_analysis_sweep.expired_running_reclaimed\"",
  ])

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "s"
  }

  bucket_options {
    explicit_buckets {
      bounds = [7200, 9000, 10800, 14400, 21600, 43200]
    }
  }
}

resource "google_logging_metric" "stale_analysis_reclaimed" {
  project     = var.project_id
  name        = "praviar_${var.env}_stale_analysis_reclaimed"
  description = "Expired RUNNING analyses reclaimed by stale-analysis reconciliation."
  filter = join(" AND ", [
    "resource.type = \"cloud_run_revision\"",
    "resource.labels.service_name = \"${var.workers_service_name}\"",
    "jsonPayload.event = \"stale_analysis_sweep.expired_running_reclaimed\"",
  ])

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "stale_analysis_redrive_failure" {
  project     = var.project_id
  name        = "praviar_${var.env}_stale_analysis_redrive_failure"
  description = "Stale-analysis reconciliation redrive dispatch failures."
  filter = join(" AND ", [
    "resource.type = \"cloud_run_revision\"",
    "resource.labels.service_name = \"${var.workers_service_name}\"",
    "jsonPayload.event = \"stale_analysis_sweep.redrive_failed\"",
  ])

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

# ---------------------------------------------------------------------------
# 7. Stale-analysis sweep liveness
# ---------------------------------------------------------------------------

resource "google_monitoring_alert_policy" "stale_sweep_liveness" {
  project      = var.project_id
  display_name = "[${var.env}] Stale-analysis sweep has no recent success"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "critical"
    service  = "api"
  }

  conditions {
    display_name = "No successful stale-analysis sweep for 30 minutes"

    condition_absent {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_revision\"",
        "metric.type = \"logging.googleapis.com/user/${google_logging_metric.stale_analysis_sweep_success.name}\"",
      ])
      duration = "1800s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

# ---------------------------------------------------------------------------
# 8. Stale-analysis recovery health
# ---------------------------------------------------------------------------

resource "google_monitoring_alert_policy" "stale_recovery_health" {
  project      = var.project_id
  display_name = "[${var.env}] Stale-analysis recovery degraded"
  combiner     = "OR"

  notification_channels = local.all_channels

  user_labels = {
    env      = var.env
    owner    = "praviar"
    severity = "critical"
    service  = "api"
  }

  conditions {
    display_name = "Expired RUNNING analysis age exceeds 2.5 hours"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_revision\"",
        "metric.type = \"logging.googleapis.com/user/${google_logging_metric.stale_analysis_expired_running_age.name}\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 9000
      duration        = "0s"

      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "More than three expired RUNNING analyses reclaimed in 15 minutes"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_revision\"",
        "metric.type = \"logging.googleapis.com/user/${google_logging_metric.stale_analysis_reclaimed.name}\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 3
      duration        = "0s"

      aggregations {
        alignment_period     = "900s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "Any stale-analysis redrive dispatch failure"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_revision\"",
        "metric.type = \"logging.googleapis.com/user/${google_logging_metric.stale_analysis_redrive_failure.name}\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}
