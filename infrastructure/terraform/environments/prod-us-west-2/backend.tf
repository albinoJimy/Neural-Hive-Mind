# =============================================================================
# Neural Hive-Mind - Terraform Backend Configuration
# =============================================================================

terraform {
  backend "s3" {
    # Bucket compartilhado para todas as regiões
    bucket = "neural-hive-mind-terraform-state"

    # Key único para esta região
    key = "environments/prod-us-west-2/terraform.tfstate"

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
