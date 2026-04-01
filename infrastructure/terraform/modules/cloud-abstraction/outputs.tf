# Outputs para Cloud Abstraction Module
# Retorna informações independentes de provider

output "cluster_endpoint" {
  description = "Endpoint API do cluster Kubernetes"
  value       = module.cloud_cluster.cluster_endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "Certificado CA do cluster"
  value       = module.cloud_cluster.cluster_ca_certificate
  sensitive   = true
}

output "cluster_name" {
  description = "Nome do cluster Kubernetes"
  value       = module.cloud_cluster.cluster_name
}

output "cluster_id" {
  description = "ID único do cluster"
  value       = module.cloud_cluster.cluster_id
}

output "vpc_id" {
  description = "ID da VPC/VNet"
  value       = module.cloud_network.vpc_id
}

output "private_subnet_ids" {
  description = "IDs das subnets privadas"
  value       = module.cloud_network.private_subnet_ids
}

output "public_subnet_ids" {
  description = "IDs das subnets públicas"
  value       = module.cloud_network.public_subnet_ids
}

output "node_security_group_id" {
  description = "ID do security group dos nós"
  value       = module.cloud_cluster.node_security_group_id
}

output "oidc_provider_arn" {
  description = "ARN do provider OIDC para IRSA"
  value       = module.cloud_cluster.oidc_provider_arn
}

output "oidc_provider_url" {
  description = "URL do provider OIDC"
  value       = module.cloud_cluster.oidc_provider_url
}

output "cloud_provider" {
  description = "Provider de cloud utilizado"
  value       = var.cloud_provider
}
