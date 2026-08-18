variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "env" {
  description = "Deployment environment (e.g. dev, staging, prod)."
  type        = string
}

variable "region" {
  description = "GCP region for regional resources."
  type        = string
}

variable "bq_dataset_id" {
  description = "BigQuery dataset ID for analytics ingest of job events. Must already exist. Kept separate from the patents dataset."
  type        = string
  default     = "analytics"
}

variable "job_webhook_url" {
  description = "HTTPS push endpoint for the job-events webhook subscription. Leave empty to skip creating the push subscription."
  type        = string
  default     = ""
}
