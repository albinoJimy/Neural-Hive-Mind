output "namespace" {
  description = "Namespace onde MongoDB foi deployado"
  value       = kubernetes_namespace.mongodb.metadata[0].name
}

output "cluster_name" {
  description = "Nome do cluster MongoDB"
  value       = var.cluster_name
}

output "service_name" {
  description = "Nome do Service Kubernetes para conexão"
  value       = kubernetes_service.mongodb.metadata[0].name
}

output "connection_string" {
  description = "String de conexão MongoDB (formato: mongodb://service:27017)"
  value       = "mongodb://${kubernetes_service.mongodb.metadata[0].name}.${kubernetes_namespace.mongodb.metadata[0].name}.svc.cluster.local:27017"
  sensitive   = true
}

output "connection_string_srv" {
  description = "String SRV para ReplicaSet (formato: mongodb+srv://service)"
  value       = "mongodb+srv://${kubernetes_service.mongodb.metadata[0].name}.${kubernetes_namespace.mongodb.metadata[0].name}.svc.cluster.local"
  sensitive   = true
}

output "secret_name" {
  description = "Nome do Secret contendo credenciais"
  value       = kubernetes_secret.mongodb_auth.metadata[0].name
}

output "operator_version" {
  description = "Versão do MongoDB Operator instalado"
  value       = helm_release.mongodb_operator.version
}

output "mongodb_version" {
  description = "Versão do MongoDB deployado"
  value       = var.mongodb_version
}

output "replica_count" {
  description = "Número de réplicas configuradas"
  value       = var.replica_count
}

output "metrics_service_name" {
  description = "Nome do Service de métricas (se habilitado)"
  value       = var.enable_metrics ? kubernetes_service.mongodb.metadata[0].name : null
}

output "backup_pvc_name" {
  description = "Nome do PVC de backup (se habilitado)"
  value       = var.backup_enabled ? kubernetes_persistent_volume_claim.backup[0].metadata[0].name : null
}
