# =============================================================================
# Neural Hive-Mind - Produção EU West 1 (Região Terciária)
# =============================================================================
# Esta é a região terciária que hospeda:
# - Cluster EKS terciário (disaster recovery europeu)
# - MongoDB Secondary
# - Redis Secondary
# - Serviços com compliance GDPR
# =============================================================================

terraform {
  backend "s3" {
    bucket         = "neural-hive-mind-terraform-state"
    key            = "environments/prod-eu-west-1/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "neural-hive-mind-terraform-locks"
  }

  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# Provider Configuration
# -----------------------------------------------------------------------------

provider "aws" {
  region = "eu-west-1"

  default_tags {
    tags = {
      Project     = "neural-hive-mind"
      Environment = "production"
      Region      = "eu-west-1"
      RegionRole  = "tertiary"
      ManagedBy   = "terraform"
      Compliance  = "GDPR"
    }
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# VPC Module - Região Terciária
# -----------------------------------------------------------------------------

module "vpc" {
  source = "../../../modules/vpc"

  name_prefix = "nhm-prod-eu"
  environment = "production"
  region      = "eu-west-1"

  cidr = "10.2.0.0/16"

  availability_zones = [
    "eu-west-1a",
    "eu-west-1b",
    "eu-west-1c"
  ]

  public_subnet_cidrs = [
    "10.2.1.0/24",
    "10.2.2.0/24",
    "10.2.3.0/24"
  ]

  private_subnet_cidrs = [
    "10.2.11.0/24",
    "10.2.12.0/24",
    "10.2.13.0/24"
  ]

  database_subnet_cidrs = [
    "10.2.21.0/24",
    "10.2.22.0/24",
    "10.2.23.0/24"
  ]

  enable_nat_gateway   = true
  enable_vpc_endpoints = true
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    RegionRole = "tertiary"
    Compliance = "GDPR"
  }
}

# -----------------------------------------------------------------------------
# EKS Cluster - Região Terciária
# -----------------------------------------------------------------------------

module "kubernetes_cluster" {
  source = "../../../modules/kubernetes-cluster"

  cluster_name = "neural-hive-eu"
  environment  = "production"
  region       = "eu-west-1"

  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids

  kubernetes_version = "1.29"

  # Node Pools (menor capacidade, foco em compliance)
  node_pools = {
    general = {
      min_size       = 2
      max_size       = 5
      desired_size   = 2
      instance_types = ["t3.xlarge"]
      capacity_type  = "ON_DEMAND"
      disk_size_gb   = 100
      labels = {
        pool = "general"
      }
    }

    compliance = {
      min_size       = 1
      max_size       = 3
      desired_size   = 1
      instance_types = ["t3.large"]
      capacity_type  = "ON_DEMAND"
      disk_size_gb   = 80
      labels = {
        pool = "compliance"
      }
    }
  }

  enable_private_endpoint = true
  enable_public_endpoint  = true

  public_access_cidrs = [
    "0.0.0.0/0"
  ]

  enable_cluster_autoscaler       = true
  enable_load_balancer_controller = true

  tags = {
    RegionRole = "tertiary"
    Compliance = "GDPR"
  }
}

# -----------------------------------------------------------------------------
# VPC Peering Connection (aceita peering do East)
# -----------------------------------------------------------------------------

module "vpc_peering_east" {
  source = "../../../modules/vpc_peering"

  requester_vpc_id = var.vpc_peer_ids["us-east-1"]
  requester_region = "us-east-1"

  accepter_vpc_id  = module.vpc.vpc_id
  accepter_region  = "eu-west-1"
  accepter_account = data.aws_caller_identity.current.account_id

  auto_accept = true

  tags = {
    Name        = "nhm-east-eu-peering"
    Description = "Peering between us-east-1 and eu-west-1"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "region" {
  description = "Região AWS"
  value       = "eu-west-1"
}

output "region_role" {
  description = "Papel da região"
  value       = "tertiary"
}

output "vpc_id" {
  description = "ID da VPC"
  value       = module.vpc.vpc_id
}

output "cluster_name" {
  description = "Nome do cluster EKS"
  value       = module.kubernetes_cluster.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint do cluster EKS"
  value       = module.kubernetes_cluster.api_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Certificado CA do cluster"
  value       = module.kubernetes_cluster.certificate_authority_data
  sensitive   = true
}

output "private_subnet_ids" {
  description = "IDs das subnets privadas"
  value       = module.vpc.private_subnet_ids
}

output "compliance_tag" {
  description = "Tag de compliance GDPR"
  value       = "GDPR"
}
