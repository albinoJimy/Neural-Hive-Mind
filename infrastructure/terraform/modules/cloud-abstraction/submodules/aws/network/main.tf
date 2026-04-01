# AWS Network Submodule
# Adapter entre abstração genérica e módulos AWS existentes

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Usar módulo AWS existente
module "vpc" {
  source = "../../../../../../network"

  name_prefix      = "neural-hive-${var.environment}"
  environment      = var.environment
  tags             = var.tags

  vpc_cidr              = var.vpc_cidr
  availability_zones    = var.availability_zones

  # Subnets calculadas a partir do VPC CIDR
  public_subnet_cidrs   = cidrsubnets(var.vpc_cidr, 8, 1)
  private_subnet_cidrs  = cidrsubnets(var.vpc_cidr, 8, 2)

  enable_nat_gateway     = var.environment == "prod"
  enable_vpc_endpoints   = true
  enable_flow_logs      = var.environment == "prod"
}

# Outputs compatíveis com interface genérica
