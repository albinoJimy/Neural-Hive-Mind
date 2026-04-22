# AWS Cluster Submodule
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
module "eks" {
  source = "../../../../../../k8s-cluster"

  environment = var.environment
  tags        = var.tags

  # Rede
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  public_subnet_ids  = var.public_subnet_ids
  availability_zones = var.availability_zones

  # Cluster
  cluster_name            = var.cluster_name
  kubernetes_version      = var.kubernetes_version
  enable_private_endpoint = var.enable_private_endpoint
  enable_public_endpoint  = !var.enable_private_endpoint
  public_access_cidrs     = var.enable_private_endpoint ? [] : ["0.0.0.0/0"]

  # Nós
  node_instance_types    = var.node_instance_types
  min_nodes_per_zone     = var.min_nodes_per_zone
  max_nodes_per_zone     = var.max_nodes_per_zone
  desired_nodes_per_zone = var.desired_nodes_per_zone

  # Add-ons
  enable_cluster_autoscaler       = true
  enable_load_balancer_controller = true
}
