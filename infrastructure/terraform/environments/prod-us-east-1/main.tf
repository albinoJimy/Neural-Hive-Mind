# =============================================================================
# Neural Hive-Mind - Produção US East 1 (Região Primária)
# =============================================================================
# Esta é a região primária que hospeda:
# - Cluster EKS principal
# - MongoDB Primary
# - Redis Primary
# - Route53 Hosted Zone principal
# =============================================================================

terraform {
  source = "../../../modules/vpc"
  region = "us-east-1"
  cidr = "10.0.0.0/16"
}

# -----------------------------------------------------------------------------
# Provider Configuration
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
# Remote State Backend
# -----------------------------------------------------------------------------

terraform {
  backend "s3" {
    bucket         = "neural-hive-mind-terraform-state"
    key            = "environments/prod-us-east-1/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "neural-hive-mind-terraform-locks"
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# VPC Module - Região Primária
# -----------------------------------------------------------------------------

module "vpc" {
  source = "../../../modules/vpc"

  name_prefix = "nhm-prod-east"
  environment = "production"
  region      = "us-east-1"

  cidr = "10.0.0.0/16"

  availability_zones = [
    "us-east-1a",
    "us-east-1b",
    "us-east-1c"
  ]

  public_subnet_cidrs = [
    "10.0.1.0/24",
    "10.0.2.0/24",
    "10.0.3.0/24"
  ]

  private_subnet_cidrs = [
    "10.0.11.0/24",
    "10.0.12.0/24",
    "10.0.13.0/24"
  ]

  database_subnet_cidrs = [
    "10.0.21.0/24",
    "10.0.22.0/24",
    "10.0.23.0/24"
  ]

  enable_nat_gateway        = true
  enable_vpc_endpoints      = true
  enable_dns_hostnames      = true
  enable_dns_support        = true

  tags = {
    RegionRole = "primary"
  }
}

# -----------------------------------------------------------------------------
# EKS Cluster - Região Primária
# -----------------------------------------------------------------------------

module "kubernetes_cluster" {
  source = "../../../modules/kubernetes-cluster"

  cluster_name = "neural-hive-east"
  environment  = "production"
  region       = "us-east-1"

  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids

  kubernetes_version = "1.29"

  # Node Pools
  node_pools = {
    general = {
      min_size       = 3
      max_size       = 10
      desired_size   = 3
      instance_types = ["t3.xlarge"]
      capacity_type  = "ON_DEMAND"
      disk_size_gb   = 100
      labels = {
        pool = "general"
      }
    }

    compute_intensive = {
      min_size       = 2
      max_size       = 5
      desired_size   = 2
      instance_types = ["c5.2xlarge"]
      capacity_type  = "SPOT"
      disk_size_gb   = 150
      labels = {
        pool = "compute-intensive"
      }
    }

    ml_workers = {
      min_size       = 1
      max_size       = 3
      desired_size   = 1
      instance_types = ["g4dn.xlarge"]
      capacity_type  = "SPOT"
      disk_size_gb   = 200
      labels = {
        pool = "ml-workers"
      }
    }
  }

  enable_private_endpoint = true
  enable_public_endpoint  = true

  public_access_cidrs = [
    "0.0.0.0/0"  # Restrito via Security Groups
  ]

  enable_cluster_autoscaler      = true
  enable_load_balancer_controller = true

  tags = {
    RegionRole = "primary"
  }
}

# -----------------------------------------------------------------------------
# VPC Peering Connections
# -----------------------------------------------------------------------------

# Peering com US West 2
module "vpc_peering_west" {
  source = "../../../modules/vpc_peering"

  requester_vpc_id = module.vpc.vpc_id
  requester_region = "us-east-1"

  accepter_vpc_id  = var.vpc_peer_ids["us-west-2"]
  accepter_region  = "us-west-2"
  accepter_account = data.aws_caller_identity.current.account_id

  auto_accept = false

  tags = {
    Name        = "nhm-east-west-peering"
    Description = "Peering between us-east-1 and us-west-2"
  }
}

# Peering com EU West 1
module "vpc_peering_eu" {
  source = "../../../modules/vpc_peering"

  requester_vpc_id = module.vpc.vpc_id
  requester_region = "us-east-1"

  accepter_vpc_id  = var.vpc_peer_ids["eu-west-1"]
  accepter_region  = "eu-west-1"
  accepter_account = data.aws_caller_identity.current.account_id

  auto_accept = false

  tags = {
    Name        = "nhm-east-eu-peering"
    Description = "Peering between us-east-1 and eu-west-1"
  }
}

# -----------------------------------------------------------------------------
# Route53 Hosted Zone (Global DNS)
# -----------------------------------------------------------------------------

module "route53" {
  source = "../../../modules/route53"

  domain_name = var.domain_name

  # Records multi-região
  records = {
    "api" = {
      type        = "A"
      alias = {
        name                   = module.kubernetes_cluster.api_endpoint
        zone_id                = module.kubernetes_cluster.hosted_zone_id
        evaluate_target_health = true
      }
      health_check = true
      failover_routing = {
        primary_region    = "us-east-1"
        secondary_regions = ["us-west-2", "eu-west-1"]
      }
    }

    "api-west" = {
      type = "CNAME"
      records = [
        module.kubernetes_cluster_west.api_endpoint
      ]
      ttl          = 60
      health_check = true
    }

    "api-eu" = {
      type = "CNAME"
      records = [
        module.kubernetes_cluster_eu.api_endpoint
      ]
      ttl          = 60
      health_check = true
    }

    "grafana" = {
      type        = "A"
      alias = {
        name                   = module.kubernetes_cluster.ingress_endpoint
        zone_id                = module.kubernetes_cluster.hosted_zone_id
        evaluate_target_health = true
      }
      health_check = true
    }

    "mlflow" = {
      type        = "A"
      alias = {
        name                   = module.kubernetes_cluster.ingress_endpoint
        zone_id                = module.kubernetes_cluster.hosted_zone_id
        evaluate_target_health = true
      }
      health_check = false
    }
  }

  # Health Checks
  health_checks = {
    api_health = {
      fqdn              = "api.${var.domain_name}"
      port              = 443
      type              = "HTTPS"
      resource_path     = "/health"
      request_interval  = 30
      failure_threshold = 3
    }
  }

  tags = {
    RegionRole = "primary"
  }
}

# -----------------------------------------------------------------------------
# MongoDB Atlas - Replica Set (Primary)
# -----------------------------------------------------------------------------

module "mongodb_replica_set" {
  source = "../../../modules/mongodb"

  cluster_name = "neural-hive-prod"
  project_id   = var.atlas_project_id

  # Configuração multi-região
  primary_region = "US_EAST_1"

  secondary_regions = [
    "US_WEST_2",
    "EU_WEST_1"
  ]

  members = [
    {
      region      = "US_EAST_1"
      node_type   = "M50"
      priority    = 1
      electable   = true
      votes       = 1
    },
    {
      region      = "US_WEST_2"
      node_type   = "M50"
      priority    = 2
      electable   = true
      votes       = 1
    },
    {
      region      = "EU_WEST_1"
      node_type   = "M50"
      priority    = 3
      electable   = true
      votes       = 1
    }
  ]

  # Configurações avançadas
  replication_factor   = 3
  write_concern_majority = true
  read_concern          = "majority"
  connect_timeout_ms    = 10000
  max_time_ms           = 30000

  # Backup e restore
  continuous_backup_enabled = true
  backup_retention_days     = 30
  snapshot_retention_days   = 7

  # Performance
  cluster_type = "REPLICASET"
  disk_size_gb = 500
  autoscale = {
    disk_gb_enabled = true
    max_disk_size   = 1000
  }

  tags = {
    RegionRole = "primary"
  }
}

# -----------------------------------------------------------------------------
# Redis Cluster - Primary
# -----------------------------------------------------------------------------

module "redis_cluster" {
  source = "../../../modules/redis"

  cluster_name      = "neural-hive-prod"
  node_type         = "cache.r6g.xlarge"
  engine_version    = "7.1"

  # Multi-AZ na região primária
  num_cache_nodes   = 3
  replicas_per_node = 1

  # Multi-region via Global Datastore
  global_replication_enabled = true
  primary_region             = "us-east-1"

  secondary_regions = [
    {
      region = "us-west-2"
      id     = var.redis_secondary_ids["us-west-2"]
    },
    {
      region = "eu-west-1"
      id     = var.redis_secondary_ids["eu-west-1"]
    }
  ]

  # Configurações
  port                      = 6379
  automatic_failover_enabled = true
  multi_az_enabled          = true

  # Parâmetros
  parameter_group_name = "default.redis7"
  parameter_group_parameters = [
    {
      name  = "maxmemory-policy"
      value = "allkeys-lru"
    },
    {
      name  = "timeout"
      value = "300"
    }
  ]

  # Security
  auth_token            = var.redis_auth_token
  transit_encryption    = true
  at_rest_encryption    = true

  # Maintenance
  maintenance_window = "sun:03:00-sun:04:00"
  snapshot_window    = "03:00-05:00"
  snapshot_retention = 7

  tags = {
    RegionRole = "primary"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "region" {
  description = "Região AWS"
  value       = "us-east-1"
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

output "mongodb_connection_string" {
  description = "String de conexão MongoDB (sensitive)"
  value       = module.mongodb_replica_set.connection_string
  sensitive   = true
}

output "redis_primary_endpoint" {
  description = "Endpoint Redis primário"
  value       = module.redis_cluster.primary_endpoint
  sensitive   = true
}

output "route53_zone_id" {
  description = "ID da hosted zone Route53"
  value       = module.route53.zone_id
}
