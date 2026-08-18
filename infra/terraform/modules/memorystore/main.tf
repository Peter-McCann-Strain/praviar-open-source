# Memorystore Redis — cache + rate-limit storage.
# MVP: Basic 1 GiB. Scale: Standard HA 5+ GiB.

resource "google_redis_instance" "cache" {
  project            = var.project_id
  name               = var.name
  tier               = var.tier
  memory_size_gb     = var.memory_size_gb
  region             = var.region
  redis_version      = "REDIS_7_2"
  authorized_network = var.vpc_id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  # DISABLED: traffic stays on the private VPC; auth_enabled=true provides
  # authentication. SERVER_AUTHENTICATION requires rediss:// + CA-cert plumbing
  # through the application client — not yet wired.
  transit_encryption_mode = "DISABLED"
  auth_enabled            = true

  redis_configs = {
    maxmemory-policy = var.maxmemory_policy
  }

  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 6
        minutes = 0
      }
    }
  }

  labels = {
    env         = var.env
    owner       = "praviar"
    cost-center = "engineering"
  }
}
