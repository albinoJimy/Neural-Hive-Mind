variable "cluster_name" {
  description = "Nome do cluster Neo4j"
  type        = string
  default     = "neural-hive-neo4j"
}

variable "namespace" {
  description = "Namespace Kubernetes"
  type        = string
  default     = "neo4j-cluster"
}

variable "neo4j_version" {
  description = "Versão do Neo4j"
  type        = string
  default     = "5.15.0"
}

variable "edition" {
  description = "Edição do Neo4j (community ou enterprise)"
  type        = string
  default     = "community"

  validation {
    condition     = contains(["community", "enterprise"], var.edition)
    error_message = "A edição deve ser 'community' ou 'enterprise'."
  }
}

variable "core_servers" {
  description = "Número de core servers (cluster causal)"
  type        = number
  default     = 3

  validation {
    condition     = var.core_servers >= 3
    error_message = "O número de core_servers deve ser no mínimo 3 para cluster."
  }
}

variable "read_replicas" {
  description = "Número de read replicas"
  type        = number
  default     = 2
}

variable "core_storage_size" {
  description = "Tamanho do storage para core servers"
  type        = string
  default     = "50Gi"
}

variable "replica_storage_size" {
  description = "Tamanho do storage para read replicas"
  type        = string
  default     = "30Gi"
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

variable "heap_initial_size" {
  description = "Tamanho inicial do heap JVM"
  type        = string
  default     = "2G"
}

variable "heap_max_size" {
  description = "Tamanho máximo do heap JVM"
  type        = string
  default     = "4G"
}

variable "pagecache_size" {
  description = "Tamanho do pagecache"
  type        = string
  default     = "2G"
}

variable "neo4j_password" {
  description = "Senha do usuário neo4j"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.neo4j_password) > 0
    error_message = "A senha do Neo4j não pode estar vazia."
  }
}

variable "tls_enabled" {
  description = "Habilitar TLS para Bolt e HTTPS"
  type        = bool
  default     = true
}

variable "plugins_enabled" {
  description = "Lista de plugins a habilitar"
  type        = list(string)
  default     = ["apoc", "graph-data-science", "neosemantics"]
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
  description = "Habilitar exportação de métricas Prometheus"
  type        = bool
  default     = true
}

variable "query_timeout" {
  description = "Timeout padrão para queries"
  type        = string
  default     = "120s"
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
