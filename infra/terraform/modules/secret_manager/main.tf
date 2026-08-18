# Secret Manager — store all sensitive config.
# Cloud Run pulls secrets at startup via --set-secrets flag (no application code change needed).
#
# Secrets created by this module are EMPTY shells — Terraform creates the resource and the
# IAM bindings; secret VERSIONS (actual values) are populated out-of-band by the founder
# via `gcloud secrets versions add <name> --data-file=-` to keep values out of state.

resource "google_secret_manager_secret" "secrets" {
  for_each = toset(var.secret_names)

  project   = var.project_id
  secret_id = each.key

  replication {
    auto {}
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
  }
}

locals {
  secret_accessor_pairs = flatten([
    for secret, accounts in var.secret_accessor_service_accounts : [
      for sa in accounts : {
        key    = "${secret}|${sa}"
        secret = secret
        sa     = sa
      }
    ]
  ])
  secret_accessors = {
    for pair in local.secret_accessor_pairs : pair.key => pair
  }
}

# Grant only the accessor list explicitly classified for each secret.
resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = local.secret_accessors

  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.value.secret].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.sa}"
}
