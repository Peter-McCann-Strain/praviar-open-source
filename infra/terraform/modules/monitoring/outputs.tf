output "alert_policy_names" {
  description = "Map of alert policy logical names to their Cloud Monitoring resource names."
  value = {
    api_error_rate        = google_monitoring_alert_policy.api_error_rate.name
    worker_failure_rate   = google_monitoring_alert_policy.worker_failure_rate.name
    api_p99_latency       = google_monitoring_alert_policy.api_p99_latency.name
    cloudsql_cpu          = google_monitoring_alert_policy.cloudsql_cpu.name
    cloudsql_connections  = google_monitoring_alert_policy.cloudsql_connections.name
    memorystore_memory    = google_monitoring_alert_policy.memorystore_memory.name
    stale_sweep_liveness  = google_monitoring_alert_policy.stale_sweep_liveness.name
    stale_recovery_health = google_monitoring_alert_policy.stale_recovery_health.name
  }
}

output "email_notification_channel_name" {
  description = "Resource name of the auto-created email notification channel. Empty string if var.alert_email was not set."
  value       = length(google_monitoring_notification_channel.email) > 0 ? google_monitoring_notification_channel.email[0].name : ""
}
