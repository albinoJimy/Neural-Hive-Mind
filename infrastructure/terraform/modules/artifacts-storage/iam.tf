# IAM policies e role para Code Forge acessar S3

# Policy document para trust (IRSA)
data "aws_iam_policy_document" "code_forge_trust_policy" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:neural-hive-execution:code-forge"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

# Policy para write (upload de SBOMs e artefatos)
data "aws_iam_policy_document" "code_forge_s3_write" {
  statement {
    sid    = "S3WriteAccess"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:GetObject",
      "s3:DeleteObject"
    ]

    resources = [
      "${aws_s3_bucket.artifacts.arn}/sboms/*",
      "${aws_s3_bucket.artifacts.arn}/artifacts/*"
    ]
  }

  statement {
    sid    = "S3ListAccess"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation"
    ]

    resources = [
      aws_s3_bucket.artifacts.arn
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["sboms/*", "artifacts/*"]
    }
  }
}

# Policy para read (leitura de SBOMs)
data "aws_iam_policy_document" "code_forge_s3_read" {
  statement {
    sid    = "S3ReadAccess"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:GetObjectAttributes"
    ]

    resources = [
      "${aws_s3_bucket.artifacts.arn}/*"
    ]
  }

  statement {
    sid    = "S3ListReadAccess"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation"
    ]

    resources = [
      aws_s3_bucket.artifacts.arn
    ]
  }
}

# Criar IAM policy para write
resource "aws_iam_policy" "code_forge_s3_write" {
  name_prefix = "${var.cluster_name}-code-forge-s3-write-"
  description = "IAM policy para Code Forge write no S3"
  policy      = data.aws_iam_policy_document.code_forge_s3_write.json

  tags = merge(var.tags, {
    Component = "code-forge"
    Purpose   = "s3-artifacts"
  })
}

# Criar IAM policy para read
resource "aws_iam_policy" "code_forge_s3_read" {
  name_prefix = "${var.cluster_name}-code-forge-s3-read-"
  description = "IAM policy para Code Forge read no S3"
  policy      = data.aws_iam_policy_document.code_forge_s3_read.json

  tags = merge(var.tags, {
    Component = "code-forge"
    Purpose   = "s3-artifacts"
  })
}

# Criar IAM role (IRSA)
resource "aws_iam_role" "code_forge_s3" {
  name_prefix        = "${var.cluster_name}-code-forge-s3-"
  description        = "IAM role para Code Forge acessar S3"
  assume_role_policy = data.aws_iam_policy_document.code_forge_trust_policy.json

  tags = merge(var.tags, {
    Component = "code-forge"
    Purpose   = "irsa"
  })
}

# Attach write policy ao role
resource "aws_iam_role_policy_attachment" "code_forge_s3_write" {
  role       = aws_iam_role.code_forge_s3.name
  policy_arn = aws_iam_policy.code_forge_s3_write.arn
}

# Attach read policy ao role
resource "aws_iam_role_policy_attachment" "code_forge_s3_read" {
  role       = aws_iam_role.code_forge_s3.name
  policy_arn = aws_iam_policy.code_forge_s3_read.arn
}
