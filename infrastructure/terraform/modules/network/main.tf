# Network Module - Neural Hive-Mind Phase 1
# Multi-zone VPC with public/private subnets for high availability

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    external = {
      source  = "hashicorp/external"
      version = "~> 2.0"
    }
  }
}

locals {
  common_tags = merge(
    var.tags,
    {
      Module      = "network"
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "neural-hive-mind"
    }
  )
}

# Validações locais para CIDRs
locals {
  all_subnets = concat(var.public_subnet_cidrs, var.private_subnet_cidrs)
}

# Validação externa robusta de CIDRs usando script Python
# Verifica contenção no VPC e sobreposições entre subnets
# Requer python3 com módulo ipaddress (padrão desde Python 3.3)
# Para ambientes sem Python, pule com: terraform apply -target=aws_vpc.main
data "external" "cidr_validation" {
  program = ["python3", "${path.module}/scripts/cidr_validate.py"]
  query = {
    vpc_cidr = var.vpc_cidr
    subnets  = jsonencode(local.all_subnets)
  }
}

# Main VPC
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-vpc"
      Type = "main"
    }
  )

  lifecycle {
    precondition {
      condition     = data.external.cidr_validation.result.contains == "true"
      error_message = "Todos os subnets devem estar contidos em vpc_cidr."
    }
    precondition {
      condition     = data.external.cidr_validation.result.overlap == "false"
      error_message = "Subnets não devem se sobrepor."
    }
  }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-igw"
    }
  )
}

# Elastic IPs for NAT Gateways
resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? length(var.availability_zones) : 0
  domain = "vpc"

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-eip-${var.availability_zones[count.index]}"
      Zone = var.availability_zones[count.index]
    }
  )

  depends_on = [aws_internet_gateway.main]
}

# Public Subnets - One per AZ
resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = merge(
    local.common_tags,
    {
      Name                                                                                   = "${var.name_prefix}-public-${var.availability_zones[count.index]}"
      Type                                                                                   = "public"
      "kubernetes.io/cluster/${var.cluster_name != "" ? var.cluster_name : var.name_prefix}" = "shared"
      "kubernetes.io/role/elb"                                                               = "1"
    }
  )
}

# Private Subnets - One per AZ
resource "aws_subnet" "private" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(
    local.common_tags,
    {
      Name                                                                                   = "${var.name_prefix}-private-${var.availability_zones[count.index]}"
      Type                                                                                   = "private"
      "kubernetes.io/cluster/${var.cluster_name != "" ? var.cluster_name : var.name_prefix}" = "shared"
      "kubernetes.io/role/internal-elb"                                                      = "1"
    }
  )
}

# NAT Gateways - One per AZ for high availability
resource "aws_nat_gateway" "main" {
  count         = var.enable_nat_gateway ? length(var.availability_zones) : 0
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-nat-${var.availability_zones[count.index]}"
      Zone = var.availability_zones[count.index]
    }
  )

  depends_on = [aws_internet_gateway.main]
}

# Public Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-public-rt"
      Type = "public"
    }
  )
}

# Private Route Tables - One per AZ
resource "aws_route_table" "private" {
  count  = length(var.availability_zones)
  vpc_id = aws_vpc.main.id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-private-rt-${var.availability_zones[count.index]}"
      Type = "private"
      Zone = var.availability_zones[count.index]
    }
  )
}

# Private Routes to NAT Gateways
resource "aws_route" "private_nat" {
  count                  = var.enable_nat_gateway ? length(var.availability_zones) : 0
  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[count.index].id
}

# Associate public subnets with public route table
resource "aws_route_table_association" "public" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Associate private subnets with private route tables
resource "aws_route_table_association" "private" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# Security Group for internal cluster communication
resource "aws_security_group" "cluster_internal" {
  name_prefix = "${var.name_prefix}-cluster-internal"
  description = "Security group for internal cluster communication"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Allow all internal VPC traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-cluster-internal-sg"
    }
  )
}

# VPC Flow Logs for security and compliance
resource "aws_flow_log" "main" {
  count = var.enable_flow_logs ? 1 : 0

  iam_role_arn        = aws_iam_role.flow_logs[0].arn
  log_destination_arn = aws_cloudwatch_log_group.flow_logs[0].arn
  traffic_type        = "ALL"
  vpc_id              = aws_vpc.main.id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-flow-logs"
    }
  )
}

# CloudWatch Log Group for VPC Flow Logs
resource "aws_cloudwatch_log_group" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  name              = "/aws/vpc/${var.name_prefix}"
  retention_in_days = var.flow_logs_retention_days

  tags = local.common_tags
}

# IAM Role for VPC Flow Logs
resource "aws_iam_role" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  name_prefix = "${var.name_prefix}-flow-logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "vpc-flow-logs.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# IAM Policy for VPC Flow Logs
resource "aws_iam_role_policy" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  role = aws_iam_role.flow_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:log-group:/aws/vpc/${var.name_prefix}:*"
      }
    ]
  })
}

# VPC Endpoints for AWS Services (reduces data transfer costs and improves security)
resource "aws_vpc_endpoint" "s3" {
  count = var.enable_vpc_endpoints ? 1 : 0

  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-s3-endpoint"
    }
  )
}

resource "aws_vpc_endpoint" "ecr_api" {
  count = var.enable_vpc_endpoints ? 1 : 0

  vpc_id             = aws_vpc.main.id
  service_name       = "com.amazonaws.${data.aws_region.current.name}.ecr.api"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.vpc_endpoints[0].id]

  private_dns_enabled = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-ecr-api-endpoint"
    }
  )
}

resource "aws_vpc_endpoint" "ecr_dkr" {
  count = var.enable_vpc_endpoints ? 1 : 0

  vpc_id             = aws_vpc.main.id
  service_name       = "com.amazonaws.${data.aws_region.current.name}.ecr.dkr"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.vpc_endpoints[0].id]

  private_dns_enabled = true

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-ecr-dkr-endpoint"
    }
  )
}

# Security Group for VPC Endpoints
resource "aws_security_group" "vpc_endpoints" {
  count = var.enable_vpc_endpoints ? 1 : 0

  name_prefix = "${var.name_prefix}-vpc-endpoints"
  description = "Security group for VPC endpoints - restrito a subnets privadas"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Allow HTTPS from private subnets only"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.private_subnet_cidrs
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name_prefix}-vpc-endpoints-sg"
    }
  )
}

# Data source for current AWS region
data "aws_region" "current" {}