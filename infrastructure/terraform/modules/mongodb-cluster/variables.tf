variable "cluster_name" {
  description = "Nome do cluster MongoDB"
  type        = string
  default     = "neural-hive-mongodb"
}

variable "namespace" {
  description = "Namespace Kubernetes"
  type        = string
  default     = "mongodb-cluster"
}

variable "mongodb_version" {
  description = "Versão do MongoDB"
  type        = string
  default     = "7.0.5"
}

variable "replica_count" {
  description = "Número de réplicas no ReplicaSet"
  type        = number
  default     = 3

  validation {
    condition     = var.replica_count >= 3
    error_message = "O replica_count deve ser no mínimo 3 para alta disponibilidade."
  }
}

variable "storage_size" {
  description = "Tamanho do PVC para cada réplica"
  type        = string
  default     = "50Gi"

  validation {
    condition     = can(regex("^[0-9]+Gi$", var.storage_size)) && tonumber(regex("^([0-9]+)Gi$", var.storage_size)[0]) >= 10
    error_message = "O storage_size deve ser no mínimo 10Gi."
  }
}

variable "storage_class" {
  description = "StorageClass para PVCs"
  type        = string
  default     = "gp3-ssd"
}

variable "mongodb_cpu_request" {
  description = "CPU request para containers MongoDB"
  type        = string
  default     = "500m"
}

variable "mongodb_cpu_limit" {
  description = "CPU limit para containers MongoDB"
  type        = string
  default     = "2"
}

variable "mongodb_memory_request" {
  description = "Memory request para containers MongoDB"
  type        = string
  default     = "2Gi"
}

variable "mongodb_memory_limit" {
  description = "Memory limit para containers MongoDB"
  type        = string
  default     = "8Gi"
}

variable "root_password" {
  description = "Senha do usuário root do MongoDB"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.root_password) > 0
    error_message = "A senha root não pode estar vazia."
  }
}

variable "tls_enabled" {
  description = "Habilitar TLS para comunicação"
  type        = bool
  default     = false
}

variable "tls_secret_name" {
  description = "Nome do secret contendo certificados TLS (certificateKeySecret). TLS será habilitado apenas se fornecido."
  type        = string
  default     = ""
}

variable "backup_enabled" {
  description = "Habilitar backup automático"
  type        = bool
  default     = true
}

variable "backup_schedule" {
  description = "Cron schedule para backup automático"
  type        = string
  default     = "0 2 * * *"
}

variable "backup_retention_days" {
  description = "Dias de retenção de backups"
  type        = number
  default     = 7
}

variable "enable_metrics" {
  description = "Habilitar exportação de métricas para Prometheus"
  type        = bool
  default     = true
}

variable "common_labels" {
  description = "Labels comuns para todos os recursos"
  type        = map(string)
  default     = {}
}

variable "pod_annotations" {
  description = "Annotations adicionais para pods"
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
