# =============================================================================
# Neural Hive-Mind - ElastiCache Redis Multi-Region Module
# =============================================================================
# Configura ElastiCache Redis com Global Datastore para multi-região
# =============================================================================

# -----------------------------------------------------------------------------
# Random Password Generation
# -----------------------------------------------------------------------------

resource "random_password" "auth_token" {
  length  = 64
  special = false
}

# -----------------------------------------------------------------------------
# Security Group
# -----------------------------------------------------------------------------

resource "aws_security_group" "redis" {
  name_prefix = "${var.cluster_name}-"
  description = "Security group for ElastiCache Redis cluster"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from VPC CIDRs"
    from_port       = var.port
    to_port         = var.port
    protocol        = "tcp"
    security_groups = var.allowed_security_groups
  }

  ingress {
    description = "Redis from peered VPCs"
    from_port   = var.port
    to_port     = var.port
    protocol    = "tcp"
    cidr_blocks = var.peered_vpc_cidrs
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.cluster_name}-sg"
    }
  )

  lifecycle {
    create_before_destroy = true
  }
}

# -----------------------------------------------------------------------------
# Parameter Group
# -----------------------------------------------------------------------------

resource "aws_elasticache_parameter_group" "this" {
  name        = "${var.cluster_name}-pg"
  family      = var.parameter_group_family
  description = "Parameter group for Neural Hive-Mind Redis cluster"

  dynamic "parameter" {
    for_each = var.parameter_group_parameters
    content {
      name  = parameter.value.name
      value = parameter.value.value
    }
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Subnet Group
# -----------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "this" {
  name        = "${var.cluster_name}-subnet-group"
  description = "Subnet group for Neural Hive-Mind Redis cluster"
  subnet_ids  = var.subnet_ids

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Replication Group (Primary Cluster)
# -----------------------------------------------------------------------------

resource "aws_elasticache_replication_group" "primary" {
  replication_group_id          = var.cluster_name
  replication_group_description = "Neural Hive-Mind Redis cluster - Primary"
  node_type                     = var.node_type

  engine               = "redis"
  engine_version       = var.engine_version
  port                 = var.port
  parameter_group_name = aws_elasticache_parameter_group.this.name
  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = [aws_security_group.redis.id]

  # Number of nodes
  num_cache_clusters         = var.num_cache_nodes
  automatic_failover_enabled = var.automatic_failover_enabled
  multi_az_enabled           = var.multi_az_enabled

  # Snapshots
  snapshot_window            = var.snapshot_window
  snapshot_retention_limit   = var.snapshot_retention_limit
  automatic_backup_retention = var.snapshot_retention_limit

  # Maintenance
  maintenance_window = var.maintenance_window
  apply_immediately  = false

  # Authentication
  auth_token                 = var.auth_token != null ? var.auth_token : random_password.auth_token.result
  transit_encryption_enabled = var.transit_encryption_enabled
  at_rest_encryption_enabled = var.at_rest_encryption_enabled

  # Cluster mode
  cluster_mode_enabled    = var.cluster_mode_enabled
  num_node_groups         = var.cluster_mode_enabled ? var.shard_count : null
  replicas_per_node_group = var.cluster_mode_enabled ? var.replicas_per_shard : var.replicas_per_node

  # Global Datastore (Multi-region)
  global_replication_group_id = var.global_replication_enabled ? aws_elasticache_global_replication_group.this[0].global_replication_group_id : null

  # Notifications
  notification_topic_arn = var.notification_topic_arn

  # Tags
  tags = merge(
    var.tags,
    {
      RegionRole = "primary"
    }
  )

  lifecycle {
    ignore_changes = [
      num_cache_clusters,
      engine_version
    ]
  }
}

# -----------------------------------------------------------------------------
# Global Replication Group (Multi-region primary)
# -----------------------------------------------------------------------------

resource "aws_elasticache_global_replication_group" "this" {
  count = var.global_replication_enabled ? 1 : 0

  global_replication_group_id          = "${var.cluster_name}-global"
  global_replication_group_description = "Neural Hive-Mind Global Redis"

  primary_replication_group_id = aws_elasticache_replication_group.primary.id

  # Cache node type
  cache_node_type = var.node_type

  # Engine
  engine         = "redis"
  engine_version = var.engine_version

  # Automatic failover
  automatic_failover_enabled = true

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Secondary Replication Groups (for other regions)
# -----------------------------------------------------------------------------

# Este recurso deve ser criado nas regiões secundárias
# usando o global_replication_group_id primário

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "cluster_id" {
  description = "ID do cluster Redis"
  value       = aws_elasticache_replication_group.primary.id
}

output "primary_endpoint" {
  description = "Endpoint primário do cluster"
  value       = aws_elasticache_replication_group.primary.primary_endpoint_address
  sensitive   = true
}

output "primary_port" {
  description = "Porta primária do cluster"
  value       = var.port
}

output "reader_endpoint" {
  description = "Endpoint de leitura (read replicas)"
  value       = aws_elasticache_replication_group.primary.reader_endpoint_address
  sensitive   = true
}

output "global_replication_group_id" {
  description = "ID do Global Replication Group (multi-region)"
  value       = var.global_replication_enabled ? aws_elasticache_global_replication_group.this[0].global_replication_group_id : null
}

output "auth_token" {
  description = "Token de autenticação"
  value       = var.auth_token != null ? var.auth_token : random_password.auth_token.result
  sensitive   = true
}

output "cluster_size" {
  description = "Número de nós no cluster"
  value       = var.num_cache_nodes * (1 + var.replicas_per_node)
}

output "configuration_endpoint" {
  description = "Endpoint de configuração (para cluster mode)"
  value       = aws_elasticache_replication_group.primary.configuration_endpoint_address
  sensitive   = true
}
