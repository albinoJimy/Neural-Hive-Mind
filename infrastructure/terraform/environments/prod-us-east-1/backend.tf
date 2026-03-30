# =============================================================================
# Neural Hive-Mind - Terraform Backend Configuration
# =============================================================================

terraform {
  backend "s3" {
    # Bucket para armazenar state files de todas as regiões
    bucket         = "neural-hive-mind-terraform-state"

    # Key único para esta região
    key            = "environments/prod-us-east-1/terraform.tfstate"

    # Região do bucket (us-east-1)
    region         = "us-east-1"

    # Criptografia do state
    encrypt        = true

    # Lock table para prevenção de conflitos
    dynamodb_table = "neural-hive-mind-terraform-locks"

    # Versionamento para rollback
    # (habilitado via AWS S3 Bucket Versioning)
  }

  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 1.15.0"
    }
  }
}

# -----------------------------------------------------------------------------
# Provider AWS
# -----------------------------------------------------------------------------

provider "aws" {
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

# -----------------------------------------------------------------------------
# Provider MongoDB Atlas
# -----------------------------------------------------------------------------

provider "mongodbatlas" {
  public_key  = var.atlas_public_key
  private_key = var.atlas_private_key
}
