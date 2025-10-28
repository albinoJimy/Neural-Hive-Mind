# Sigstore IRSA Module
# Creates IAM Role for Service Account (IRSA) for Sigstore Policy Controller

data "aws_iam_policy_document" "sigstore_trust_policy" {
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
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

# IAM policy for Sigstore Policy Controller
# Minimal permissions needed for image signature verification
data "aws_iam_policy_document" "sigstore_policy" {
  # KMS permissions for signature verification if using AWS KMS
  # NOTE: This is only needed if you're using AWS KMS for signing/verifying
  # For standard Sigstore (cosign) with public keys, these permissions are not required
  statement {
    sid    = "KMSAccess"
    effect = "Allow"

    actions = [
      "kms:DescribeKey",
      "kms:GetPublicKey",
      "kms:Verify"
    ]

    # Restrict to specific KMS keys if possible
    # Replace with actual key ARNs when KMS keys are created
    resources = [
      "arn:aws:kms:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:key/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "kms:RequestAlias"
      values   = ["alias/sigstore-*", "alias/container-signing-*"]
    }
  }

  # CloudWatch logs permissions for audit trail
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ]

    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/eks/${var.cluster_name}/sigstore-policy-controller*"
    ]
  }
}

# Get current AWS region and account ID
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Create IAM policy
resource "aws_iam_policy" "sigstore_policy" {
  name_prefix = "${var.cluster_name}-sigstore-policy-controller-"
  description = "IAM policy for Sigstore Policy Controller IRSA"
  policy      = data.aws_iam_policy_document.sigstore_policy.json

  tags = merge(var.tags, {
    Component = "sigstore-policy-controller"
    Purpose   = "irsa"
  })
}

# Create IAM role
resource "aws_iam_role" "sigstore_role" {
  name_prefix        = "${var.cluster_name}-sigstore-policy-controller-"
  description        = "IAM role for Sigstore Policy Controller service account"
  assume_role_policy = data.aws_iam_policy_document.sigstore_trust_policy.json

  tags = merge(var.tags, {
    Component = "sigstore-policy-controller"
    Purpose   = "irsa"
  })
}

# Attach policy to role
resource "aws_iam_role_policy_attachment" "sigstore_policy_attachment" {
  role       = aws_iam_role.sigstore_role.name
  policy_arn = aws_iam_policy.sigstore_policy.arn
}