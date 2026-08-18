variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "env" {
  description = "Environment label (dev|staging|prod)."
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name (e.g. praviar-pg)."
  type        = string
  default     = "praviar-pg"
}

variable "region" {
  description = "GCP region."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for private IP (output of vpc module)."
  type        = string
}

variable "tier" {
  description = "Cloud SQL tier. Staging: db-custom-1-3840. Prod: db-custom-2-7680."
  type        = string
  default     = "db-custom-2-7680"
}

variable "edition" {
  description = "Cloud SQL edition: ENTERPRISE or ENTERPRISE_PLUS."
  type        = string
  default     = "ENTERPRISE"
}

variable "availability_type" {
  description = "REGIONAL (HA) or ZONAL. MVP=ZONAL ($), Pilot+=REGIONAL ($$)."
  type        = string
  default     = "ZONAL"
}

variable "disk_size_gb" {
  description = "Initial disk size in GB."
  type        = number
  default     = 50
}

variable "disk_max_size_gb" {
  description = "Auto-resize ceiling in GB."
  type        = number
  default     = 500
}

variable "database_name" {
  description = "Application database name. PIN to 'praviar' per execution plan §8."
  type        = string
  default     = "praviar"
}

variable "app_user" {
  description = "Least-privilege API database user."
  type        = string
  default     = "praviar_api"
}

variable "app_user_password" {
  description = "Initial password for the API database user. Sourced from Secret Manager — never hard-code."
  type        = string
  sensitive   = true
}

variable "worker_user" {
  description = "Worker database user for queue-owned background jobs."
  type        = string
  default     = "praviar_worker"
}

variable "worker_user_password" {
  description = "Initial password for the worker database user."
  type        = string
  sensitive   = true
}

variable "epo_checkpoint_writer_user" {
  description = "Dedicated global EPO atomic-checkpoint writer login."
  type        = string
  default     = "praviar_epo_checkpoint_writer"
}

variable "epo_checkpoint_writer_user_password" {
  description = "Initial password for the EPO atomic-checkpoint writer login."
  type        = string
  sensitive   = true
}

variable "migration_user" {
  description = "Migration database user that SET ROLEs to alembic_runner."
  type        = string
  default     = "praviar_migrator"
}

variable "migration_user_password" {
  description = "Initial password for the migration database user."
  type        = string
  sensitive   = true
}

variable "claimed_use_writer_user" {
  description = "Dedicated claimed-use receipt procedure login."
  type        = string
  default     = "praviar_claimed_use_writer"
}

variable "claimed_use_writer_user_password" {
  description = "Initial password for the claimed-use writer login."
  type        = string
  sensitive   = true
}

variable "global_erasure_user" {
  description = "Highly privileged global tenant-erasure executor login."
  type        = string
  default     = "praviar_global_erasure"
}

variable "global_erasure_user_password" {
  description = "Initial password for the global tenant-erasure executor."
  type        = string
  sensitive   = true
}

variable "bootstrap_user" {
  description = "Privileged bootstrap user used only by the role/grant bootstrap job."
  type        = string
  default     = "postgres"
}

variable "bootstrap_user_password" {
  description = "Initial password for the bootstrap database user."
  type        = string
  sensitive   = true
}

variable "deletion_protection" {
  description = "Prevent accidental terraform destroy. Always true in prod/staging."
  type        = bool
  default     = true
}
