# =============================================================================
# Neural Hive-Mind - Terraform Backend Configuration
# =============================================================================

terraform {
  backend "s3" {
    # Bucket compartilhado para todas as regiões
    bucket = "neural-hive-mind-terraform-state"

    # Key único para esta região
    key = "environments/prod-eu-west-1/terraform.tfstate"

    # Região do bucket (us-east-1 para centralização)
    region = "us-east-1"

    # Criptografia do state
    encrypt = true

    # Lock table compartilhada
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
# Provider AWS
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
# Provider AWS Aliases para peering
# -----------------------------------------------------------------------------

provider "aws" {
  alias  = "east"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "neural-hive-mind"
      Environment = "production"
      Region      = "us-east-1"
      RegionRole  = "primary"
      ManagedBy   = "terraform"
    }
  }
}
