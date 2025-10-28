# Variables para Redis Cluster Module

variable "cluster_name" {
  description = "Nome do cluster Redis"
  type        = string
  default     = "neural-hive-cache"
}

variable "namespace" {
  description = "Namespace Kubernetes para Redis Cluster"
  type        = string
  default     = "redis-cluster"
}

variable "redis_version" {
  description = "Versão do Redis"
  type        = string
  default     = "7.0.5"
}

variable "cluster_size" {
  description = "Número total de nodes no cluster (deve ser múltiplo de 3)"
  type        = number
  default     = 6
  validation {
    condition     = var.cluster_size >= 6 && var.cluster_size % 3 == 0
    error_message = "Cluster size deve ser >= 6 e múltiplo de 3."
  }
}

variable "storage_size" {
  description = "Tamanho do storage por instância Redis"
  type        = string
  default     = "10Gi"
}

variable "storage_class" {
  description = "Storage class para volumes Redis"
  type        = string
  default     = "gp3-ssd"
}

variable "replicas_per_master" {
  description = "Número de replicas por master"
  type        = number
  default     = 1
}

variable "default_ttl_seconds" {
  description = "TTL padrão para cache (segundos)"
  type        = number
  default     = 600  # 10 minutos
}

variable "memory_policy" {
  description = "Política de eviction de memória"
  type        = string
  default     = "allkeys-lru"
  validation {
    condition = contains([
      "noeviction", "allkeys-lru", "volatile-lru",
      "allkeys-random", "volatile-random", "volatile-ttl"
    ], var.memory_policy)
    error_message = "Memory policy deve ser uma das opções válidas do Redis."
  }
}

variable "enable_persistence" {
  description = "Habilitar persistência de dados (AOF + RDB)"
  type        = bool
  default     = true
}

variable "enable_metrics" {
  description = "Habilitar coleta de métricas Prometheus"
  type        = bool
  default     = true
}

variable "backup_enabled" {
  description = "Habilitar backup automático"
  type        = bool
  default     = true
}

variable "backup_schedule" {
  description = "Schedule do backup em formato cron"
  type        = string
  default     = "0 2 * * *"  # Diário às 2h
}

variable "backup_storage_size" {
  description = "Tamanho do storage para backups"
  type        = string
  default     = "50Gi"
}

# Configurações de Segurança
variable "enable_auth" {
  description = "Habilitar autenticação Redis"
  type        = bool
  default     = true
}

variable "redis_password" {
  description = "Senha do Redis (usar via environment ou secrets)"
  type        = string
  sensitive   = true
}

variable "tls_enabled" {
  description = "Habilitar TLS para conexões Redis"
  type        = bool
  default     = true
}

variable "ca_cert" {
  description = "Certificado CA para TLS"
  type        = string
  default     = ""
  sensitive   = true
}

variable "ca_key" {
  description = "Chave privada do CA para TLS"
  type        = string
  default     = ""
  sensitive   = true
}

# Resource Limits
variable "redis_cpu_request" {
  description = "CPU request para pods Redis"
  type        = string
  default     = "500m"
}

variable "redis_cpu_limit" {
  description = "CPU limit para pods Redis"
  type        = string
  default     = "2"
}

variable "redis_memory_request" {
  description = "Memory request para pods Redis"
  type        = string
  default     = "1Gi"
}

variable "redis_memory_limit" {
  description = "Memory limit para pods Redis"
  type        = string
  default     = "4Gi"
}

# Kubernetes Configuration
variable "service_account_name" {
  description = "Nome da ServiceAccount para pods Redis"
  type        = string
  default     = "redis-cluster"
}

variable "common_labels" {
  description = "Labels comuns para todos os recursos"
  type        = map(string)
  default = {
    "environment"    = "production"
    "managed-by"     = "terraform"
    "project"        = "neural-hive-mind"
  }
}

variable "pod_annotations" {
  description = "Annotations para pods Redis"
  type        = map(string)
  default = {
    "neural-hive.io/monitoring" = "enabled"
    "neural-hive.io/backup"     = "enabled"
  }
}

# Environment Tags
variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment deve ser dev, staging ou prod."
  }
}

variable "tags" {
  description = "Tags de governança e compliance"
  type        = map(string)
  default = {
    "data_owner"         = "team-sre"
    "data_classification" = "internal"
    "pii_data"           = "false"
    "retention_policy"   = "90d"
    "sla_tier"           = "gold"
  }
}