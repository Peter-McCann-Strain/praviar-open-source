variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "name" {
  description = "VPC name (e.g. praviar-vpc)."
  type        = string
}

variable "region" {
  description = "Primary GCP region (e.g. us-central1)."
  type        = string
}

variable "primary_subnet_cidr" {
  description = "CIDR for the primary subnet (internal services, not Cloud Run)."
  type        = string
  default     = "10.10.0.0/20"
}

variable "cloud_run_subnet_cidr" {
  description = "CIDR for the Cloud Run Direct VPC Egress subnet. /24 = 256 IPs, enough for max_instances across all services."
  type        = string
  default     = "10.10.16.0/24"
}
