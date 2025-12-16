# Outputs Root - Neural Hive-Mind Infrastructure

# Outputs da Rede
output "vpc_id" {
  description = "ID da VPC criada"
  value       = module.network.vpc_id
}

output "vpc_cidr" {
  description = "CIDR block da VPC"
  value       = module.network.vpc_cidr
}

output "private_subnet_ids" {
  description = "Lista de IDs das subnets privadas"
  value       = module.network.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Lista de IDs das subnets públicas"
  value       = module.network.public_subnet_ids
}

output "availability_zones" {
  description = "Zonas de disponibilidade utilizadas"
  value       = module.network.availability_zones
}

output "nat_gateway_ips" {
  description = "IPs elásticos dos NAT Gateways"
  value       = module.network.nat_gateway_ips
}

# Outputs do Cluster Kubernetes
output "cluster_endpoint" {
  description = "Endpoint para API do cluster EKS"
  value       = module.k8s-cluster.cluster_endpoint
}

output "cluster_ca_certificate" {
  description = "Certificado CA do cluster em base64"
  value       = module.k8s-cluster.cluster_certificate_authority
}

output "cluster_name" {
  description = "Nome do cluster EKS"
  value       = module.k8s-cluster.cluster_name
}

output "cluster_arn" {
  description = "ARN do cluster EKS"
  value       = module.k8s-cluster.cluster_arn
}

output "cluster_version" {
  description = "Versão do Kubernetes do cluster"
  value       = module.k8s-cluster.cluster_version
}

output "oidc_issuer_url" {
  description = "URL do OIDC issuer do cluster"
  value       = module.k8s-cluster.oidc_issuer_url
}

output "oidc_provider_arn" {
  description = "ARN do OIDC provider"
  value       = module.k8s-cluster.oidc_provider_arn
}

output "cluster_security_group_id" {
  description = "ID do security group do cluster"
  value       = module.k8s-cluster.cluster_security_group_id
}

output "cluster_autoscaler_role_arn" {
  description = "ARN da role IAM do Cluster Autoscaler"
  value       = module.k8s-cluster.cluster_autoscaler_role_arn
}

output "load_balancer_controller_role_arn" {
  description = "ARN da role IAM do Load Balancer Controller"
  value       = module.k8s-cluster.load_balancer_controller_role_arn
}

# Outputs do Container Registry
output "registry_urls" {
  description = "URLs dos repositórios ECR criados"
  value       = module.container-registry.registry_urls
}

output "registry_arns" {
  description = "ARNs dos repositórios ECR criados"
  value       = module.container-registry.registry_arns
}

output "registry_kms_key_arn" {
  description = "ARN da chave KMS para criptografia de imagens"
  value       = module.container-registry.registry_kms_key_arn
}

output "signing_kms_key_arn" {
  description = "ARN da chave KMS para assinatura de imagens"
  value       = module.container-registry.signing_kms_key_arn
}

output "image_signing_role_arn" {
  description = "ARN da role IAM para assinatura de imagens"
  value       = module.container-registry.image_signing_role_arn
}

output "vulnerability_topic_arn" {
  description = "ARN do tópico SNS para notificações de vulnerabilidades"
  value       = module.container-registry.vulnerability_topic_arn
}

output "vulnerability_processor_function_name" {
  description = "Nome da função Lambda para processar vulnerabilidades"
  value       = module.container-registry.vulnerability_processor_function_name
}

# Outputs do Sigstore IRSA
output "sigstore_irsa_role_arn" {
  description = "ARN da IAM role criada para Sigstore Policy Controller IRSA"
  value       = module["sigstore-irsa"].role_arn
}

# Outputs para integração com kubectl
output "kubectl_config_command" {
  description = "Comando para configurar kubectl"
  value       = "aws eks update-kubeconfig --region us-east-1 --name ${module.k8s-cluster.cluster_name}"
}

# Outputs da Camada de Memória

# MongoDB Outputs
output "mongodb_namespace" {
  description = "Namespace do MongoDB"
  value       = module.mongodb_cluster.namespace
}

output "mongodb_connection_string" {
  description = "String de conexão MongoDB"
  value       = module.mongodb_cluster.connection_string
  sensitive   = true
}

output "mongodb_service_name" {
  description = "Nome do Service MongoDB"
  value       = module.mongodb_cluster.service_name
}

# Neo4j Outputs
output "neo4j_namespace" {
  description = "Namespace do Neo4j"
  value       = module.neo4j_cluster.namespace
}

output "neo4j_bolt_uri" {
  description = "URI Bolt do Neo4j"
  value       = module.neo4j_cluster.bolt_uri
}

output "neo4j_http_uri" {
  description = "URI HTTP do Neo4j"
  value       = module.neo4j_cluster.http_uri
}

# ClickHouse Outputs
output "clickhouse_namespace" {
  description = "Namespace do ClickHouse"
  value       = module.clickhouse_cluster.namespace
}

output "clickhouse_http_uri" {
  description = "URI HTTP do ClickHouse"
  value       = module.clickhouse_cluster.http_uri
}

output "clickhouse_native_uri" {
  description = "URI Native do ClickHouse"
  value       = module.clickhouse_cluster.native_uri
  sensitive   = true
}

# Outputs Vault HA
output "kms_key_id" {
  description = "KMS Key ID utilizada para auto-unseal do Vault"
  value       = module.vault-ha.kms_key_id
}

output "vault_server_role_arn" {
  description = "IAM Role ARN associada ao serviço Vault via IRSA"
  value       = module.vault-ha.vault_server_role_arn
}

output "audit_logs_bucket_name" {
  description = "Bucket S3 para logs de auditoria do Vault"
  value       = module.vault-ha.audit_logs_bucket_name
}

# Outputs SPIRE datastore
output "connection_string" {
  description = "Connection string do banco de dados do SPIRE Server"
  value       = module.spire-datastore.connection_string
  sensitive   = true
}

output "secret_arn" {
  description = "ARN do secret no AWS Secrets Manager para SPIRE datastore"
  value       = module.spire-datastore.secret_arn
}

output "secret_name" {
  description = "Nome do secret no AWS Secrets Manager para SPIRE datastore"
  value       = module.spire-datastore.secret_name
}
