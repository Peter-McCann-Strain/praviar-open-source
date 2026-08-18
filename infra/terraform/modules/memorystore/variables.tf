variable "project_id" {
  type = string
}

variable "env" {
  type = string
}

variable "name" {
  type    = string
  default = "praviar-cache"
}

variable "region" {
  type = string
}

variable "vpc_id" {
  description = "VPC ID for private services access."
  type        = string
}

variable "tier" {
  description = "BASIC (single node) or STANDARD_HA (replicated)."
  type        = string
  default     = "BASIC"
}

variable "memory_size_gb" {
  type    = number
  default = 1
}

variable "maxmemory_policy" {
  description = "Redis memory-pressure policy; monetary ledgers must use noeviction."
  type        = string
  default     = "allkeys-lru"

  validation {
    condition = contains(
      ["allkeys-lru", "allkeys-lfu", "volatile-lru", "volatile-lfu", "noeviction"],
      var.maxmemory_policy,
    )
    error_message = "maxmemory_policy must be an explicitly supported Redis policy."
  }
}
