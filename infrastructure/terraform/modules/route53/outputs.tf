# =============================================================================
# Neural Hive-Mind - Route53 Outputs
# =============================================================================

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

output "record_ids" {
  description = "IDs dos registros DNS criados"
  value       = { for k, v in aws_route53_record.this : k => v.id }
}
