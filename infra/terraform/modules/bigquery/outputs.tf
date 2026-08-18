output "dataset_id" {
  description = "BigQuery dataset ID."
  value       = google_bigquery_dataset.patents.dataset_id
}

output "table_id" {
  description = "BigQuery table ID."
  value       = google_bigquery_table.patents.table_id
}

output "table_fqn" {
  description = "Fully-qualified table name in project.dataset.table form."
  value       = "${var.project_id}.${google_bigquery_dataset.patents.dataset_id}.${google_bigquery_table.patents.table_id}"
}
