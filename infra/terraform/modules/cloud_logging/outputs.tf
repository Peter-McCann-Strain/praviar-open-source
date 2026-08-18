output "audit_archive_bucket" {
  value = google_storage_bucket.audit_archive.name
}

output "access_log_bucket" {
  description = "Dedicated non-recursive destination for Cloud Storage server access logs."
  value       = google_storage_bucket.access_logs.name

  depends_on = [google_storage_bucket_iam_member.access_log_writer]
}

output "data_access_sink_writer_identity" {
  value = google_logging_project_sink.data_access.writer_identity
}
