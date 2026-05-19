# =============================================================================
# Neural Hive-Mind - MongoDB Outputs
# =============================================================================

output "project_id" {
  description = "MongoDB Atlas Project ID"
  value       = mongodbatlas_project.this.id
}

output "cluster_id" {
  description = "MongoDB Atlas Cluster ID"
  value       = mongodbatlas_advanced_cluster.this.id
}

output "cluster_name" {
  description = "Nome do cluster"
  value       = mongodbatlas_advanced_cluster.this.name
}

output "connection_string" {
  description = "Standard connection string (public)"
  value       = mongodbatlas_advanced_cluster.this.connection_strings[0].standard_srv
  sensitive   = true
}

output "connection_string_private" {
  description = "Private connection string (via VPC peering)"
  value       = mongodbatlas_advanced_cluster.this.connection_strings[0].private_srv
  sensitive   = true
}

output "connection_strings" {
  description = "Todas as connection strings"
  value       = mongodbatlas_advanced_cluster.this.connection_strings
  sensitive   = true
}

output "admin_username" {
  description = "Admin username"
  value       = mongodbatlas_database_user.admin.username
}

output "app_username" {
  description = "App username"
  value       = mongodbatlas_database_user.app.username
}

output "replica_set_name" {
  description = "Nome do replica set"
  value       = mongodbatlas_advanced_cluster.this.replica_set_name
}

output "connection_strings_private_endpoint" {
  description = "Connection strings para private endpoint"
  value       = try(mongodbatlas_advanced_cluster.this.connection_strings[0].private_endpoint_srv, {})
  sensitive   = true
}

output "peering_ids" {
  description = "IDs dos peerings de rede"
  value = {
    east = try(mongodbatlas_network_peering.east[0].id, null)
    west = try(mongodbatlas_network_peering.west[0].id, null)
    eu   = try(mongodbatlas_network_peering.eu[0].id, null)
  }
}
