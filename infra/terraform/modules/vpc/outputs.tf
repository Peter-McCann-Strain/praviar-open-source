output "vpc_id" {
  value = google_compute_network.vpc.id
}

output "vpc_name" {
  value = google_compute_network.vpc.name
}

output "primary_subnet_id" {
  value = google_compute_subnetwork.primary.id
}

output "cloud_run_subnet_id" {
  description = "Subnetwork ID for Cloud Run Direct VPC Egress."
  value       = google_compute_subnetwork.cloud_run.id
}
