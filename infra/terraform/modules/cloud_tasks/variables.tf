variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "queue_name" {
  type    = string
  default = "pipeline-default"
}

variable "max_concurrent_dispatches" {
  description = "Soft cap on parallel pipeline jobs."
  type        = number
  default     = 10
}

variable "max_dispatches_per_second" {
  type    = number
  default = 5
}

variable "enqueuer_service_account_emails" {
  description = "Runtime service accounts allowed to create tasks on this queue"
  type        = list(string)
  default     = []
}
