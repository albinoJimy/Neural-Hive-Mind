# Outputs do Módulo Cluster Kubernetes - Neural Hive-Mind

output "cluster_endpoint" {
  description = "Endpoint para API do cluster EKS"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_certificate_authority" {
  description = "Certificado CA do cluster em base64"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "cluster_name" {
  description = "Nome do cluster EKS"
  value       = aws_eks_cluster.main.name
}

output "cluster_arn" {
  description = "ARN do cluster EKS"
  value       = aws_eks_cluster.main.arn
}

output "cluster_version" {
  description = "Versão do Kubernetes do cluster"
  value       = aws_eks_cluster.main.version
}

output "node_group_arns" {
  description = "ARNs dos node groups"
  value       = aws_eks_node_group.main[*].arn
}

output "node_group_ids" {
  description = "IDs dos node groups"
  value       = aws_eks_node_group.main[*].id
}

output "oidc_issuer_url" {
  description = "URL do OIDC issuer do cluster"
  value       = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

output "oidc_provider_arn" {
  description = "ARN do OIDC provider"
  value       = aws_iam_openid_connect_provider.cluster.arn
}

output "cluster_security_group_id" {
  description = "ID do security group do cluster"
  value       = aws_security_group.cluster.id
}

output "cluster_iam_role_arn" {
  description = "ARN da role IAM do cluster"
  value       = aws_iam_role.cluster.arn
}

output "node_iam_role_arn" {
  description = "ARN da role IAM dos nodes"
  value       = aws_iam_role.node_group.arn
}

output "cluster_autoscaler_role_arn" {
  description = "ARN da role IAM do Cluster Autoscaler"
  value       = var.enable_cluster_autoscaler ? aws_iam_role.cluster_autoscaler[0].arn : null
}

output "load_balancer_controller_role_arn" {
  description = "ARN da role IAM do Load Balancer Controller"
  value       = var.enable_load_balancer_controller ? aws_iam_role.load_balancer_controller[0].arn : null
}

output "kms_key_arn" {
  description = "ARN da chave KMS para criptografia de secrets"
  value       = aws_kms_key.cluster.arn
}

output "nodes_kms_key_arn" {
  description = "ARN da chave KMS para criptografia de volumes EBS"
  value       = aws_kms_key.nodes.arn
}