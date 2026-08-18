output "instance_name" {
  value = google_sql_database_instance.primary.name
}

output "connection_name" {
  description = "Cloud SQL connection name used in DSN: postgresql+asyncpg://user:pass@/db?host=/cloudsql/<connection_name>"
  value       = google_sql_database_instance.primary.connection_name
}

output "private_ip" {
  value = google_sql_database_instance.primary.private_ip_address
}

output "database_name" {
  value = google_sql_database.praviar.name
}

output "bootstrap_user" {
  value = google_sql_user.bootstrap.name
}

output "app_user" {
  value = google_sql_user.api.name
}

output "worker_user" {
  value = google_sql_user.worker.name
}

output "epo_checkpoint_writer_user" {
  value = google_sql_user.epo_checkpoint_writer.name
}

output "migration_user" {
  value = google_sql_user.migrator.name
}

output "claimed_use_writer_user" {
  value = google_sql_user.claimed_use_writer.name
}

output "global_erasure_user" {
  value = google_sql_user.global_erasure.name
}
