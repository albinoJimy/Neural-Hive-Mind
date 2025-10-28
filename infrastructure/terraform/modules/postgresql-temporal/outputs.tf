# Outputs do módulo PostgreSQL Temporal

output "postgres_host" {
  description = "Hostname do PostgreSQL (service headless)"
  value       = "${var.cluster_name}-headless.${var.namespace}.svc.cluster.local"
}

output "postgres_port" {
  description = "Porta do PostgreSQL"
  value       = 5432
}

output "postgres_database" {
  description = "Nome do database Temporal"
  value       = "temporal"
}

output "postgres_connection_string" {
  description = "Connection string PostgreSQL"
  value       = "postgresql://temporal:${var.temporal_password}@${var.cluster_name}-headless.${var.namespace}.svc.cluster.local:5432/temporal?sslmode=require"
  sensitive   = true
}

output "namespace" {
  description = "Namespace onde PostgreSQL foi provisionado"
  value       = var.namespace
}

output "service_name" {
  description = "Nome do service headless"
  value       = "${var.cluster_name}-headless"
}
