variable "cluster_name" {
  description = "Nome do cluster ClickHouse"
  type        = string
  default     = "neural-hive-clickhouse"
}

variable "namespace" {
  description = "Namespace Kubernetes"
  type        = string
  default     = "clickhouse-cluster"
}

variable "clickhouse_version" {
  description = "Versão do ClickHouse"
  type        = string
  default     = "23.8"
}

variable "shards" {
  description = "Número de shards"
  type        = number
  default     = 3

  validation {
    condition     = var.shards >= 1
    error_message = "O número de shards deve ser no mínimo 1."
  }
}

variable "replicas" {
  description = "Número de réplicas por shard"
  type        = number
  default     = 2

  validation {
    condition     = var.replicas >= 2
    error_message = "O número de réplicas deve ser no mínimo 2 para alta disponibilidade."
  }
}

variable "zookeeper_nodes" {
  description = "Número de nós ZooKeeper/Keeper"
  type        = number
  default     = 3

  validation {
    condition     = var.zookeeper_nodes >= 3 && var.zookeeper_nodes % 2 == 1
    error_message = "O número de nós ZooKeeper deve ser no mínimo 3 e ímpar."
  }
}

variable "storage_size" {
  description = "Tamanho do storage por pod ClickHouse"
  type        = string
  default     = "100Gi"
}

variable "zk_storage_size" {
  description = "Tamanho do storage por pod ZooKeeper"
  type        = string
  default     = "10Gi"
}

variable "storage_class" {
  description = "StorageClass para PVCs"
  type        = string
  default     = "gp3-ssd"
}

variable "cpu_request" {
  description = "CPU request por pod"
  type        = string
  default     = "500m"
}

variable "cpu_limit" {
  description = "CPU limit por pod"
  type        = string
  default     = "2"
}

variable "memory_request" {
  description = "Memory request por pod"
  type        = string
  default     = "2Gi"
}

variable "memory_limit" {
  description = "Memory limit por pod"
  type        = string
  default     = "8Gi"
}

variable "max_memory_usage" {
  description = "Limite de memória para queries"
  type        = string
  default     = "10Gi"
}

variable "max_threads" {
  description = "Threads máximas por query"
  type        = number
  default     = 8
}

variable "admin_password" {
  description = "Senha do usuário admin"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.admin_password) > 0
    error_message = "A senha admin não pode estar vazia."
  }
}

variable "readonly_password" {
  description = "Senha do usuário readonly"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.readonly_password) > 0
    error_message = "A senha readonly não pode estar vazia."
  }
}

variable "writer_password" {
  description = "Senha do usuário writer"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.writer_password) > 0
    error_message = "A senha writer não pode estar vazia."
  }
}

variable "tls_enabled" {
  description = "Habilitar TLS"
  type        = bool
  default     = true
}

variable "compression_codec" {
  description = "Codec de compressão"
  type        = string
  default     = "ZSTD(3)"
}

variable "ttl_days" {
  description = "TTL padrão em dias (18 meses = 540 dias)"
  type        = number
  default     = 540
}

variable "backup_enabled" {
  description = "Habilitar backup automático"
  type        = bool
  default     = true
}

variable "backup_schedule" {
  description = "Cron schedule para backup"
  type        = string
  default     = "0 3 * * *"
}

variable "enable_metrics" {
  description = "Habilitar exportação de métricas"
  type        = bool
  default     = true
}

variable "common_labels" {
  description = "Labels comuns para todos os recursos"
  type        = map(string)
  default     = {}
}

variable "environment" {
  description = "Ambiente de deployment (dev/staging/prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "O ambiente deve ser dev, staging ou prod."
  }
}
