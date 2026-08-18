output "api_sa_email" {
  value = google_service_account.api.email
}

output "workers_sa_email" {
  value = google_service_account.workers.email
}

output "db_bootstrap_sa_email" {
  value = google_service_account.db_bootstrap.email
}

output "db_migration_sa_email" {
  value = google_service_account.db_migration.email
}

output "tasks_invoker_sa_email" {
  value = google_service_account.tasks_invoker.email
}

output "all_runtime_sa_emails" {
  description = "All runtime SA emails — useful for Secret Manager accessor bindings."
  value = [
    google_service_account.api.email,
    google_service_account.workers.email,
  ]
}
