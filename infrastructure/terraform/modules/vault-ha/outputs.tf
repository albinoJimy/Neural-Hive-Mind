# Outputs do módulo Vault HA

output "kms_key_id" {
  description = "ID da KMS key para Vault auto-unseal"
  value       = aws_kms_key.vault_unseal.key_id
}

output "kms_key_arn" {
  description = "ARN da KMS key para Vault auto-unseal"
  value       = aws_kms_key.vault_unseal.arn
}

output "vault_server_role_arn" {
  description = "ARN do IAM role para Vault server (IRSA)"
  value       = aws_iam_role.vault_server.arn
}

output "vault_server_role_name" {
  description = "Nome do IAM role para Vault server"
  value       = aws_iam_role.vault_server.name
}

output "root_token_secret_arn" {
  description = "ARN do Secrets Manager secret para Vault root token"
  value       = aws_secretsmanager_secret.vault_root_token.arn
}

output "unseal_keys_secret_arn" {
  description = "ARN do Secrets Manager secret para Vault unseal keys"
  value       = aws_secretsmanager_secret.vault_unseal_keys.arn
}

output "audit_logs_bucket_name" {
  description = "Nome do S3 bucket para Vault audit logs"
  value       = var.enable_audit_logs ? aws_s3_bucket.vault_audit_logs[0].id : null
}

output "audit_logs_bucket_arn" {
  description = "ARN do S3 bucket para Vault audit logs"
  value       = var.enable_audit_logs ? aws_s3_bucket.vault_audit_logs[0].arn : null
}
