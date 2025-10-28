output "namespace" {
  description = "Namespace onde Neo4j foi deployado"
  value       = kubernetes_namespace.neo4j.metadata[0].name
}

output "cluster_name" {
  description = "Nome do cluster Neo4j"
  value       = var.cluster_name
}

output "bolt_service_name" {
  description = "Nome do Service para conexões Bolt"
  value       = kubernetes_service.neo4j_bolt.metadata[0].name
}

output "http_service_name" {
  description = "Nome do Service para HTTP/Browser"
  value       = kubernetes_service.neo4j_http.metadata[0].name
}

output "bolt_uri" {
  description = "URI Bolt para conexões (formato: bolt://service:7687)"
  value       = "bolt://${kubernetes_service.neo4j_bolt.metadata[0].name}.${kubernetes_namespace.neo4j.metadata[0].name}.svc.cluster.local:7687"
}

output "http_uri" {
  description = "URI HTTP para browser (formato: http://service:7474)"
  value       = "http://${kubernetes_service.neo4j_http.metadata[0].name}.${kubernetes_namespace.neo4j.metadata[0].name}.svc.cluster.local:7474"
}

output "secret_name" {
  description = "Nome do Secret contendo credenciais"
  value       = kubernetes_secret.neo4j_auth.metadata[0].name
}

output "neo4j_version" {
  description = "Versão do Neo4j deployado"
  value       = var.neo4j_version
}

output "edition" {
  description = "Edição do Neo4j (community ou enterprise)"
  value       = var.edition
}

output "core_servers_count" {
  description = "Número de core servers"
  value       = var.core_servers
}

output "read_replicas_count" {
  description = "Número de read replicas"
  value       = var.read_replicas
}

output "metrics_service_name" {
  description = "Nome do Service de métricas (se habilitado)"
  value       = var.enable_metrics ? kubernetes_service.neo4j_metrics[0].metadata[0].name : null
}

output "plugins_installed" {
  description = "Lista de plugins habilitados"
  value       = var.plugins_enabled
}
