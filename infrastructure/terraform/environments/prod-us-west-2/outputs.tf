# =============================================================================
# Neural Hive-Mind - Outputs Produção US West 2
# =============================================================================

output "region" {
  description = "Região AWS"
  value       = "us-west-2"
}

output "region_role" {
  description = "Papel da região (secondary)"
  value       = "secondary"
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

output "vpc_peering_east_id" {
  description = "ID do peering VPC com US East"
  value       = module.vpc_peering_east.peering_id
}

output "oidc_provider_arn" {
  description = "ARN do provider OIDC do EKS"
  value       = module.kubernetes_cluster.oidc_provider_arn
}

output "oidc_issuer_url" {
  description = "URL do issuer OIDC"
  value       = module.kubernetes_cluster.oidc_issuer_url
}
