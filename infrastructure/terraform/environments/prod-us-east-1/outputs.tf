# =============================================================================
# Neural Hive-Mind - Outputs Produção US East 1
# =============================================================================

output "region" {
  description = "Região AWS"
  value       = "us-east-1"
}

output "region_role" {
  description = "Papel da região (primary/secondary)"
  value       = "primary"
}

output "vpc_id" {
  description = "ID da VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "CIDR da VPC"
  value       = module.vpc.vpc_cidr
}

output "private_subnet_ids" {
  description = "IDs das subnets privadas"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "IDs das subnets públicas"
  value       = module.vpc.public_subnet_ids
}

output "database_subnet_ids" {
  description = "IDs das subnets de banco de dados"
  value       = module.vpc.database_subnet_ids
}

output "cluster_name" {
  description = "Nome do cluster EKS"
  value       = module.kubernetes_cluster.cluster_name
}

output "cluster_arn" {
  description = "ARN do cluster EKS"
  value       = module.kubernetes_cluster.cluster_arn
}

output "cluster_endpoint" {
  description = "Endpoint do API server do EKS"
  value       = module.kubernetes_cluster.api_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Certificado CA do cluster"
  value       = module.kubernetes_cluster.certificate_authority_data
  sensitive   = true
}

output "cluster_security_group_id" {
  description = "ID do security group do cluster"
  value       = module.kubernetes_cluster.security_group_id
}

output "mongodb_connection_string" {
  description = "String de conexão MongoDB Atlas"
  value       = module.mongodb_replica_set.connection_string
  sensitive   = true
}

output "mongodb_cluster_id" {
  description = "ID do cluster MongoDB Atlas"
  value       = module.mongodb_replica_set.cluster_id
}

output "redis_primary_endpoint" {
  description = "Endpoint primário do Redis"
  value       = module.redis_cluster.primary_endpoint
  sensitive   = true
}

output "redis_cluster_id" {
  description = "ID do cluster ElastiCache Redis"
  value       = module.redis_cluster.cluster_id
}

output "route53_zone_id" {
  description = "ID da hosted zone Route53"
  value       = module.route53.zone_id
}

output "route53_zone_name_servers" {
  description = "Name servers da hosted zone"
  value       = module.route53.name_servers
}

output "vpc_peering_west_id" {
  description = "ID do peering VPC com US West"
  value       = module.vpc_peering_west.peering_id
}

output "vpc_peering_eu_id" {
  description = "ID do peering VPC com EU West"
  value       = module.vpc_peering_eu.peering_id
}

output "oidc_provider_arn" {
  description = "ARN do provider OIDC do EKS"
  value       = module.kubernetes_cluster.oidc_provider_arn
}

output "oidc_issuer_url" {
  description = "URL do issuer OIDC"
  value       = module.kubernetes_cluster.oidc_issuer_url
}
