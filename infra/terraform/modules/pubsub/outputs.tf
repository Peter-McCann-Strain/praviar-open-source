output "job_events_topic_id" {
  description = "Fully-qualified Pub/Sub topic ID for job-events (projects/<project>/topics/job-events)."
  value       = google_pubsub_topic.job_events.id
}

output "job_dlq_topic_id" {
  description = "Fully-qualified Pub/Sub topic ID for job-dlq (projects/<project>/topics/job-dlq)."
  value       = google_pubsub_topic.job_dlq.id
}

output "job_events_subscription_id" {
  description = "Fully-qualified subscription ID for the BigQuery ingest subscription on job-events."
  value       = google_pubsub_subscription.job_events_bq.id
}
