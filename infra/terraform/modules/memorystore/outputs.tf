output "host" {
  value = google_redis_instance.cache.host
}

output "port" {
  value = google_redis_instance.cache.port
}

output "auth_string" {
  description = "Auth string for AUTH command (use as REDIS_PASSWORD)."
  value       = google_redis_instance.cache.auth_string
  sensitive   = true
}

output "redis_url" {
  description = "redis://:<auth>@<host>:<port>/0 — store in Secret Manager."
  value       = "redis://:${google_redis_instance.cache.auth_string}@${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
  sensitive   = true
}
