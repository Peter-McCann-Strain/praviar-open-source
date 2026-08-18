variable "project_id" {
  type = string
}

variable "api_sa_id" {
  type    = string
  default = "praviar-api"
}

variable "workers_sa_id" {
  type    = string
  default = "praviar-workers"
}

variable "tasks_invoker_sa_id" {
  type    = string
  default = "praviar-tasks-invoker"
}

variable "db_bootstrap_sa_id" {
  type    = string
  default = "praviar-db-bootstrap"
}

variable "db_migration_sa_id" {
  type    = string
  default = "praviar-db-migration"
}

variable "report_exports_bucket" {
  description = "GCS bucket name for governed report exports. Used to scope GCS IAM bindings for api and workers SAs."
  type        = string
}
