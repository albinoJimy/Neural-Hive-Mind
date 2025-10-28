# Outputs para Redis Cluster Module

output "cluster_name" {
  description = "Nome do cluster Redis"
  value       = var.cluster_name
}

output "cluster_namespace" {
  description = "Namespace do cluster Redis"
  value       = kubernetes_namespace.redis_cluster.metadata[0].name
}

output "cluster_endpoint" {
  description = "Endpoint do cluster Redis"
  value       = "${var.cluster_name}.${kubernetes_namespace.redis_cluster.metadata[0].name}.svc.cluster.local"
}

output "cluster_port" {
  description = "Porta do cluster Redis"
  value       = 6379
}

output "cluster_service_name" {
  description = "Nome do service Kubernetes"
  value       = kubernetes_service.redis_cluster.metadata[0].name
}

output "auth_secret_name" {
  description = "Nome do secret com credenciais Redis"
  value       = kubernetes_secret.redis_auth.metadata[0].name
}

output "auth_secret_namespace" {
  description = "Namespace do secret de autenticação"
  value       = kubernetes_secret.redis_auth.metadata[0].namespace
}

output "ca_cert_secret_name" {
  description = "Nome do secret com certificado CA (se TLS habilitado)"
  value       = var.tls_enabled ? kubernetes_secret.redis_ca_cert[0].metadata[0].name : null
}

output "connection_string" {
  description = "String de conexão Redis (sem senha)"
  value       = "redis://${var.cluster_name}.${kubernetes_namespace.redis_cluster.metadata[0].name}.svc.cluster.local:6379"
}

output "connection_string_tls" {
  description = "String de conexão Redis com TLS (sem senha)"
  value       = var.tls_enabled ? "rediss://${var.cluster_name}.${kubernetes_namespace.redis_cluster.metadata[0].name}.svc.cluster.local:6379" : null
}

# Outputs para integração com Gateway de Intenções
output "gateway_integration" {
  description = "Configuração para integração com Gateway"
  value = {
    endpoint           = "${var.cluster_name}.${kubernetes_namespace.redis_cluster.metadata[0].name}.svc.cluster.local"
    port               = 6379
    auth_secret        = kubernetes_secret.redis_auth.metadata[0].name
    auth_secret_key    = "password"
    tls_enabled        = var.tls_enabled
    ca_cert_secret     = var.tls_enabled ? kubernetes_secret.redis_ca_cert[0].metadata[0].name : null
    default_ttl        = var.default_ttl_seconds
    memory_policy      = var.memory_policy
    namespace          = kubernetes_namespace.redis_cluster.metadata[0].name
  }
  sensitive = false
}

# Outputs para observabilidade
output "metrics_endpoint" {
  description = "Endpoint de métricas Prometheus"
  value       = var.enable_metrics ? "${var.cluster_name}-metrics.${kubernetes_namespace.redis_cluster.metadata[0].name}.svc.cluster.local:9121" : null
}

output "metrics_path" {
  description = "Path das métricas"
  value       = "/metrics"
}

output "metrics_labels" {
  description = "Labels para ServiceMonitor"
  value = {
    app       = var.cluster_name
    component = "cache"
    layer     = "memory"
  }
}

# Outputs para backup
output "backup_location" {
  description = "Localização dos backups (se habilitado)"
  value       = var.backup_enabled ? "/backup" : null
}

output "backup_pvc_name" {
  description = "Nome do PVC de backup"
  value       = var.backup_enabled ? kubernetes_persistent_volume_claim.backup_pvc[0].metadata[0].name : null
}

output "backup_schedule" {
  description = "Schedule do backup"
  value       = var.backup_enabled ? var.backup_schedule : null
}

# Outputs para configuração de aplicações
output "client_config" {
  description = "Configuração para clientes Redis"
  value = {
    # Environment variables para aplicações
    REDIS_HOST            = "${var.cluster_name}.${kubernetes_namespace.redis_cluster.metadata[0].name}.svc.cluster.local"
    REDIS_PORT            = "6379"
    REDIS_PASSWORD_SECRET = kubernetes_secret.redis_auth.metadata[0].name
    REDIS_PASSWORD_KEY    = "password"
    REDIS_TLS_ENABLED     = tostring(var.tls_enabled)
    REDIS_DEFAULT_TTL     = tostring(var.default_ttl_seconds)
    REDIS_MAX_CONNECTIONS = "100"
    REDIS_POOL_SIZE      = "10"
    REDIS_TIMEOUT        = "5000"
  }
  sensitive = false
}

# Outputs de status e configuração
output "cluster_config" {
  description = "Configuração atual do cluster"
  value = {
    size              = var.cluster_size
    redis_version     = var.redis_version
    storage_size      = var.storage_size
    storage_class     = var.storage_class
    memory_policy     = var.memory_policy
    persistence       = var.enable_persistence
    metrics_enabled   = var.enable_metrics
    backup_enabled    = var.backup_enabled
    tls_enabled       = var.tls_enabled
    auth_enabled      = var.enable_auth
  }
}

output "maintenance_config" {
  description = "ConfigMap com scripts de manutenção"
  value = {
    name      = kubernetes_config_map.redis_maintenance.metadata[0].name
    namespace = kubernetes_config_map.redis_maintenance.metadata[0].namespace
    scripts   = keys(kubernetes_config_map.redis_maintenance.data)
  }
}