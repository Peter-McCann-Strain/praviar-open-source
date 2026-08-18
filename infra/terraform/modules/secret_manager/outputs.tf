output "secret_ids" {
  description = "Map of secret name → Secret Manager resource ID (for Cloud Run --set-secrets)."
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.id }
}
