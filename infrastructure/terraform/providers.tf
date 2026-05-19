# Configuração dos Providers - Neural Hive-Mind
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
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

}

# Provider AWS
provider "aws" {
  region = var.aws_region != "" ? var.aws_region : "us-east-1"

  # Configurações de retry para maior robustez
  retry_mode  = "adaptive"
  max_retries = 3

  default_tags {
    tags = var.tags
  }
}

# Provider Kubernetes - configurado após criação do cluster
provider "kubernetes" {
  host = module.k8s-cluster.cluster_endpoint
  # Output real do módulo k8s-cluster é "cluster_certificate_authority"
  # (ver modules/k8s-cluster/outputs.tf:8); nome anterior causava
  # "Reference to undeclared attribute" em terraform validate.
  cluster_ca_certificate = base64decode(module.k8s-cluster.cluster_certificate_authority)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--cluster-name",
      module.k8s-cluster.cluster_name,
      "--region",
      var.aws_region
    ]
  }
}

# Provider Helm - configurado após criação do cluster
provider "helm" {
  kubernetes {
    host = module.k8s-cluster.cluster_endpoint
    # Output real do módulo k8s-cluster é "cluster_certificate_authority"
    # (ver modules/k8s-cluster/outputs.tf:8); nome anterior causava
    # "Reference to undeclared attribute" em terraform validate.
    cluster_ca_certificate = base64decode(module.k8s-cluster.cluster_certificate_authority)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = [
        "eks",
        "get-token",
        "--cluster-name",
        module.k8s-cluster.cluster_name,
        "--region",
        var.aws_region
      ]
    }
  }
}