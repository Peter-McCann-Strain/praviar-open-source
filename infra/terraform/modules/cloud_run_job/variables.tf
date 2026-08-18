variable "project_id" {
  type = string
}

variable "env" {
  type = string
}

variable "job_name" {
  description = "Cloud Run Job name, for example api-migrate."
  type        = string
}

variable "region" {
  type = string
}

variable "image" {
  description = "Immutable OCI image reference for the certified API release."
  type        = string

  validation {
    condition     = can(regex("^[^[:space:]@]+@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be one immutable OCI repository@sha256 reference."
  }
}

variable "approved_image_repository" {
  description = "Exact Artifact Registry repository authorized for this job image, without a tag or digest."
  type        = string

  validation {
    condition = can(regex(
      "^[a-z0-9.-]+(/[a-z0-9._-]+)+$",
      var.approved_image_repository,
    ))
    error_message = "approved_image_repository must be an OCI repository without a tag or digest."
  }
}

variable "required_image_digest" {
  description = "Exact API image sha256 digest approved by the release certification."
  type        = string

  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.required_image_digest))
    error_message = "required_image_digest must be a lowercase OCI sha256 digest."
  }
}

variable "service_account_email" {
  description = "Runtime service account email."
  type        = string
}

variable "network_id" {
  description = "VPC network ID for Direct VPC Egress."
  type        = string
}

variable "subnetwork_id" {
  description = "Subnetwork ID for Direct VPC Egress (the cloud_run_subnet from the vpc module)."
  type        = string
}

variable "command" {
  description = "Container command for the job."
  type        = list(string)
}

variable "args" {
  description = "Container args for the job."
  type        = list(string)
  default     = []
}

variable "task_count" {
  type    = number
  default = 1
}

variable "parallelism" {
  type    = number
  default = 1
}

variable "max_retries" {
  type    = number
  default = 0
}

variable "task_timeout" {
  description = "Task timeout, for example 600s."
  type        = string
  default     = "600s"
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "1Gi"
}

variable "env_vars" {
  description = "Static env vars."
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Env vars sourced from Secret Manager. Release trust roots should pin an immutable numeric version."
  type = map(object({
    secret_id = string
    version   = optional(string, "latest")
  }))
  default = {}
}

variable "cloudsql_connection_name" {
  description = "Cloud SQL connection name to attach. Empty string disables."
  type        = string
  default     = ""
}

variable "binary_authorization_enabled" {
  description = "Enforce the project's default Binary Authorization policy when this job executes. Production must set this true."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Protect long-lived production jobs from accidental deletion."
  type        = bool
  default     = false
}
