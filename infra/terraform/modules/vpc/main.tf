# VPC module — private network for Cloud SQL + Memorystore + Cloud Run Direct VPC Egress.

resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = var.name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

# Materialize GCP's implied deny-ingress posture as an auditable rule with
# firewall logging. Future VM-based services must add a narrower, higher-
# priority allow rule rather than inheriting an accidental broad ingress path.
resource "google_compute_firewall" "deny_all_ingress" {
  project   = var.project_id
  name      = "${var.name}-deny-all-ingress"
  network   = google_compute_network.vpc.name
  direction = "INGRESS"
  priority  = 65534

  source_ranges = ["0.0.0.0/0"]

  deny {
    protocol = "all"
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_subnetwork" "primary" {
  project                  = var.project_id
  name                     = "${var.name}-${var.region}-primary"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.primary_subnet_cidr
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Dedicated subnet for Cloud Run Direct VPC Egress.
# Each Cloud Run instance consumes one IP; /24 gives 256 addresses across
# both API (max 5) and workers (max 10) with plenty of headroom.
resource "google_compute_subnetwork" "cloud_run" {
  project                  = var.project_id
  name                     = "${var.name}-${var.region}-cloud-run"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.cloud_run_subnet_cidr
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Public API revisions route all egress through this VPC so synchronous calls
# to internal-only Cloud Run services are recognized as internal. Cloud NAT
# preserves access to counsel, billing, and email providers without assigning
# public addresses to serverless instances.
resource "google_compute_router" "cloud_run_egress" {
  project = var.project_id
  name    = "${var.name}-${var.region}-cloud-run-egress"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "cloud_run_egress" {
  project                            = var.project_id
  name                               = "${var.name}-${var.region}-cloud-run-egress"
  router                             = google_compute_router.cloud_run_egress.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# Reserved IP range for Cloud SQL + Memorystore private services access.
resource "google_compute_global_address" "private_services" {
  project       = var.project_id
  name          = "${var.name}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  # Explicit address prevents GCP from auto-selecting a /16 that overlaps
  # with the primary subnet (10.10.0.0/20) or Cloud Run subnet (10.10.16.0/24).
  address = "10.20.0.0"
  network = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}
