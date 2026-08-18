variable "project_id" {
  type = string
}

variable "env" {
  type = string
}

variable "secret_names" {
  description = "Secret IDs to create (no values — populated out-of-band)."
  type        = list(string)
  default = [
    # Database
    "bootstrap-database-url",
    "api-database-url",
    "claimed-use-writer-database-url",
    "global-erasure-database-url",
    "worker-database-url",
    "migration-database-url",
    "epo-checkpoint-database-url",
    "api-key-hmac-secret",
    "pipeline-checkpoint-hmac-secret",
    "claimed-use-attestation-hmac-secret",
    "epo-acquisition-kms-keyring",
    "epo-checkpoint-kms-keyring",
    "report-certification-signing-keyring",
    "report-certification-public-keyring",
    "certification-release-receipt",
    "certification-release-public-key",
    # Cache
    "redis-url",
    "chat-budget-redis-url",
    # Clerk
    "clerk-secret-key",
    "clerk-webhook-secret",
    "clerk-publishable-key",
    "clerk-domain",
    "clerk-jwks-url",
    # Stripe
    "stripe-secret-key",
    "stripe-webhook-secret",
    # LLM
    "anthropic-api-key",
    # Observability
    "sentry-dsn",
    "honeycomb-api-key",
    # Email delivery
    "postmark-api-token",
    "external-report-delivery-keyring",
  ]
}

variable "secret_accessor_service_accounts" {
  description = "Exhaustive per-secret accessor classification. Keys must exactly equal secret_names; there is no shared-access fallback."
  type        = map(list(string))

  validation {
    condition = (
      length(var.secret_names) == length(toset(var.secret_names)) &&
      length(setsubtract(toset(var.secret_names), toset(keys(var.secret_accessor_service_accounts)))) == 0 &&
      length(setsubtract(toset(keys(var.secret_accessor_service_accounts)), toset(var.secret_names))) == 0 &&
      alltrue([
        for accounts in values(var.secret_accessor_service_accounts) :
        length(accounts) > 0 && length(accounts) == length(toset(accounts))
      ])
    )
    error_message = "secret_accessor_service_accounts must classify every secret_name exactly once with a nonempty, duplicate-free accessor list and may not contain unknown secrets."
  }
}
