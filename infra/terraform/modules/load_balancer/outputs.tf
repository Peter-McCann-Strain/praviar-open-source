output "lb_ip_address" {
  description = "Global anycast IPv4 address of the HTTPS load balancer. Create an A record for var.domain pointing here."
  value       = google_compute_global_address.lb.address
}

output "lb_ip_name" {
  description = "Resource name of the reserved global address (useful for DNS module references)."
  value       = google_compute_global_address.lb.name
}

output "lb_https_url" {
  description = "Public HTTPS URL derived from the configured domain."
  value       = "https://${var.domain}"
}

output "ssl_certificate_name" {
  description = "Name of the Google-managed SSL certificate resource."
  value       = google_compute_managed_ssl_certificate.lb.name
}

output "backend_service_name" {
  description = "Name of the backend service resource (useful for alerting policy targets)."
  value       = google_compute_backend_service.api.name
}

output "security_policy_name" {
  description = "Name of the Cloud Armor security policy attached to the backend service."
  value       = google_compute_security_policy.waf.name
}

output "security_policy_id" {
  description = "Self-link of the Cloud Armor security policy."
  value       = google_compute_security_policy.waf.self_link
}

output "neg_id" {
  description = "ID of the Serverless NEG."
  value       = google_compute_region_network_endpoint_group.cloudrun.id
}
