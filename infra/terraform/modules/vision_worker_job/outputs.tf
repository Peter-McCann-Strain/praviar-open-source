output "job_name" {
  value       = google_cloud_run_v2_job.vision.name
  description = "Dedicated private vision preflight job name."
}

output "job_id" {
  value       = google_cloud_run_v2_job.vision.id
  description = "Dedicated private vision preflight job resource ID."
}

output "runtime_service_account_email" {
  value       = google_service_account.vision.email
  description = "Dedicated no-network vision runtime identity."
}
