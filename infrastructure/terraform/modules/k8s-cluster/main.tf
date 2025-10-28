# Módulo Cluster Kubernetes - Neural Hive-Mind Fase 1
# Cluster EKS multi-zona com auto-scaling

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }
}

locals {
  common_tags = merge(
    var.tags,
    {
      Module        = "k8s-cluster"
      Environment   = var.environment
      ManagedBy     = "terraform"
      Project       = "neural-hive-mind"
      ClusterName   = var.cluster_name
    }
  )
}

# IAM Role para o Cluster EKS
resource "aws_iam_role" "cluster" {
  name = "${var.cluster_name}-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Políticas IAM para o Cluster
resource "aws_iam_role_policy_attachment" "cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.cluster.name
}

resource "aws_iam_role_policy_attachment" "vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.cluster.name
}

# Security Group para o Control Plane
resource "aws_security_group" "cluster" {
  name_prefix = "${var.cluster_name}-cluster-sg"
  description = "Security group para control plane do EKS"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.cluster_name}-cluster-sg"
    }
  )
}

# Cluster EKS
resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  version  = var.kubernetes_version
  role_arn = aws_iam_role.cluster.arn

  vpc_config {
    subnet_ids              = concat(var.private_subnet_ids, var.public_subnet_ids)
    endpoint_private_access = var.enable_private_endpoint
    endpoint_public_access  = var.enable_public_endpoint
    public_access_cidrs     = var.public_access_cidrs
    security_group_ids      = [aws_security_group.cluster.id]
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.cluster.arn
    }
    resources = ["secrets"]
  }

  enabled_cluster_log_types = var.enabled_log_types

  tags = local.common_tags

  depends_on = [
    aws_iam_role_policy_attachment.cluster_policy,
    aws_iam_role_policy_attachment.vpc_resource_controller,
  ]
}

# KMS Key para criptografia de secrets
resource "aws_kms_key" "cluster" {
  description             = "KMS key para criptografia de secrets do EKS ${var.cluster_name}"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.cluster_name}-secrets-kms"
    }
  )
}

resource "aws_kms_alias" "cluster" {
  name          = "alias/${var.cluster_name}-secrets"
  target_key_id = aws_kms_key.cluster.key_id
}

# IAM Role para Node Groups
resource "aws_iam_role" "node_group" {
  name = "${var.cluster_name}-node-group-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Políticas IAM para Node Groups
resource "aws_iam_role_policy_attachment" "node_group_worker" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.node_group.name
}

resource "aws_iam_role_policy_attachment" "node_group_cni" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.node_group.name
}

resource "aws_iam_role_policy_attachment" "node_group_registry" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.node_group.name
}

resource "aws_iam_role_policy_attachment" "node_group_ssm" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  role       = aws_iam_role.node_group.name
}

# Launch Template para Node Groups
resource "aws_launch_template" "node_group" {
  name_prefix = "${var.cluster_name}-node-"

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size = var.disk_size_gb
      volume_type = "gp3"
      encrypted   = true
      kms_key_id  = aws_kms_key.nodes.arn
    }
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }

  monitoring {
    enabled = true
  }

  user_data = base64encode(templatefile("${path.module}/user_data.tpl", {
    cluster_name = var.cluster_name
    endpoint     = aws_eks_cluster.main.endpoint
    ca_cert      = aws_eks_cluster.main.certificate_authority[0].data
  }))

  tag_specifications {
    resource_type = "instance"
    tags = merge(
      local.common_tags,
      {
        Name = "${var.cluster_name}-node"
      }
    )
  }
}

# KMS Key para criptografia de volumes EBS dos nodes
resource "aws_kms_key" "nodes" {
  description             = "KMS key para criptografia de volumes EBS dos nodes ${var.cluster_name}"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.cluster_name}-nodes-kms"
    }
  )
}

resource "aws_kms_alias" "nodes" {
  name          = "alias/${var.cluster_name}-nodes"
  target_key_id = aws_kms_key.nodes.key_id
}

# Node Groups Gerenciados - Um por AZ para alta disponibilidade
resource "aws_eks_node_group" "main" {
  # Valida que o número de availability zones corresponde ao número de subnets
  count = min(length(var.availability_zones), length(var.private_subnet_ids))

  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-ng-${var.availability_zones[count.index]}"
  node_role_arn   = aws_iam_role.node_group.arn
  subnet_ids      = [var.private_subnet_ids[count.index]]

  scaling_config {
    desired_size = var.desired_nodes_per_zone
    max_size     = var.max_nodes_per_zone
    min_size     = var.min_nodes_per_zone
  }

  update_config {
    max_unavailable_percentage = 33
  }

  instance_types = var.node_instance_types

  launch_template {
    id      = aws_launch_template.node_group.id
    version = "$Latest"
  }

  labels = {
    Environment = var.environment
    Zone        = var.availability_zones[count.index]
    NodeGroup   = "${var.cluster_name}-ng-${var.availability_zones[count.index]}"
  }

  tags = merge(
    local.common_tags,
    {
      Name                                                    = "${var.cluster_name}-ng-${var.availability_zones[count.index]}"
      "k8s.io/cluster-autoscaler/${var.cluster_name}"        = "owned"
      "k8s.io/cluster-autoscaler/enabled"                    = "true"
    }
  )

  depends_on = [
    aws_iam_role_policy_attachment.node_group_worker,
    aws_iam_role_policy_attachment.node_group_cni,
    aws_iam_role_policy_attachment.node_group_registry,
  ]

  lifecycle {
    ignore_changes        = [scaling_config[0].desired_size]
    create_before_destroy = true
  }
}

# OIDC Provider para IRSA (IAM Roles for Service Accounts)
data "tls_certificate" "cluster" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "cluster" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.cluster.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer

  tags = merge(
    local.common_tags,
    {
      Name = "${var.cluster_name}-oidc"
    }
  )
}

# IAM Role para Cluster Autoscaler
resource "aws_iam_role" "cluster_autoscaler" {
  count = var.enable_cluster_autoscaler ? 1 : 0
  name  = "${var.cluster_name}-cluster-autoscaler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.cluster.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:sub" = "system:serviceaccount:kube-system:cluster-autoscaler"
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Política para Cluster Autoscaler
resource "aws_iam_role_policy" "cluster_autoscaler" {
  count = var.enable_cluster_autoscaler ? 1 : 0
  name  = "${var.cluster_name}-cluster-autoscaler"
  role  = aws_iam_role.cluster_autoscaler[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeScalingActivities",
          "eks:DescribeNodegroup"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup"
        ]
        Resource = "arn:aws:autoscaling:*:*:autoScalingGroup:*:autoScalingGroupName/eks-${var.cluster_name}-*"
      }
    ]
  })
}

# IAM Role para AWS Load Balancer Controller
resource "aws_iam_role" "load_balancer_controller" {
  count = var.enable_load_balancer_controller ? 1 : 0
  name  = "${var.cluster_name}-load-balancer-controller"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.cluster.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Política para Load Balancer Controller com permissões mínimas
resource "aws_iam_role_policy" "load_balancer_controller" {
  count = var.enable_load_balancer_controller ? 1 : 0
  name  = "${var.cluster_name}-load-balancer-controller"
  role  = aws_iam_role.load_balancer_controller[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "iam:CreateServiceLinkedRole",
          "ec2:DescribeAccountAttributes",
          "ec2:DescribeAddresses",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeInternetGateways",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeInstances",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeTags",
          "ec2:CreateSecurityGroup",
          "ec2:CreateTags",
          "ec2:DeleteTags",
          "ec2:DeleteSecurityGroup",
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:RevokeSecurityGroupIngress",
          "ec2:AuthorizeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupEgress",
          "ec2:CreateSecurityGroup",
          "elasticloadbalancing:*",
          "acm:ListCertificates",
          "acm:DescribeCertificate",
          "iam:ListServerCertificates",
          "iam:GetServerCertificate",
          "cognito-idp:DescribeUserPoolClient",
          "wafv2:GetWebACL",
          "wafv2:GetWebACLForResource",
          "wafv2:AssociateWebACL",
          "wafv2:DisassociateWebACL",
          "shield:DescribeProtection",
          "shield:GetSubscriptionState",
          "shield:DeleteProtection",
          "shield:CreateProtection",
          "shield:DescribeSubscription",
          "shield:ListProtections"
        ]
        Resource = "*"
      }
    ]
  })
}

# ConfigMap aws-auth para permitir que nodes se juntem ao cluster
resource "kubernetes_config_map" "aws_auth" {
  metadata {
    name      = "aws-auth"
    namespace = "kube-system"
  }

  data = {
    mapRoles = yamlencode(concat(
      [
        {
          rolearn  = aws_iam_role.node_group.arn
          username = "system:node:{{EC2PrivateDNSName}}"
          groups   = ["system:bootstrappers", "system:nodes"]
        }
      ],
      var.map_roles
    ))
    mapUsers = yamlencode(var.map_users)
  }

  depends_on = [aws_eks_cluster.main]
}

# IAM Role para EBS CSI Driver
resource "aws_iam_role" "ebs_csi_driver" {
  name = "${var.cluster_name}-ebs-csi-driver"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.cluster.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Política para EBS CSI Driver
resource "aws_iam_role_policy_attachment" "ebs_csi_driver" {
  role       = aws_iam_role.ebs_csi_driver.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# Addon EBS CSI Driver
resource "aws_eks_addon" "ebs_csi_driver" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "aws-ebs-csi-driver"
  addon_version            = "v1.33.0-eksbuild.1"
  service_account_role_arn = aws_iam_role.ebs_csi_driver.arn
  resolve_conflicts_on_update = "OVERWRITE"

  tags = merge(
    local.common_tags,
    {
      Name = "${var.cluster_name}-ebs-csi-driver"
    }
  )

  depends_on = [
    aws_eks_node_group.main,
    aws_iam_role_policy_attachment.ebs_csi_driver
  ]
}