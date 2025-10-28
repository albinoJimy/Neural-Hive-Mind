# Outputs do módulo Temporal Server

output "temporal_frontend_host" {
  description = "Hostname do Temporal Frontend"
  value       = "temporal-frontend.${var.namespace}.svc.cluster.local"
}

output "temporal_frontend_port" {
  description = "Porta do Temporal Frontend"
  value       = 7233
}

output "temporal_web_url" {
  description = "URL do Temporal Web UI (se habilitado)"
  value       = var.enable_web_ui ? (var.enable_ingress ? "http://${var.ingress_host}" : "http://temporal-web.${var.namespace}.svc.cluster.local:8080") : null
}

output "temporal_namespace" {
  description = "Namespace Temporal para workflows"
  value       = "neural-hive-mind"
}

output "namespace" {
  description = "Namespace Kubernetes onde Temporal foi provisionado"
  value       = var.namespace
}
