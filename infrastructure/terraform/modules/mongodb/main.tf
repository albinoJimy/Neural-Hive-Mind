# =============================================================================
# Neural Hive-Mind - MongoDB Atlas Multi-Region Module
# =============================================================================
# Configura MongoDB Atlas com replica set multi-região
# =============================================================================

# -----------------------------------------------------------------------------
# MongoDB Atlas Project
# -----------------------------------------------------------------------------

resource "mongodbatlas_project" "this" {
  name   = var.project_name
  org_id = var.atlas_org_id

  tags = var.tags
}

# -----------------------------------------------------------------------------
# MongoDB Atlas Network Peering (VPC)
# -----------------------------------------------------------------------------

resource "mongodbatlas_network_peering" "east" {
  project_id    = mongodbatlas_project.this.id
  atlas_cidr_block = "192.168.0.0/24"

  provider_name = "AWS"
  region        = "US_EAST_1"

  # VPC peering connection com AWS
  aws_account_id    = var.aws_account_id
  vpc_id            = var.vpc_ids["us-east-1"]
  route_table_cidr  = var.vpc_cidrs["us-east-1"]
}

resource "mongodbatlas_network_peering" "west" {
  project_id    = mongodbatlas_project.this.id

  provider_name = "AWS"
  region        = "US_WEST_2"

  aws_account_id    = var.aws_account_id
  vpc_id            = var.vpc_ids["us-west-2"]
  route_table_cidr  = var.vpc_cidrs["us-west-2"]
}

resource "mongodbatlas_network_peering" "eu" {
  project_id    = mongodbatlas_project.this.id

  provider_name = "AWS"
  region        = "EU_WEST_1"

  aws_account_id    = var.aws_account_id
  vpc_id            = var.vpc_ids["eu-west-1"]
  route_table_cidr  = var.vpc_cidrs["eu-west-1"]
}

# -----------------------------------------------------------------------------
# MongoDB Atlas Advanced Cluster (Multi-Region)
# -----------------------------------------------------------------------------

resource "mongodbatlas_advanced_cluster" "this" {
  project_id   = mongodbatlas_project.this.id
  name         = var.cluster_name

  # Cluster Type
  cluster_type = "REPLICASET"

  # Backup Configuration
  backup_enabled = var.continuous_backup_enabled

  # Bi-Connector
  bi_connector = var.enable_bi_connector ? {
    enabled = var.enable_bi_connector
    read_preference = "secondary"
  } : null

  # Connector Configuration
  connector_config = var.enable_connector ? {
    enabled               = var.enable_connector
    connector_docker_img = var.connector_docker_image
  } : null

  # Labels
  labels = var.labels

  # Replication Specs (Multi-region configuration)
  replication_specs {
    region_name             = "US_EAST_1"
    num_shards              = var.num_shards
    zone_name               = "Zone 1"

    # Advanced configuration for US East
    auto_merging = {
      enabled = false
    }

    # Read preference
    read_prefs = [
      {
        region_name = "US_EAST_1"
      }
    ]

    # Write concern
    write_concern = {
      w        = "majority"
      j        = true
      wtimeout = 5000
    }

    # Nodes
    region_config {
      electable_specs {
        instance_size = var.members[0].node_type
        node_count    = 3
      }

      priority      = var.members[0].priority
      votes         = var.members[0].votes
      read_only     = var.members[0].read_only != null ? var.members[0].read_only : false
    }
  }

  replication_specs {
    region_name             = "US_WEST_2"
    num_shards              = var.num_shards
    zone_name               = "Zone 2"

    # Read preference
    read_prefs = [
      {
        region_name = "US_WEST_2"
      }
    ]

    # Nodes
    region_config {
      electable_specs {
        instance_size = var.members[1].node_type
        node_count    = 3
      }

      priority      = var.members[1].priority
      votes         = var.members[1].votes
      read_only     = var.members[1].read_only != null ? var.members[1].read_only : false
    }
  }

  replication_specs {
    region_name             = "EU_WEST_1"
    num_shards              = var.num_shards
    zone_name               = "Zone 3"

    # Read preference
    read_prefs = [
      {
        region_name = "EU_WEST_1"
      }
    ]

    # Nodes
    region_config {
      electable_specs {
        instance_size = var.members[2].node_type
        node_count    = 3
      }

      priority      = var.members[2].priority
      votes         = var.members[2].votes
      read_only     = var.members[2].read_only != null ? var.members[2].read_only : false
    }
  }

  # Retention
  retention_days = var.backup_retention_days

  # Auto-scaling
  auto_scaling = var.autoscale != null ? {
    compute = {
      enabled          = var.autoscale.compute_enabled != null ? var.autoscale.compute_enabled : true
      scale_down_enabled = true
      min_instance_size = var.members[0].node_type
      max_instance_size = "M80"
    }
    disk_gb_enabled = var.autoscale.disk_gb_enabled != null ? var.autoscale.disk_gb_enabled : true
  } : null

  # Encryption
  encryption_at_rest_provider = "AWS"

  # Version
  version_release_system = "LATEST"

  # Tags
  tags = var.tags
}

# -----------------------------------------------------------------------------
# MongoDB Atlas Database Users
# -----------------------------------------------------------------------------

resource "mongodbatlas_database_user" "admin" {
  username           = "nhm-admin"
  password           = var.admin_password
  project_id         = mongodbatlas_project.this.id
  auth_database_name = "admin"

  scopes {
    name = "admin"
    type = "CLUSTER"
  }

  roles {
    name     = "atlasAdmin"
    database = "admin"
  }
}

resource "mongodbatlas_database_user" "app" {
  username           = "nhm-app"
  password           = var.app_password
  project_id         = mongodbatlas_project.this.id
  auth_database_name = "admin"

  scopes {
    name = "admin"
    type = "CLUSTER"
  }

  roles {
    name     = "readWrite"
    database = "neural_hive_mind"
  }

  roles {
    name     = "readAnyDatabase"
    database = "admin"
  }
}

# -----------------------------------------------------------------------------
# MongoDB Atlas Private Link (Optional)
# -----------------------------------------------------------------------------

resource "mongodbatlas_private_endpoint" "east" {
  count              = var.enable_private_link ? 1 : 0
  project_id         = mongodbatlas_project.this.id
  cluster_name       = mongodbatlas_advanced_cluster.this.name
  provider_name      = "AWS"
  region             = "US_EAST_1"

  private_endpoint_ip_address = var.private_endpoint_ips["us-east-1"]
}

# -----------------------------------------------------------------------------
# MongoDB Atlas Access List
# -----------------------------------------------------------------------------

resource "mongodbatlas_project_ip_access_list" "security_group" {
  project_id = mongodbatlas_project.this.id
  cidr_block = var.vpc_cidrs["us-east-1"]
  comment    = "US East Security Group"
}

resource "mongodbatlas_project_ip_access_list" "security_group_west" {
  project_id = mongodbatlas_project.this.id
  cidr_block = var.vpc_cidrs["us-west-2"]
  comment    = "US West Security Group"
}

resource "mongodbatlas_project_ip_access_list" "security_group_eu" {
  project_id = mongodbatlas_project.this.id
  cidr_block = var.vpc_cidrs["eu-west-1"]
  comment    = "EU Security Group"
}

# -----------------------------------------------------------------------------
# MongoDB Atlas Auditing
# -----------------------------------------------------------------------------

resource "mongodbatlas_auditing" "this" {
  count      = var.enable_auditing ? 1 : 0
  project_id = mongodbatlas_project.this.id

  audit_filter           = var.audit_filter
  audit_authorization_success = true
  enabled                = true
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "project_id" {
  description = "MongoDB Atlas Project ID"
  value       = mongodbatlas_project.this.id
}

output "cluster_id" {
  description = "MongoDB Atlas Cluster ID"
  value       = mongodbatlas_advanced_cluster.this.id
}

output "connection_string" {
  description = "Standard connection string"
  value       = mongodbatlas_advanced_cluster.this.connection_strings[0].standard_srv
  sensitive   = true
}

output "connection_string_private" {
  description = "Private connection string (via VPC peering)"
  value       = mongodbatlas_advanced_cluster.this.connection_strings[0].private_srv
  sensitive   = true
}

output "admin_username" {
  description = "Admin username"
  value       = mongodbatlas_database_user.admin.username
  sensitive   = true
}

output "app_username" {
  description = "App username"
  value       = mongodbatlas_database_user.app.username
  sensitive   = true
}
