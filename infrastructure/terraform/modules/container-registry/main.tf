# Módulo Container Registry - Neural Hive-Mind Fase 1
# Registry OCI seguro com scanning de vulnerabilidades e assinatura de imagens

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  common_tags = merge(
    var.tags,
    {
      Module      = "container-registry"
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "neural-hive-mind"
    }
  )
}

# ECR Repository para imagens do Neural Hive-Mind
resource "aws_ecr_repository" "neural_hive" {
  for_each = toset(var.repository_names)

  name                 = "${var.registry_name}/${each.value}"
  image_tag_mutability = var.image_tag_mutability

  encryption_configuration {
    encryption_type = "KMS"
    kms_key        = aws_kms_key.registry.arn
  }

  image_scanning_configuration {
    scan_on_push = var.enable_vulnerability_scanning
  }

  tags = merge(
    local.common_tags,
    {
      Name       = "${var.registry_name}/${each.value}"
      Repository = each.value
    }
  )
}

# Enhanced scanning configuration com Inspector v2
resource "aws_ecr_registry_scanning_configuration" "enhanced" {
  count = var.enable_vulnerability_scanning ? 1 : 0

  scan_type = "ENHANCED"

  rule {
    scan_frequency = "SCAN_ON_PUSH"
    repository_filter {
      filter      = "*"
      filter_type = "WILDCARD"
    }
  }
}

# KMS Key para criptografia de imagens
resource "aws_kms_key" "registry" {
  description             = "KMS key para criptografia de imagens ECR ${var.registry_name}"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.registry_name}-ecr-kms"
    }
  )
}

resource "aws_kms_alias" "registry" {
  name          = "alias/${var.registry_name}-ecr"
  target_key_id = aws_kms_key.registry.key_id
}

# Política de retenção de imagens
resource "aws_ecr_lifecycle_policy" "retention" {
  for_each = aws_ecr_repository.neural_hive

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Manter últimas ${var.image_retention_count} imagens"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "release"]
          countType     = "imageCountMoreThan"
          countNumber   = var.image_retention_count
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Remover imagens untagged após ${var.untagged_retention_days} dias"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_retention_days
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# IAM Policy para acesso ao ECR
resource "aws_iam_policy" "ecr_read" {
  name        = "${var.registry_name}-ecr-read"
  description = "Política para leitura de imagens ECR"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetAuthorizationToken",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages"
        ]
        Resource = concat(
          [for repo in aws_ecr_repository.neural_hive : repo.arn],
          ["*"]
        )
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_policy" "ecr_write" {
  name        = "${var.registry_name}-ecr-write"
  description = "Política para escrita de imagens ECR"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetAuthorizationToken",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = concat(
          [for repo in aws_ecr_repository.neural_hive : repo.arn],
          ["*"]
        )
      }
    ]
  })

  tags = local.common_tags
}

# EventBridge Rule para notificação de vulnerabilidades ECR
resource "aws_cloudwatch_event_rule" "vulnerability_findings" {
  count = var.enable_vulnerability_scanning ? 1 : 0

  name        = "${var.registry_name}-ecr-vulnerability-findings"
  description = "Captura findings de vulnerabilidades ECR"

  event_pattern = jsonencode({
    source      = ["aws.ecr"]
    detail-type = ["ECR Image Scan"]
    detail = {
      scan-status = ["COMPLETE"]
      repository-name = [for repo in var.repository_names : "${var.registry_name}/${repo}"]
    }
  })

  tags = local.common_tags
}

# EventBridge Rule para Inspector findings
resource "aws_cloudwatch_event_rule" "inspector_findings" {
  count = var.enable_vulnerability_scanning ? 1 : 0

  name        = "${var.registry_name}-inspector-vulnerability-findings"
  description = "Captura findings de vulnerabilidades Inspector"

  event_pattern = jsonencode({
    source      = ["aws.inspector2"]
    detail-type = ["Inspector2 Finding"]
    detail = {
      type = ["CONTAINER_IMAGE"]
    }
  })

  tags = local.common_tags
}

# SNS Topic para notificações
resource "aws_sns_topic" "vulnerability_notifications" {
  count = var.enable_vulnerability_scanning ? 1 : 0

  name              = "${var.registry_name}-vulnerability-notifications"
  kms_master_key_id = aws_kms_key.registry.id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.registry_name}-vulnerability-sns"
    }
  )
}

# EventBridge Target para SNS (ECR)
resource "aws_cloudwatch_event_target" "sns_ecr" {
  count = var.enable_vulnerability_scanning ? 1 : 0

  rule      = aws_cloudwatch_event_rule.vulnerability_findings[0].name
  target_id = "vulnerability-ecr-sns"
  arn       = aws_sns_topic.vulnerability_notifications[0].arn

  input_transformer {
    input_paths = {
      repository = "$.detail.repository-name"
      severity   = "$.detail.finding-severity-counts"
      status     = "$.detail.scan-status"
    }

    input_template = "\"ECR Scan Complete for <repository>. Severity counts: <severity>\""
  }
}

# EventBridge Target para SNS (Inspector)
resource "aws_cloudwatch_event_target" "sns_inspector" {
  count = var.enable_vulnerability_scanning ? 1 : 0

  rule      = aws_cloudwatch_event_rule.inspector_findings[0].name
  target_id = "vulnerability-inspector-sns"
  arn       = aws_sns_topic.vulnerability_notifications[0].arn

  input_transformer {
    input_paths = {
      severity = "$.detail.severity"
      title    = "$.detail.title"
      type     = "$.detail.type"
    }

    input_template = "\"Inspector2 Finding: <title>. Severity: <severity>. Type: <type>\""
  }
}

# Dados do arquivo zip da função Lambda
data "archive_file" "vulnerability_processor" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  type        = "zip"
  source_file = "${path.module}/lambda/vulnerability_processor.py"
  output_path = "${path.module}/lambda/vulnerability_processor.zip"
}

# Lambda para processar vulnerabilidades críticas
resource "aws_lambda_function" "vulnerability_processor" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  filename         = data.archive_file.vulnerability_processor[0].output_path
  source_code_hash = data.archive_file.vulnerability_processor[0].output_base64sha256
  function_name    = "${var.registry_name}-vulnerability-processor"
  role            = aws_iam_role.lambda_execution[0].arn
  handler         = "vulnerability_processor.handler"
  runtime         = "python3.11"
  timeout         = 60

  environment {
    variables = {
      REGISTRY_NAME = var.registry_name
      SNS_TOPIC_ARN = aws_sns_topic.vulnerability_notifications[0].arn
      CRITICAL_SEVERITY_THRESHOLD = var.critical_severity_threshold
    }
  }

  tags = local.common_tags
}

# IAM Role para Lambda
resource "aws_iam_role" "lambda_execution" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  name = "${var.registry_name}-lambda-vulnerability-processor"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Política para Lambda
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.lambda_execution[0].name
}

resource "aws_iam_role_policy" "lambda_ecr_sns" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  role = aws_iam_role.lambda_execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:DescribeImageScanFindings",
          "ecr:GetRepositoryPolicy",
          "ecr:SetRepositoryPolicy",
          "ecr:PutImageTagMutability"
        ]
        Resource = [for repo in aws_ecr_repository.neural_hive : repo.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.vulnerability_notifications[0].arn
      }
    ]
  })
}

# EventBridge Target para Lambda (ECR)
resource "aws_cloudwatch_event_target" "lambda_ecr" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  rule      = aws_cloudwatch_event_rule.vulnerability_findings[0].name
  target_id = "vulnerability-ecr-lambda"
  arn       = aws_lambda_function.vulnerability_processor[0].arn
}

# EventBridge Target para Lambda (Inspector)
resource "aws_cloudwatch_event_target" "lambda_inspector" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  rule      = aws_cloudwatch_event_rule.inspector_findings[0].name
  target_id = "vulnerability-inspector-lambda"
  arn       = aws_lambda_function.vulnerability_processor[0].arn
}

resource "aws_lambda_permission" "allow_eventbridge_ecr" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridgeECR"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.vulnerability_processor[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.vulnerability_findings[0].arn
}

resource "aws_lambda_permission" "allow_eventbridge_inspector" {
  count = var.enable_vulnerability_scanning && var.block_critical_vulnerabilities ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridgeInspector"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.vulnerability_processor[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.inspector_findings[0].arn
}

# IAM Role para assinatura de imagens (Sigstore/Notation)
resource "aws_iam_role" "image_signing" {
  count = var.enable_image_signing ? 1 : 0

  name = "${var.registry_name}-image-signing"

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
            "${replace(var.oidc_issuer_url, "https://", "")}:sub" = "system:serviceaccount:${var.signing_namespace}:image-signer"
            "${replace(var.oidc_issuer_url, "https://", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Política para assinatura de imagens
resource "aws_iam_role_policy" "image_signing" {
  count = var.enable_image_signing ? 1 : 0

  role = aws_iam_role.image_signing[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Sign",
          "kms:Verify",
          "kms:DescribeKey",
          "kms:GetPublicKey"
        ]
        Resource = aws_kms_key.signing[0].arn
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:PutImageTagMutability",
          "ecr:StartImageScan",
          "ecr:DescribeImages",
          "ecr:DescribeImageScanFindings"
        ]
        Resource = [for repo in aws_ecr_repository.neural_hive : repo.arn]
      }
    ]
  })
}

# KMS Key para assinatura de imagens
resource "aws_kms_key" "signing" {
  count = var.enable_image_signing ? 1 : 0

  description             = "KMS key para assinatura de imagens ${var.registry_name}"
  deletion_window_in_days = 10
  enable_key_rotation     = false # Assinatura não suporta rotação automática
  key_usage               = "SIGN_VERIFY"

  customer_master_key_spec = "RSA_4096"

  tags = merge(
    local.common_tags,
    {
      Name = "${var.registry_name}-signing-kms"
      Purpose = "image-signing"
    }
  )
}

resource "aws_kms_alias" "signing" {
  count = var.enable_image_signing ? 1 : 0

  name          = "alias/${var.registry_name}-signing"
  target_key_id = aws_kms_key.signing[0].key_id
}