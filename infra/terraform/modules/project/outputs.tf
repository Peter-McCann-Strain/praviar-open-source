output "enabled_apis" {
  description = "Set of GCP service APIs enabled on the project."
  value       = [for s in google_project_service.enabled : s.service]
}
