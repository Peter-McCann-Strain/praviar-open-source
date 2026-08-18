variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "env" {
  description = "Deployment environment label (e.g. prod, staging)."
  type        = string
}

variable "region" {
  description = "GCP region where the Cloud Run service runs (e.g. us-central1). The Serverless NEG must be co-located."
  type        = string
}

variable "service_name" {
  description = "Cloud Run v2 service name to route traffic to (e.g. api)."
  type        = string
}

variable "domain" {
  description = "Deployment-operator-controlled fully-qualified domain name for the Google-managed SSL certificate (for example, api.example.invalid in a non-deployed template)."
  type        = string
}

variable "name_prefix" {
  description = "Short identifier prepended to all resource names. Defaults to service_name when empty."
  type        = string
  default     = ""
}

variable "armor_rule_preview" {
  description = "When true, Cloud Armor OWASP CRS rules are set to preview mode (log only, no block). Set to false once the policy is validated in production."
  type        = bool
  default     = true
}

variable "rate_limit_general_threshold" {
  description = "Maximum requests per minute per IP for general API traffic before Cloud Armor enforces a 429."
  type        = number
  default     = 1000
}

variable "rate_limit_auth_threshold" {
  description = "Maximum requests per minute per IP for paths matching /api/v*/auth/* before Cloud Armor enforces a 429."
  type        = number
  default     = 10
}

variable "connection_draining_timeout_sec" {
  description = "Seconds the backend service waits for in-flight requests to complete during instance removal."
  type        = number
  default     = 30
}

variable "adaptive_protection_enabled" {
  description = "Enable Cloud Armor Adaptive Protection (ML-based L7 DDoS detection)."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Additional labels merged onto the forwarding rules."
  type        = map(string)
  default     = {}
}
