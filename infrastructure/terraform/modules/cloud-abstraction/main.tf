# Cloud Abstraction Module - Neural Hive-Mind
#
# Este módulo implementa uma camada de abstração multi-cloud que permite
# deploy do Neural Hive-Mind em AWS, Azure ou GCP usando a mesma configuração.
#
# Arquitetura:
#   - Interface genérica para recursos (VPC, Cluster, Subnets)
#   - Implementações específicas por provider (aws/azure/gcp)
#   - Factory pattern para seleção dinâmica do provider

locals {
  # Mapeamento de regiões por provider
  region_map = {
    aws = {
      us-east-1    = "us-east-1"
      us-west-2    = "us-west-2"
      eu-west-1    = "eu-west-1"
      eu-central-1 = "eu-central-1"
    }
    azure = {
      us-east-1    = "eastus"
      us-west-2    = "westus2"
      eu-west-1    = "westeurope"
      eu-central-1 = "germanywestcentral"
    }
    gcp = {
      us-east-1    = "us-east1"
      us-west-2    = "us-west2"
      eu-west-1    = "europe-west1"
      eu-central-1 = "europe-central1"
    }
  }

  # Normalizar região baseada no provider
  normalized_region = lookup(
    local.region_map[var.cloud_provider],
    var.region,
    var.region
  )

  # Tags comuns
  common_tags = merge(
    var.tags,
    {
      Environment   = var.environment
      Project       = "neural-hive-mind"
      ManagedBy     = "terraform"
      CloudProvider = var.cloud_provider
    }
  )
}

# ============================================================================
# Factory Pattern - Seleciona módulo baseado no cloud_provider
# ============================================================================

module "cloud_network" {
  source = "./submodules/${var.cloud_provider}/network"

  environment        = var.environment
  region             = local.normalized_region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  tags               = local.common_tags

  # Parâmetros específicos por provider são mapeados no submodule
}

module "cloud_cluster" {
  source = "./submodules/${var.cloud_provider}/cluster"

  environment        = var.environment
  region             = local.normalized_region
  cluster_name       = var.cluster_name
  kubernetes_version = var.kubernetes_version

  # Rede
  vpc_id             = module.cloud_network.vpc_id
  private_subnet_ids = module.cloud_network.private_subnet_ids
  public_subnet_ids  = module.cloud_network.public_subnet_ids
  availability_zones = var.availability_zones

  # Configurações dos nós
  node_instance_types    = var.node_instance_types
  min_nodes_per_zone     = var.min_nodes_per_zone
  max_nodes_per_zone     = var.max_nodes_per_zone
  desired_nodes_per_zone = var.desired_nodes_per_zone

  # Configurações de acesso
  enable_private_endpoint = var.enable_private_cluster

  tags = local.common_tags
}

# ============================================================================
# Recursos pós-cluster (independentes de provider)
# ============================================================================

# Provider Kubernetes configurado dinamicamente
provider "kubernetes" {
  host                   = module.cloud_cluster.cluster_endpoint
  cluster_ca_certificate = base64decode(module.cloud_cluster.cluster_ca_certificate)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = var.cloud_provider == "aws" ? "aws" : var.cloud_provider == "azure" ? "az" : "gcloud"
    args = var.cloud_provider == "aws" ? [
      "eks",
      "get-token",
      "--cluster-name",
      module.cloud_cluster.cluster_name,
      "--region",
      local.normalized_region
      ] : var.cloud_provider == "azure" ? [
      "aks",
      "get-credentials",
      "--resource-group",
      "${var.cluster_name}-rg",
      "--name",
      module.cloud_cluster.cluster_name
      ] : [
      "container",
      "clusters",
      "get-credentials",
      module.cloud_cluster.cluster_name,
      "--region",
      local.normalized_region
    ]
  }
}

# Namespace principal
resource "kubernetes_namespace" "neural_hive" {
  metadata {
    name = var.environment == "prod" ? "neural-hive" : "neural-hive-${var.environment}"

    labels = {
      name        = "neural-hive"
      environment = var.environment
      project     = "neural-hive-mind"
    }
  }

  depends_on = [module.cloud_cluster]
}

# ConfigMap com informações do provider
resource "kubernetes_config_map" "cloud_info" {
  metadata {
    name      = "cloud-provider-info"
    namespace = kubernetes_namespace.neural_hive.metadata[0].name
  }

  data = {
    cloud_provider = var.cloud_provider
    region         = local.normalized_region
    cluster_name   = module.cloud_cluster.cluster_name
    cluster_id     = module.cloud_cluster.cluster_id
  }
}
