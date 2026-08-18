output "repository_url" {
  description = "Full repository URL prefix for docker push (e.g. us-central1-docker.pkg.dev/praviar-prod/praviar)."
  value       = "${google_artifact_registry_repository.containers.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}

output "repository_id" {
  value = google_artifact_registry_repository.containers.repository_id
}
