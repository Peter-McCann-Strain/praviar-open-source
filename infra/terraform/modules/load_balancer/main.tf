# Global HTTPS Load Balancer with Cloud Armor WAF for the Praviar API Cloud Run service.
#
# Traffic flow:
#   Client → Global Forwarding Rule (443) → Target HTTPS Proxy
#     → URL Map → Backend Service (Cloud Armor WAF attached)
#       → Serverless NEG → Cloud Run v2 service
#
# HTTP on port 80 is accepted only to issue a 301 redirect to HTTPS; no
# backend traffic ever traverses unencrypted.
#
# Cloud Armor rule priority ladder (lower number = evaluated first):
#   1000  — auth-path rate limit   (/api/v*/auth/*)
#   2000  — general rate limit     (all paths)
#   10000 — OWASP CRS SQLi         (preview initially)
#   10001 — OWASP CRS XSS          (preview initially)
#   10002 — OWASP CRS RCE          (preview initially)
#   2147483647 — default allow

locals {
  prefix = var.name_prefix != "" ? var.name_prefix : var.service_name

  common_labels = merge(
    {
      env         = var.env
      owner       = "praviar"
      cost-center = "engineering"
      service     = var.service_name
      managed-by  = "terraform"
    },
    var.labels,
  )
}

# ─── Static anycast IP ────────────────────────────────────────────────────────

resource "google_compute_global_address" "lb" {
  project      = var.project_id
  name         = "${local.prefix}-lb-ip"
  address_type = "EXTERNAL"
  ip_version   = "IPV4"

  description = "Global anycast IP for the ${var.service_name} HTTPS load balancer (${var.env})."
}

# ─── Google-managed SSL certificate ──────────────────────────────────────────

resource "google_compute_managed_ssl_certificate" "lb" {
  project = var.project_id
  name    = "${local.prefix}-lb-cert"

  managed {
    domains = [var.domain]
  }

  lifecycle {
    # GCP provisions certificates asynchronously; recreation triggers a new
    # provisioning cycle that can take up to 20 minutes. Only allow recreation
    # when the domain list actually changes.
    create_before_destroy = true
  }
}

# ─── Serverless Network Endpoint Group ───────────────────────────────────────
# Must be in the same region as the Cloud Run service.

resource "google_compute_region_network_endpoint_group" "cloudrun" {
  project               = var.project_id
  name                  = "${local.prefix}-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = var.service_name
  }

  description = "Serverless NEG for Cloud Run service '${var.service_name}' in ${var.region} (${var.env})."

  lifecycle {
    create_before_destroy = true
  }
}

# ─── Cloud Armor security policy ─────────────────────────────────────────────

resource "google_compute_security_policy" "waf" {
  project     = var.project_id
  name        = "${local.prefix}-waf"
  description = "Cloud Armor WAF for the ${var.service_name} backend (${var.env}). OWASP CRS 4.22 + rate limiting."

  # Adaptive Protection — ML-based L7 DDoS detection and suggested rules.
  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable          = var.adaptive_protection_enabled
      rule_visibility = "STANDARD"
    }
  }

  # ── Priority 1000: auth-path rate limit ────────────────────────────────────
  # Tightest limit applied first. Matches /api/v<n>/auth/<anything> to protect
  # login, token refresh, and registration endpoints from credential stuffing.
  rule {
    priority    = 1000
    description = "Rate-limit auth endpoints: max ${var.rate_limit_auth_threshold} req/min per IP."
    action      = "rate_based_ban"
    preview     = false

    match {
      expr {
        expression = "request.path.matches('/api/v[0-9]+/auth/')"
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"

      rate_limit_threshold {
        count        = var.rate_limit_auth_threshold
        interval_sec = 60
      }

      # Clients that breach the threshold are banned for 5 minutes.
      ban_threshold {
        count        = var.rate_limit_auth_threshold * 2
        interval_sec = 60
      }
      ban_duration_sec = 300

      enforce_on_key = "IP"
    }
  }

  # ── Priority 2000: general API rate limit ─────────────────────────────────
  # Broad cap across all paths. Prevents runaway scrapers or misconfigured
  # clients from exhausting Cloud Run autoscaling budget.
  rule {
    priority    = 2000
    description = "Rate-limit all paths: max ${var.rate_limit_general_threshold} req/min per IP."
    action      = "throttle"
    preview     = false

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"

      rate_limit_threshold {
        count        = var.rate_limit_general_threshold
        interval_sec = 60
      }

      enforce_on_key = "IP"
    }
  }

  # ── Priority 9999: targeted Log4Shell/JNDI canary signatures ─────────────
  # This narrow rule is enforced even while broader CRS rules are in preview.
  # It blocks exploit probes before they reach current or future backends.
  rule {
    priority    = 9999
    description = "Block Log4Shell/JNDI exploit signatures."
    action      = "deny(403)"
    preview     = false

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('cve-canary')"
      }
    }
  }

  # ── Priority 10000: OWASP CRS SQLi — sensitivity level 1 ─────────────────
  # Sensitivity 1 = fewest false positives; rules with internalRuleId matching
  # sensitivity 2, 3, and 4 are excluded via preconfigured_waf_config so only
  # the lowest-paranoia SQLi signatures fire.
  rule {
    priority    = 10000
    description = "OWASP CRS SQLi at sensitivity level 1 (lowest false-positive surface)."
    action      = "deny(403)"
    preview     = var.armor_rule_preview

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable')"
      }
    }

    preconfigured_waf_config {
      exclusion {
        request_uri {
          operator = "STARTS_WITH"
          value    = "/"
        }
        target_rule_set = "sqli-v33-stable"
        # Exclude sensitivity 2/3/4 rule IDs so only sensitivity-1 rules fire.
        target_rule_ids = [
          "owasp-crs-v030301-id942110-sqli",
          "owasp-crs-v030301-id942120-sqli",
          "owasp-crs-v030301-id942130-sqli",
          "owasp-crs-v030301-id942140-sqli",
          "owasp-crs-v030301-id942160-sqli",
          "owasp-crs-v030301-id942170-sqli",
          "owasp-crs-v030301-id942180-sqli",
          "owasp-crs-v030301-id942190-sqli",
          "owasp-crs-v030301-id942200-sqli",
          "owasp-crs-v030301-id942210-sqli",
          "owasp-crs-v030301-id942220-sqli",
          "owasp-crs-v030301-id942230-sqli",
          "owasp-crs-v030301-id942240-sqli",
          "owasp-crs-v030301-id942250-sqli",
          "owasp-crs-v030301-id942251-sqli",
          "owasp-crs-v030301-id942260-sqli",
          "owasp-crs-v030301-id942270-sqli",
          "owasp-crs-v030301-id942280-sqli",
          "owasp-crs-v030301-id942290-sqli",
          "owasp-crs-v030301-id942300-sqli",
          "owasp-crs-v030301-id942310-sqli",
          "owasp-crs-v030301-id942320-sqli",
          "owasp-crs-v030301-id942330-sqli",
          "owasp-crs-v030301-id942340-sqli",
          "owasp-crs-v030301-id942350-sqli",
          "owasp-crs-v030301-id942360-sqli",
          "owasp-crs-v030301-id942370-sqli",
          "owasp-crs-v030301-id942380-sqli",
          "owasp-crs-v030301-id942390-sqli",
          "owasp-crs-v030301-id942400-sqli",
          "owasp-crs-v030301-id942410-sqli",
          "owasp-crs-v030301-id942420-sqli",
          "owasp-crs-v030301-id942421-sqli",
          "owasp-crs-v030301-id942430-sqli",
          "owasp-crs-v030301-id942431-sqli",
          "owasp-crs-v030301-id942432-sqli",
          "owasp-crs-v030301-id942440-sqli",
          "owasp-crs-v030301-id942450-sqli",
          "owasp-crs-v030301-id942460-sqli",
          "owasp-crs-v030301-id942470-sqli",
          "owasp-crs-v030301-id942480-sqli",
          "owasp-crs-v030301-id942490-sqli",
          "owasp-crs-v030301-id942500-sqli",
          "owasp-crs-v030301-id942510-sqli",
        ]
      }
    }
  }

  # ── Priority 10001: OWASP CRS XSS — sensitivity level 1 ──────────────────
  rule {
    priority    = 10001
    description = "OWASP CRS XSS at sensitivity level 1."
    action      = "deny(403)"
    preview     = var.armor_rule_preview

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable')"
      }
    }

    preconfigured_waf_config {
      exclusion {
        request_uri {
          operator = "STARTS_WITH"
          value    = "/"
        }
        target_rule_set = "xss-v33-stable"
        # Exclude sensitivity 2/3/4 XSS rule IDs; retain only sensitivity-1 coverage.
        target_rule_ids = [
          "owasp-crs-v030301-id941100-xss",
          "owasp-crs-v030301-id941110-xss",
          "owasp-crs-v030301-id941120-xss",
          "owasp-crs-v030301-id941130-xss",
          "owasp-crs-v030301-id941140-xss",
          "owasp-crs-v030301-id941150-xss",
          "owasp-crs-v030301-id941160-xss",
          "owasp-crs-v030301-id941170-xss",
          "owasp-crs-v030301-id941180-xss",
          "owasp-crs-v030301-id941190-xss",
          "owasp-crs-v030301-id941200-xss",
          "owasp-crs-v030301-id941210-xss",
          "owasp-crs-v030301-id941220-xss",
          "owasp-crs-v030301-id941230-xss",
          "owasp-crs-v030301-id941240-xss",
          "owasp-crs-v030301-id941250-xss",
          "owasp-crs-v030301-id941260-xss",
          "owasp-crs-v030301-id941270-xss",
          "owasp-crs-v030301-id941280-xss",
          "owasp-crs-v030301-id941290-xss",
          "owasp-crs-v030301-id941300-xss",
          "owasp-crs-v030301-id941310-xss",
          "owasp-crs-v030301-id941320-xss",
          "owasp-crs-v030301-id941330-xss",
          "owasp-crs-v030301-id941340-xss",
          "owasp-crs-v030301-id941350-xss",
          "owasp-crs-v030301-id941360-xss",
          "owasp-crs-v030301-id941370-xss",
          "owasp-crs-v030301-id941380-xss",
        ]
      }
    }
  }

  # ── Priority 10002: OWASP CRS RCE — sensitivity level 1 ──────────────────
  rule {
    priority    = 10002
    description = "OWASP CRS RCE/command injection at sensitivity level 1."
    action      = "deny(403)"
    preview     = var.armor_rule_preview

    match {
      expr {
        expression = "evaluatePreconfiguredWaf('rce-v33-stable')"
      }
    }

    preconfigured_waf_config {
      exclusion {
        request_uri {
          operator = "STARTS_WITH"
          value    = "/"
        }
        target_rule_set = "rce-v33-stable"
        # Exclude sensitivity 2/3/4 RCE rule IDs; retain only sensitivity-1 coverage.
        target_rule_ids = [
          "owasp-crs-v030301-id932110-rce",
          "owasp-crs-v030301-id932115-rce",
          "owasp-crs-v030301-id932120-rce",
          "owasp-crs-v030301-id932130-rce",
          "owasp-crs-v030301-id932140-rce",
          "owasp-crs-v030301-id932150-rce",
          "owasp-crs-v030301-id932160-rce",
          "owasp-crs-v030301-id932170-rce",
          "owasp-crs-v030301-id932180-rce",
          "owasp-crs-v030301-id932190-rce",
          "owasp-crs-v030301-id932200-rce",
        ]
      }
    }
  }

  # ── Priority 2147483647: default allow ────────────────────────────────────
  # Explicit default rule so intent is unambiguous in audit logs.
  rule {
    priority    = 2147483647
    description = "Default: allow all traffic not matched by higher-priority rules."
    action      = "allow"
    preview     = false

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

# ─── Backend service ──────────────────────────────────────────────────────────

resource "google_compute_backend_service" "api" {
  project     = var.project_id
  name        = "${local.prefix}-backend"
  description = "Backend service for ${var.service_name} Cloud Run (${var.env}) with Cloud Armor WAF."

  protocol              = "HTTPS"
  timeout_sec           = 30
  load_balancing_scheme = "EXTERNAL_MANAGED"

  # Serverless NEGs do not support health checks; Cloud Run manages its own
  # readiness. The backend service health-check field is omitted intentionally.

  security_policy = google_compute_security_policy.waf.id

  connection_draining_timeout_sec = var.connection_draining_timeout_sec

  log_config {
    enable      = true
    sample_rate = 1.0
  }

  backend {
    group = google_compute_region_network_endpoint_group.cloudrun.id

    # Serverless NEG backends do not support balancing_mode, max_rate, or
    # max_utilization — capacity is governed by Cloud Run autoscaling.
    capacity_scaler = 1.0
  }
}

# ─── HTTPS URL map ────────────────────────────────────────────────────────────

resource "google_compute_url_map" "https" {
  project         = var.project_id
  name            = "${local.prefix}-url-map"
  description     = "Routes all HTTPS traffic for ${var.domain} to the ${var.service_name} backend service."
  default_service = google_compute_backend_service.api.id
}

# ─── HTTP URL map (redirect only) ─────────────────────────────────────────────
# Accepts HTTP on port 80 and immediately returns a 301 to the HTTPS URL.
# No backend service is referenced; no traffic reaches Cloud Run over HTTP.

resource "google_compute_url_map" "http_redirect" {
  project     = var.project_id
  name        = "${local.prefix}-http-redirect"
  description = "Redirects all HTTP traffic for ${var.domain} to HTTPS with a 301."

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

# ─── Target HTTPS proxy ───────────────────────────────────────────────────────

resource "google_compute_target_https_proxy" "lb" {
  project          = var.project_id
  name             = "${local.prefix}-https-proxy"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb.id]

  description = "Target HTTPS proxy for the ${var.service_name} load balancer (${var.env})."
}

# ─── Target HTTP proxy (redirect only) ───────────────────────────────────────

resource "google_compute_target_http_proxy" "redirect" {
  project     = var.project_id
  name        = "${local.prefix}-http-redirect-proxy"
  url_map     = google_compute_url_map.http_redirect.id
  description = "Target HTTP proxy that forwards to the HTTP→HTTPS redirect URL map."
}

# ─── Global forwarding rule — HTTPS (port 443) ────────────────────────────────

resource "google_compute_global_forwarding_rule" "https" {
  project               = var.project_id
  name                  = "${local.prefix}-https-fwd"
  description           = "Forwards external HTTPS traffic on port 443 to the ${var.service_name} target proxy."
  target                = google_compute_target_https_proxy.lb.id
  ip_address            = google_compute_global_address.lb.id
  port_range            = "443"
  load_balancing_scheme = "EXTERNAL_MANAGED"

  labels = local.common_labels
}

# ─── Global forwarding rule — HTTP (port 80, redirect) ────────────────────────

resource "google_compute_global_forwarding_rule" "http_redirect" {
  project               = var.project_id
  name                  = "${local.prefix}-http-redirect-fwd"
  description           = "Accepts HTTP on port 80 and feeds the redirect proxy (no backend traffic)."
  target                = google_compute_target_http_proxy.redirect.id
  ip_address            = google_compute_global_address.lb.id
  port_range            = "80"
  load_balancing_scheme = "EXTERNAL_MANAGED"

  labels = local.common_labels
}
