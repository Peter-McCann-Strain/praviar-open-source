variable "project_id" {
  type = string
}

variable "env" {
  type = string
}

variable "service_name" {
  description = "Cloud Run service name (e.g. api, workers)."
  type        = string
}

variable "region" {
  type = string
}

variable "image" {
  description = "Immutable digest-qualified container image managed by Terraform."
  type        = string

  validation {
    condition     = can(regex("^[^[:space:]@]+@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be an immutable repository-qualified @sha256:<64 lowercase hex> reference."
  }
}

variable "required_image_digest" {
  description = "Optional certified OCI digest that the deployed image must exactly match."
  type        = string
  default     = ""

  validation {
    condition = (
      var.required_image_digest == "" ||
      can(regex("^sha256:[0-9a-f]{64}$", var.required_image_digest))
    )
    error_message = "required_image_digest must be empty or sha256:<64 lowercase hex>."
  }
}

variable "service_account_email" {
  description = "Runtime SA email (from iam module)."
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

variable "vpc_egress" {
  description = "Cloud Run VPC egress mode. Synchronous callers of internal Cloud Run services must use ALL_TRAFFIC."
  type        = string
  default     = "PRIVATE_RANGES_ONLY"

  validation {
    condition     = contains(["PRIVATE_RANGES_ONLY", "ALL_TRAFFIC"], var.vpc_egress)
    error_message = "vpc_egress must be PRIVATE_RANGES_ONLY or ALL_TRAFFIC."
  }
}

variable "ingress" {
  description = "INGRESS_TRAFFIC_ALL | INGRESS_TRAFFIC_INTERNAL_ONLY | INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 5
}

variable "cpu" {
  type    = string
  default = "2"
}

variable "memory" {
  type    = string
  default = "2Gi"
}

variable "cpu_always_on" {
  description = "Keep CPU allocated when idle (needed for background tasks)."
  type        = bool
  default     = false
}

variable "startup_cpu_boost" {
  type    = bool
  default = true
}

variable "request_timeout" {
  description = "Per-request timeout (Cloud Run max 3600s)."
  type        = string
  default     = "300s"
}

variable "container_port" {
  type    = number
  default = 8080
}

variable "max_instance_request_concurrency" {
  description = "Maximum concurrent requests per container instance. Set to 1 for CPU-bound workers; 80-150 for async API."
  type        = number
  default     = 80
}

variable "health_path" {
  description = "HTTP path for startup + liveness probes."
  type        = string
  default     = "/api/health/ready"
}

variable "env_vars" {
  description = "Static env vars."
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Env vars sourced from Secret Manager. Pin release-sensitive values to an immutable numeric version."
  type = map(object({
    secret_id = string
    version   = optional(string, "latest")
  }))
  default = {}
}

variable "cloudsql_connection_name" {
  description = "Cloud SQL connection name (project:region:instance) to attach. Empty string disables."
  type        = string
  default     = ""
}

variable "allow_public_invocation" {
  description = "Allow allUsers run.invoker. Production API must pair this with load-balancer-only ingress; workers keep it false."
  type        = bool
  default     = false
}

variable "oidc_invoker_sa_emails" {
  description = "Service account emails allowed to invoke via OIDC (e.g. tasks_invoker SA for workers)."
  type        = list(string)
  default     = []
}

variable "binary_authorization_enabled" {
  description = "Enforce the project's default Binary Authorization policy for every new revision. Production must set this true."
  type        = bool
  default     = false
}
