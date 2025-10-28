# Variables para Keycloak Module

variable "instance_name" {
  description = "Nome da instância Keycloak"
  type        = string
  default     = "keycloak"
}

variable "namespace" {
  description = "Namespace Kubernetes para Keycloak"
  type        = string
  default     = "auth"
}

variable "keycloak_version" {
  description = "Versão do Keycloak"
  type        = string
  default     = "22.0.5"
}

variable "replicas" {
  description = "Número de replicas Keycloak para HA"
  type        = number
  default     = 2
  validation {
    condition     = var.replicas >= 1
    error_message = "Replicas deve ser >= 1."
  }
}

# Admin Configuration
variable "admin_username" {
  description = "Username do administrador Keycloak"
  type        = string
  default     = "admin"
}

variable "admin_password" {
  description = "Senha do administrador (usar via environment ou secrets)"
  type        = string
  default     = ""
  sensitive   = true
}

# Database Configuration
variable "database_host" {
  description = "Host do banco de dados PostgreSQL"
  type        = string
}

variable "database_port" {
  description = "Porta do banco de dados"
  type        = number
  default     = 5432
}

variable "database_name" {
  description = "Nome do banco de dados"
  type        = string
  default     = "keycloak"
}

variable "database_username" {
  description = "Username do banco de dados"
  type        = string
  default     = "keycloak"
}

variable "database_password" {
  description = "Senha do banco de dados"
  type        = string
  default     = ""
  sensitive   = true
}

# Realm Configuration
variable "realm_name" {
  description = "Nome do realm principal"
  type        = string
  default     = "neural-hive"
}

variable "token_lifespan" {
  description = "Tempo de vida do token em segundos"
  type        = number
  default     = 3600  # 1 hora
}

# OAuth2 Clients Configuration
variable "gateway_redirect_uris" {
  description = "URIs de redirect para o Gateway de Intenções"
  type        = list(string)
  default = [
    "https://gateway.neural-hive.local/auth/callback",
    "http://localhost:8080/auth/callback"
  ]
}

variable "gateway_web_origins" {
  description = "Origens web permitidas para o Gateway"
  type        = list(string)
  default = [
    "https://gateway.neural-hive.local",
    "http://localhost:8080"
  ]
}

variable "client_ids" {
  description = "Lista de client IDs OAuth2 adicionais"
  type        = list(string)
  default     = []
}

variable "client_secrets" {
  description = "Map de secrets para clients OAuth2"
  type        = map(string)
  default     = {}
  sensitive   = true
}

# Resource Limits
variable "cpu_request" {
  description = "CPU request para pods Keycloak"
  type        = string
  default     = "500m"
}

variable "cpu_limit" {
  description = "CPU limit para pods Keycloak"
  type        = string
  default     = "2"
}

variable "memory_request" {
  description = "Memory request para pods Keycloak"
  type        = string
  default     = "1Gi"
}

variable "memory_limit" {
  description = "Memory limit para pods Keycloak"
  type        = string
  default     = "2Gi"
}

# Monitoring Configuration
variable "enable_metrics" {
  description = "Habilitar coleta de métricas Prometheus"
  type        = bool
  default     = true
}

variable "log_level" {
  description = "Nível de log Keycloak"
  type        = string
  default     = "INFO"
  validation {
    condition = contains([
      "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"
    ], var.log_level)
    error_message = "Log level deve ser TRACE, DEBUG, INFO, WARN, ERROR ou FATAL."
  }
}

# TLS Configuration
variable "tls_enabled" {
  description = "Habilitar TLS para Keycloak"
  type        = bool
  default     = true
}

variable "tls_cert" {
  description = "Certificado TLS"
  type        = string
  default     = ""
  sensitive   = true
}

variable "tls_key" {
  description = "Chave privada TLS"
  type        = string
  default     = ""
  sensitive   = true
}

# Backup Configuration
variable "backup_enabled" {
  description = "Habilitar backup automático do realm"
  type        = bool
  default     = true
}

variable "backup_schedule" {
  description = "Schedule do backup em formato cron"
  type        = string
  default     = "0 3 * * *"  # Diário às 3h
}

variable "backup_retention_days" {
  description = "Retenção dos backups em dias"
  type        = number
  default     = 30
}

# Integration Configuration
variable "istio_injection" {
  description = "Habilitar injeção Istio sidecar"
  type        = bool
  default     = true
}

variable "external_url" {
  description = "URL externa do Keycloak"
  type        = string
  default     = "https://keycloak.neural-hive.local"
}

# Kubernetes Configuration
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
  description = "Annotations para pods Keycloak"
  type        = map(string)
  default = {
    "neural-hive.io/monitoring" = "enabled"
    "neural-hive.io/backup"     = "enabled"
  }
}

# Environment Configuration
variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment deve ser dev, staging ou prod."
  }
}

# Governance Tags
variable "tags" {
  description = "Tags de governança e compliance"
  type        = map(string)
  default = {
    "data_owner"         = "team-security"
    "data_classification" = "confidential"
    "pii_data"           = "true"
    "retention_policy"   = "365d"
    "sla_tier"           = "platinum"
    "compliance"         = "oauth2-oidc"
  }
}

# Advanced Configuration
variable "theme_name" {
  description = "Nome do tema customizado Keycloak"
  type        = string
  default     = "neural-hive"
}

variable "session_timeout" {
  description = "Timeout da sessão em segundos"
  type        = number
  default     = 1800  # 30 minutos
}

variable "max_session_lifespan" {
  description = "Tempo máximo de vida da sessão em segundos"
  type        = number
  default     = 36000  # 10 horas
}

variable "password_policy" {
  description = "Política de senha customizada"
  type        = string
  default     = "hashIterations(27500) and specialChars(1) and upperCase(1) and digits(1) and notUsername(undefined) and length(8)"
}

# LDAP Integration (opcional)
variable "ldap_enabled" {
  description = "Habilitar integração LDAP/AD"
  type        = bool
  default     = false
}

variable "ldap_config" {
  description = "Configuração LDAP"
  type = object({
    vendor          = string
    connection_url  = string
    users_dn        = string
    bind_dn         = string
    bind_credential = string
  })
  default = {
    vendor          = "ad"
    connection_url  = ""
    users_dn        = ""
    bind_dn         = ""
    bind_credential = ""
  }
  sensitive = true
}