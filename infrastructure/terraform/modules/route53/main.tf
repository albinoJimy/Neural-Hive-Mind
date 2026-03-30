# =============================================================================
# Neural Hive-Mind - Route53 Multi-Region Module
# =============================================================================
# Gerencia DNS global com health checks e failover
# =============================================================================

# -----------------------------------------------------------------------------
# Private Hosted Zone para cluster EKS
# -----------------------------------------------------------------------------

resource "aws_route53_zone" "private" {
  count = var.create_private_zone ? 1 : 0

  name = var.domain_name

  vpc {
    vpc_id = var.vpc_id
  }

  comment = "Private hosted zone for Neural Hive-Mind cluster"

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Public Hosted Zone para DNS global
# -----------------------------------------------------------------------------

resource "aws_route53_zone" "public" {
  count = var.create_public_zone ? 1 : 0

  name = var.domain_name

  comment = "Public hosted zone for Neural Hive-Mind global DNS"

  tags = merge(
    var.tags,
    {
      Type = "public-global"
    }
  )
}

# -----------------------------------------------------------------------------
# Health Checks
# -----------------------------------------------------------------------------

resource "aws_route53_health_check" "this" {
  for_each = var.health_checks

  fqdn              = each.value.fqdn
  port              = each.value.port
  type              = each.value.type
  resource_path     = each.value.resource_path
  request_interval  = each.value.request_interval
  failure_threshold = each.value.failure_threshold

  measure_latency = true

  tags = merge(
    var.tags,
    {
      Name = each.key
    }
  )
}

# -----------------------------------------------------------------------------
# DNS Records
# -----------------------------------------------------------------------------

resource "aws_route53_record" "this" {
  for_each = var.records

  zone_id = var.create_public_zone ? aws_route53_zone.public[0].zone_id : aws_route53_zone.private[0].zone_id
  name    = "${each.key}.${var.domain_name}"
  type    = each.value.type

  alias {
    name                   = each.value.alias.name
    zone_id                = each.value.alias.zone_id
    evaluate_target_health = try(each.value.alias.evaluate_target_health, true)
  }

  # Failover routing policy configurado
  failover_routing_policy {
    type = each.value.failover_routing != null ? "PRIMARY" : null
  }

  # Latency routing policy para multi-região
  latency_routing_policy {
    region = each.value.region
  }

  # Geoproximity routing
  geoproximity_routing_policy {
    # Configuração para roteamento baseado em localização
  }

  health_check_id = each.value.health_check ? aws_route53_health_check["${each.key}_health"].id : null

  # Allow multiple records for round-robin
  multivalue_answer_enabled = each.value.multivalue_answer != null ? each.value.multivalue_answer : false

  ttl = each.value.ttl != null ? each.value.ttl : null

  records = each.value.records != null ? each.value.records : null

  depends_on = [
    aws_route53_health_check.this
  ]
}

# -----------------------------------------------------------------------------
# Failover Records (Primary/Secondary)
# -----------------------------------------------------------------------------

resource "aws_route53_record" "failover_primary" {
  for_each = {
    for k, v in var.records : k => v
    if v.failover_routing != null
  }

  zone_id = aws_route53_zone.public[0].zone_id
  name    = "${each.key}.${var.domain_name}"
  type    = each.value.type

  failover_routing_policy {
    type = "PRIMARY"
  }

  alias {
    name                   = each.value.alias.name
    zone_id                = each.value.alias.zone_id
    evaluate_target_health = true
  }

  set_identifier = "${each.key}-primary"
  health_check_id = aws_route53_health_check["${each.key}_health"].id
}

resource "aws_route53_record" "failover_secondary" {
  for_each = {
    for k, v in var.records : k => v
    if v.failover_routing != null
  }

  zone_id = aws_route53_zone.public[0].zone_id
  name    = "${each.key}.${var.domain_name}"
  type    = each.value.type

  failover_routing_policy {
    type = "SECONDARY"
  }

  alias {
    name                   = each.value.secondary_alias.name
    zone_id                = each.value.secondary_alias.zone_id
    evaluate_target_health = true
  }

  set_identifier = "${each.key}-secondary"
}

# -----------------------------------------------------------------------------
# Latency Records (Multi-region routing)
# -----------------------------------------------------------------------------

resource "aws_route53_record" "latency" {
  for_each = {
    for k, v in var.records : k => v
    if v.latency_routing != null
  }

  zone_id = aws_route53_zone.public[0].zone_id
  name    = "${each.key}.${var.domain_name}"
  type    = each.value.type

  latency_routing_policy {
    region = each.value.region
  }

  alias {
    name                   = each.value.alias.name
    zone_id                = each.value.alias.zone_id
    evaluate_target_health = true
  }

  set_identifier = "${each.key}-${each.value.region}"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "zone_id" {
  description = "ID da hosted zone Route53"
  value       = var.create_public_zone ? aws_route53_zone.public[0].zone_id : aws_route53_zone.private[0].zone_id
}

output "zone_name" {
  description = "Nome da hosted zone"
  value       = var.domain_name
}

output "name_servers" {
  description = "Name servers da hosted zone pública"
  value       = var.create_public_zone ? aws_route53_zone.public[0].name_servers : []
}

output "health_check_ids" {
  description = "IDs dos health checks criados"
  value       = { for k, v in aws_route53_health_check.this : k => v.id }
}
