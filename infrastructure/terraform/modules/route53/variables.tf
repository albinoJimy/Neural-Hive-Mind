# =============================================================================
# Neural Hive-Mind - Route53 Variables
# =============================================================================

variable "domain_name" {
  description = "Domínio principal para Route53"
  type        = string
}

variable "vpc_id" {
  description = "ID da VPC para private hosted zone"
  type        = string
  default     = null
}

variable "create_private_zone" {
  description = "Criar private hosted zone"
  type        = bool
  default     = false
}

variable "create_public_zone" {
  description = "Criar public hosted zone"
  type        = bool
  default     = true
}

variable "records" {
  description = "Mapa de registros DNS"
  type = map(object({
    type    = string
    ttl     = optional(number)
    records = optional(list(string))
    alias = optional(object({
      name                   = string
      zone_id                = string
      evaluate_target_health = optional(bool, true)
    }))
    health_check      = optional(bool, false)
    multivalue_answer = optional(bool)
    region            = optional(string)
    failover_routing  = optional(map(string))
    latency_routing   = optional(map(string))
    secondary_alias = optional(object({
      name                   = string
      zone_id                = string
      evaluate_target_health = optional(bool, true)
    }))
  }))
  default = {}
}

variable "health_checks" {
  description = "Mapa de health checks"
  type = map(object({
    fqdn              = string
    port              = number
    type              = string
    resource_path     = optional(string, "/")
    request_interval  = optional(number, 30)
    failure_threshold = optional(number, 3)
  }))
  default = {}
}

variable "tags" {
  description = "Tags adicionais"
  type        = map(string)
  default     = {}
}
