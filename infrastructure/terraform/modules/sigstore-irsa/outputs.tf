output "role_arn" {
  description = "ARN of the IAM role created for Sigstore Policy Controller IRSA"
  value       = aws_iam_role.sigstore_role.arn
}

output "role_name" {
  description = "Name of the IAM role created for Sigstore Policy Controller IRSA"
  value       = aws_iam_role.sigstore_role.name
}

output "policy_arn" {
  description = "ARN of the IAM policy attached to the Sigstore Policy Controller role"
  value       = aws_iam_policy.sigstore_policy.arn
}