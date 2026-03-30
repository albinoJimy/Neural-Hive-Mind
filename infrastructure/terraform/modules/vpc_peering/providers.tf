# =============================================================================
# Neural Hive-Mind - VPC Peering Providers
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Provider para a região solicitante
provider "aws" {
  alias  = "requester"
  region = var.requester_region
}

# Provider para a região aceptora
provider "aws" {
  alias  = "accepter"
  region = var.accepter_region
}
