# =============================================================================
# Neural Hive-Mind - Produção US West 2 (Região Secundária)
# =============================================================================
# Esta é a região secundária que hospeda:
# - Cluster EKS secundário (disaster recovery)
# - MongoDB Secondary
# - Redis Secondary
# =============================================================================

terraform {
  backend "s3" {
    bucket         = "neural-hive-mind-terraform-state"
    key            = "environments/prod-us-west-2/terraform.tfstate"
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
  region = "us-west-2"

  default_tags {
    tags = {
      Project     = "neural-hive-mind"
      Environment = "production"
      Region      = "us-west-2"
      RegionRole  = "secondary"
      ManagedBy   = "terraform"
    }
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# VPC Module - Região Secundária
# -----------------------------------------------------------------------------

module "vpc" {
  source = "../../../modules/vpc"

  name_prefix = "nhm-prod-west"
  environment = "production"
  region      = "us-west-2"

  cidr = "10.1.0.0/16"

  availability_zones = [
    "us-west-2a",
    "us-west-2b",
    "us-west-2c"
  ]

  public_subnet_cidrs = [
    "10.1.1.0/24",
    "10.1.2.0/24",
    "10.1.3.0/24"
  ]

  private_subnet_cidrs = [
    "10.1.11.0/24",
    "10.1.12.0/24",
    "10.1.13.0/24"
  ]

  database_subnet_cidrs = [
    "10.1.21.0/24",
    "10.1.22.0/24",
    "10.1.23.0/24"
  ]

  enable_nat_gateway        = true
  enable_vpc_endpoints      = true
  enable_dns_hostnames      = true
  enable_dns_support        = true

  tags = {
    RegionRole = "secondary"
  }
}

# -----------------------------------------------------------------------------
# EKS Cluster - Região Secundária
# -----------------------------------------------------------------------------

module "kubernetes_cluster" {
  source = "../../../modules/kubernetes-cluster"

  cluster_name = "neural-hive-west"
  environment  = "production"
  region       = "us-west-2"

  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids

  kubernetes_version = "1.29"

  # Node Pools (menor capacidade que primária)
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

    compute_intensive = {
      min_size       = 1
      max_size       = 3
      desired_size   = 1
      instance_types = ["c5.2xlarge"]
      capacity_type  = "SPOT"
      disk_size_gb   = 150
      labels = {
        pool = "compute-intensive"
      }
    }
  }

  enable_private_endpoint = true
  enable_public_endpoint  = true

  public_access_cidrs = [
    "0.0.0.0/0"
  ]

  enable_cluster_autoscaler      = true
  enable_load_balancer_controller = true

  tags = {
    RegionRole = "secondary"
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
  accepter_region  = "us-west-2"
  accepter_account = data.aws_caller_identity.current.account_id

  auto_accept = true

  tags = {
    Name        = "nhm-east-west-peering"
    Description = "Peering between us-east-1 and us-west-2"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "region" {
  description = "Região AWS"
  value       = "us-west-2"
}

output "region_role" {
  description = "Papel da região"
  value       = "secondary"
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
