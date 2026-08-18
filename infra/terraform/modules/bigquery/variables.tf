variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "env" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
}

variable "region" {
  description = "BigQuery dataset location (GCP region, e.g. US or us-central1)."
  type        = string
  default     = "US"
}

variable "dataset_id" {
  description = "BigQuery dataset ID for the patent search table."
  type        = string
  default     = "patents"
}

variable "table_id" {
  description = "BigQuery table ID within the dataset."
  type        = string
  default     = "patents"
}

variable "reader_service_accounts" {
  description = "Service account emails that need READER access to query the patent table."
  type        = list(string)
  default     = []
}
