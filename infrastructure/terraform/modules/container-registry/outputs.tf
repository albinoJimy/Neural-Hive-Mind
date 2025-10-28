# Outputs do Módulo Container Registry - Neural Hive-Mind

output "registry_urls" {
  description = "URLs dos repositórios ECR criados"
  value       = { for k, v in aws_ecr_repository.neural_hive : k => v.repository_url }
}

output "registry_arns" {
  description = "ARNs dos repositórios ECR criados"
  value       = { for k, v in aws_ecr_repository.neural_hive : k => v.arn }
}

output "registry_kms_key_arn" {
  description = "ARN da chave KMS para criptografia de imagens"
  value       = aws_kms_key.registry.arn
}

output "signing_kms_key_arn" {
  description = "ARN da chave KMS para assinatura de imagens"
  value       = var.enable_image_signing ? aws_kms_key.signing[0].arn : null
}

output "image_signing_role_arn" {
  description = "ARN da role IAM para assinatura de imagens"
  value       = var.enable_image_signing ? aws_iam_role.image_signing[0].arn : null
}

output "ecr_read_policy_arn" {
  description = "ARN da política IAM para leitura de imagens"
  value       = aws_iam_policy.ecr_read.arn
}

output "ecr_write_policy_arn" {
  description = "ARN da política IAM para escrita de imagens"
  value       = aws_iam_policy.ecr_write.arn
}

output "vulnerability_topic_arn" {
  description = "ARN do tópico SNS para notificações de vulnerabilidades"
  value       = var.enable_vulnerability_scanning ? aws_sns_topic.vulnerability_notifications[0].arn : null
}

output "vulnerability_processor_function_name" {
  description = "Nome da função Lambda para processar vulnerabilidades"
  value       = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? aws_lambda_function.vulnerability_processor[0].function_name : null
}