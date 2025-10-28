# Variáveis do módulo PostgreSQL Temporal

variable "cluster_name" {
  description = "Nome do cluster PostgreSQL"
  type        = string
  default     = "postgres-temporal"
}

variable "namespace" {
  description = "Namespace Kubernetes"
  type        = string
  default     = "temporal-postgres"
}

variable "replica_count" {
  description = "Número de réplicas PostgreSQL"
  type        = number
  default     = 3
}

variable "storage_size" {
  description = "Tamanho do storage para cada réplica"
  type        = string
  default     = "50Gi"
}

variable "storage_class" {
  description = "Storage class para PVCs"
  type        = string
  default     = "standard"
}

variable "postgres_version" {
  description = "Versão da imagem PostgreSQL"
  type        = string
  default     = "15-alpine"
}

variable "backup_enabled" {
  description = "Habilitar backup automático"
  type        = bool
  default     = false
}

variable "enable_external_access" {
  description = "Expor PostgreSQL externamente via LoadBalancer"
  type        = bool
  default     = false
}

variable "common_labels" {
  description = "Labels comuns para todos os recursos"
  type        = map(string)
  default     = {}
}

variable "environment" {
  description = "Ambiente de deployment"
  type        = string
  default     = "production"
}

variable "postgres_password" {
  description = "Senha do usuário postgres (superuser)"
  type        = string
  sensitive   = true
}

variable "temporal_password" {
  description = "Senha do usuário temporal"
  type        = string
  sensitive   = true
}

variable "replication_password" {
  description = "Senha para replicação"
  type        = string
  sensitive   = true
}
