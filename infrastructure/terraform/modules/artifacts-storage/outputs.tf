# Outputs para módulo artifacts-storage

output "bucket_name" {
  description = "Nome do bucket S3"
  value       = aws_s3_bucket.artifacts.id
}

output "bucket_arn" {
  description = "ARN do bucket S3"
  value       = aws_s3_bucket.artifacts.arn
}

output "bucket_region" {
  description = "Região do bucket S3"
  value       = data.aws_region.current.name
}

output "code_forge_role_arn" {
  description = "ARN do IAM role para Code Forge (IRSA)"
  value       = aws_iam_role.code_forge_s3.arn
}
