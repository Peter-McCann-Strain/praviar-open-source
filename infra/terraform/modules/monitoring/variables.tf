variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "env" {
  description = "Deployment environment (e.g. dev, staging, prod)."
  type        = string
}

variable "api_service_name" {
  description = "Cloud Run service name for the API (e.g. praviar-api)."
  type        = string
}

variable "workers_service_name" {
  description = "Cloud Run service name for the workers (e.g. praviar-workers)."
  type        = string
}

variable "notification_channel_ids" {
  description = "List of Cloud Monitoring notification channel resource names (e.g. email, PagerDuty). Passed to all alert policies."
  type        = list(string)
  default     = []
}

variable "alert_email" {
  description = "Email address for an auto-created email notification channel. Leave empty to skip."
  type        = string
  default     = ""
}
