output "queue_name" {
  value = google_cloud_tasks_queue.pipeline.name
}

output "queue_id" {
  description = "Fully qualified queue ID for API/workers env vars."
  value       = "projects/${var.project_id}/locations/${var.region}/queues/${google_cloud_tasks_queue.pipeline.name}"
  depends_on  = [google_cloud_tasks_queue_iam_member.enqueuer]
}
