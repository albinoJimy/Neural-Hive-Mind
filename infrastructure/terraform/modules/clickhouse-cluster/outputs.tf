output "namespace" {
  description = "Namespace onde ClickHouse foi deployado"
  value       = kubernetes_namespace.clickhouse.metadata[0].name
}

output "cluster_name" {
  description = "Nome do cluster ClickHouse"
  value       = var.cluster_name
}

output "http_service_name" {
  description = "Nome do Service HTTP"
  value       = kubernetes_service.clickhouse.metadata[0].name
}

output "native_service_name" {
  description = "Nome do Service Native protocol"
  value       = kubernetes_service.clickhouse.metadata[0].name
}

output "http_uri" {
  description = "URI HTTP para conexões (formato: http://service:8123)"
  value       = "http://${kubernetes_service.clickhouse.metadata[0].name}.${kubernetes_namespace.clickhouse.metadata[0].name}.svc.cluster.local:8123"
}

output "native_uri" {
  description = "URI Native protocol (formato: clickhouse://service:9000)"
  value       = "clickhouse://${kubernetes_service.clickhouse.metadata[0].name}.${kubernetes_namespace.clickhouse.metadata[0].name}.svc.cluster.local:9000"
  sensitive   = true
}

output "secret_name" {
  description = "Nome do Secret contendo credenciais"
  value       = kubernetes_secret.clickhouse_auth.metadata[0].name
}

output "clickhouse_version" {
  description = "Versão do ClickHouse deployado"
  value       = var.clickhouse_version
}

output "shards_count" {
  description = "Número de shards"
  value       = var.shards
}

output "replicas_per_shard" {
  description = "Número de réplicas por shard"
  value       = var.replicas
}

output "zookeeper_nodes_count" {
  description = "Número de nós ZooKeeper"
  value       = var.zookeeper_nodes
}

output "metrics_service_name" {
  description = "Nome do Service de métricas (se habilitado)"
  value       = var.enable_metrics ? kubernetes_service.clickhouse.metadata[0].name : null
}

output "total_storage_provisioned" {
  description = "Storage total provisionado (estimativa)"
  value       = "${var.shards * var.replicas * tonumber(regex("^[0-9]+", var.storage_size))}Gi"
}
