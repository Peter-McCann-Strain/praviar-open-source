variable "project_id" {
  type = string
}

variable "env" {
  type = string

  validation {
    condition     = contains(["staging", "prod"], var.env)
    error_message = "The production vision job may only be instantiated in staging or prod."
  }
}

variable "job_name" {
  type        = string
  description = "Private Cloud Run Job name."
}

variable "region" {
  type = string
}

variable "image" {
  type        = string
  description = "Digest-qualified dedicated vision image."

  validation {
    condition     = can(regex("^[^[:space:]@]+@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be an immutable repository@sha256 reference."
  }
}

variable "approved_image_repository" {
  type        = string
  description = "Exact approved Artifact Registry vision-worker repository."

  validation {
    condition     = can(regex("^[a-z0-9.-]+(/[a-z0-9._-]+)+$", var.approved_image_repository))
    error_message = "approved_image_repository must not contain a tag or digest."
  }
}

variable "required_image_digest" {
  type        = string
  description = "Release-approved dedicated vision OCI digest."

  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.required_image_digest))
    error_message = "required_image_digest must be a lowercase OCI sha256 digest."
  }
}

variable "roster_sha256" {
  type        = string
  description = "SHA-256 of the exact production vision roster embedded in the image."

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.roster_sha256))
    error_message = "roster_sha256 must be a lowercase SHA-256 digest without a prefix."
  }
}

variable "ml_bom_sha256" {
  type        = string
  description = "SHA-256 of the release-approved ML-BOM embedded in the image."

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.ml_bom_sha256))
    error_message = "ml_bom_sha256 must be a lowercase SHA-256 digest without a prefix."
  }
}

variable "deployer_service_account_email" {
  type        = string
  description = "Deployment service account granted actAs on the dedicated private runtime identity."

  validation {
    condition = can(regex(
      "^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\\.iam\\.gserviceaccount\\.com$",
      var.deployer_service_account_email,
    ))
    error_message = "deployer_service_account_email must be a canonical GCP service-account email."
  }
}

variable "network_id" {
  type = string
}

variable "subnetwork_id" {
  type = string
}

variable "task_timeout" {
  type    = string
  default = "3600s"
}

variable "cpu" {
  type    = string
  default = "4"
}

variable "memory" {
  type    = string
  default = "16Gi"
}

variable "deletion_protection" {
  type        = bool
  description = "Protect the production preflight job from accidental deletion."
  default     = true
}
