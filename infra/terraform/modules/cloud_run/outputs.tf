output "service_name" {
  value = google_cloud_run_v2_service.service.name
}

output "service_url" {
  description = "Default Cloud Run-issued URL. Use LB-only ingress only after Terraform owns the LB/probe route."
  value       = google_cloud_run_v2_service.service.uri
}

output "service_id" {
  value = google_cloud_run_v2_service.service.id
}
