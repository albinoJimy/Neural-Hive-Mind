# =============================================================================
# Neural Hive-Mind - Redis Outputs
# =============================================================================

output "cluster_id" {
  description = "ID do cluster Redis"
  value       = aws_elasticache_replication_group.primary.id
}

output "cluster_name" {
  description = "Nome do cluster"
  value       = var.cluster_name
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

output "configuration_endpoint" {
  description = "Endpoint de configuração (cluster mode)"
  value       = aws_elasticache_replication_group.primary.configuration_endpoint_address
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
  description = "Número total de nós (primários + réplicas)"
  value       = var.cluster_mode_enabled ? var.shard_count * (1 + var.replicas_per_shard) : var.num_cache_nodes * (1 + var.replicas_per_node)
}

output "engine_version" {
  description = "Versão do Redis em uso"
  value       = var.engine_version
}

output "node_type" {
  description = "Tipo de nó"
  value       = var.node_type
}

output "security_group_id" {
  description = "ID do security group"
  value       = aws_security_group.redis.id
}

output "subnet_group_name" {
  description = "Nome do subnet group"
  value       = aws_elasticache_subnet_group.this.name
}

output "parameter_group_name" {
  description = "Nome do parameter group"
  value       = aws_elasticache_parameter_group.this.name
}
