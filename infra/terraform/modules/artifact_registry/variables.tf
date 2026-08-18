variable "project_id" {
  type = string
}

variable "env" {
  type = string
}

variable "region" {
  type = string
}

variable "repository_id" {
  type    = string
  default = "praviar"
}

variable "cloudbuild_service_account" {
  description = "Service account email used by Cloud Build."
  type        = string
}
