# Vault HA Module - Recursos AWS para Vault com auto-unseal e IRSA

# KMS Key para auto-unseal do Vault
resource "aws_kms_key" "vault_unseal" {
  description             = "KMS key para Vault auto-unseal no cluster ${var.cluster_name}"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-vault-unseal"
      Component   = "vault"
      Environment = var.environment
    }
  )
}

resource "aws_kms_alias" "vault_unseal" {
  name          = "alias/${var.cluster_name}-vault-unseal"
  target_key_id = aws_kms_key.vault_unseal.key_id
}

# IAM Role para Vault Server com IRSA (IAM Roles for Service Accounts)
resource "aws_iam_role" "vault_server" {
  name = "${var.cluster_name}-vault-server"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = var.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${replace(var.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:vault:vault-server"
            "${replace(var.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-vault-server"
      Component   = "vault"
      Environment = var.environment
    }
  )
}

# IAM Policy para Vault Server - KMS access
resource "aws_iam_policy" "vault_kms_unseal" {
  name        = "${var.cluster_name}-vault-kms-unseal"
  description = "Permite Vault usar KMS para auto-unseal"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.vault_unseal.arn
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "vault_kms_unseal" {
  role       = aws_iam_role.vault_server.name
  policy_arn = aws_iam_policy.vault_kms_unseal.arn
}

# IAM Policy para Vault Server - Secrets Manager (para root token e unseal keys backup)
resource "aws_iam_policy" "vault_secrets_manager" {
  name        = "${var.cluster_name}-vault-secrets-manager"
  description = "Permite Vault acessar Secrets Manager para backup de tokens"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:CreateSecret",
          "secretsmanager:UpdateSecret",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:${var.cluster_name}/vault/*"
        ]
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "vault_secrets_manager" {
  role       = aws_iam_role.vault_server.name
  policy_arn = aws_iam_policy.vault_secrets_manager.arn
}

# Secrets Manager Secret para Vault root token (criado manualmente ou por init job)
resource "aws_secretsmanager_secret" "vault_root_token" {
  name                    = "${var.cluster_name}/vault/root-token"
  description             = "Vault root token para cluster ${var.cluster_name}"
  recovery_window_in_days = 30

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-vault-root-token"
      Component   = "vault"
      Environment = var.environment
    }
  )
}

# Secrets Manager Secret para unseal keys backup
resource "aws_secretsmanager_secret" "vault_unseal_keys" {
  name                    = "${var.cluster_name}/vault/unseal-keys"
  description             = "Vault unseal keys backup para cluster ${var.cluster_name}"
  recovery_window_in_days = 30

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-vault-unseal-keys"
      Component   = "vault"
      Environment = var.environment
    }
  )
}

# S3 Bucket para Vault audit logs (opcional)
resource "aws_s3_bucket" "vault_audit_logs" {
  count  = var.enable_audit_logs ? 1 : 0
  bucket = "${var.cluster_name}-vault-audit-logs"

  tags = merge(
    var.tags,
    {
      Name        = "${var.cluster_name}-vault-audit-logs"
      Component   = "vault"
      Environment = var.environment
    }
  )
}

resource "aws_s3_bucket_versioning" "vault_audit_logs" {
  count  = var.enable_audit_logs ? 1 : 0
  bucket = aws_s3_bucket.vault_audit_logs[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "vault_audit_logs" {
  count  = var.enable_audit_logs ? 1 : 0
  bucket = aws_s3_bucket.vault_audit_logs[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "vault_audit_logs" {
  count  = var.enable_audit_logs ? 1 : 0
  bucket = aws_s3_bucket.vault_audit_logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# IAM Policy para S3 audit logs
resource "aws_iam_policy" "vault_audit_logs" {
  count       = var.enable_audit_logs ? 1 : 0
  name        = "${var.cluster_name}-vault-audit-logs"
  description = "Permite Vault escrever audit logs no S3"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.vault_audit_logs[0].arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.vault_audit_logs[0].arn
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "vault_audit_logs" {
  count      = var.enable_audit_logs ? 1 : 0
  role       = aws_iam_role.vault_server.name
  policy_arn = aws_iam_policy.vault_audit_logs[0].arn
}
