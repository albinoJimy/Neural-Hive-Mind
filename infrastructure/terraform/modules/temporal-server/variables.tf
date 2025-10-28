# Variáveis do módulo Temporal Server

variable "namespace" {
  description = "Namespace Kubernetes para Temporal Server"
  type        = string
  default     = "temporal"
}

variable "temporal_version" {
  description = "Versão da imagem Temporal Server"
  type        = string
  default     = "1.22.0"
}

variable "postgres_connection_string" {
  description = "Connection string do PostgreSQL"
  type        = string
  sensitive   = true
}

variable "enable_web_ui" {
  description = "Habilitar Temporal Web UI"
  type        = bool
  default     = false
}

variable "enable_ingress" {
  description = "Habilitar Ingress para Web UI"
  type        = bool
  default     = false
}

variable "ingress_host" {
  description = "Hostname para Ingress"
  type        = string
  default     = "temporal.local"
}

variable "replica_counts" {
  description = "Número de réplicas para cada componente"
  type = object({
    frontend = number
    history  = number
    matching = number
    worker   = number
  })
  default = {
    frontend = 2
    history  = 3
    matching = 3
    worker   = 2
  }
}

variable "resources" {
  description = "Resources requests/limits para componentes"
  type = object({
    frontend = object({
      requests_cpu    = string
      requests_memory = string
      limits_cpu      = string
      limits_memory   = string
    })
    history = object({
      requests_cpu    = string
      requests_memory = string
      limits_cpu      = string
      limits_memory   = string
    })
    matching = object({
      requests_cpu    = string
      requests_memory = string
      limits_cpu      = string
      limits_memory   = string
    })
    worker = object({
      requests_cpu    = string
      requests_memory = string
      limits_cpu      = string
      limits_memory   = string
    })
  })
  default = {
    frontend = {
      requests_cpu    = "500m"
      requests_memory = "1Gi"
      limits_cpu      = "2000m"
      limits_memory   = "4Gi"
    }
    history = {
      requests_cpu    = "1000m"
      requests_memory = "2Gi"
      limits_cpu      = "3000m"
      limits_memory   = "6Gi"
    }
    matching = {
      requests_cpu    = "500m"
      requests_memory = "1Gi"
      limits_cpu      = "2000m"
      limits_memory   = "4Gi"
    }
    worker = {
      requests_cpu    = "500m"
      requests_memory = "1Gi"
      limits_cpu      = "2000m"
      limits_memory   = "4Gi"
    }
  }
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
