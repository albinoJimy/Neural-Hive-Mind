# =============================================================================
# Neural Hive-Mind - MongoDB Variables
# =============================================================================

variable "project_name" {
  description = "Nome do projeto MongoDB Atlas"
  type        = string
  default     = "neural-hive-mind-prod"
}

variable "atlas_org_id" {
  description = "MongoDB Atlas Organization ID"
  type        = string
  sensitive   = true
}

variable "atlas_public_key" {
  description = "MongoDB Atlas Public Key"
  type        = string
  sensitive   = true
}

variable "atlas_private_key" {
  description = "MongoDB Atlas Private Key"
  type        = string
  sensitive   = true
}

variable "cluster_name" {
  description = "Nome do cluster MongoDB Atlas"
  type        = string
  default     = "neural-hive-prod"
}

variable "num_shards" {
  description = "Número de shards no cluster"
  type        = number
  default     = 1
}

variable "members" {
  description = "Configuração dos membros do replica set"
  type = list(object({
    region    = string
    node_type = string
    priority  = number
    electable = optional(bool, true)
    votes     = number
    read_only = optional(bool)
  }))
  default = [
    {
      region    = "US_EAST_1"
      node_type = "M50"
      priority  = 1
      votes     = 1
    },
    {
      region    = "US_WEST_2"
      node_type = "M50"
      priority  = 2
      votes     = 1
    },
    {
      region    = "EU_WEST_1"
      node_type = "M50"
      priority  = 3
      votes     = 1
    }
  ]
}

variable "continuous_backup_enabled" {
  description = "Habilitar backup contínuo"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "Dias de retenção de backup"
  type        = number
  default     = 30
}

variable "enable_bi_connector" {
  description = "Habilitar BI Connector"
  type        = bool
  default     = false
}

variable "enable_connector" {
  description = "Habilitar Connector"
  type        = bool
  default     = false
}

variable "connector_docker_image" {
  description = "Imagem Docker do connector"
  type        = string
  default     = "mongodb/data-federation:11.6.0.2346.ga20240801-9044131"
}

variable "autoscale" {
  description = "Configuração de auto-scaling"
  type = object({
    compute_enabled = optional(bool, true)
    disk_gb_enabled = optional(bool, true)
    max_disk_size   = optional(number, 1000)
  })
  default = {
    compute_enabled = true
    disk_gb_enabled = true
  }
}

variable "enable_private_link" {
  description = "Habilitar Private Link"
  type        = bool
  default     = false
}

variable "private_endpoint_ips" {
  description = "IPs dos endpoints privados por região"
  type        = map(string)
  default     = {}
}

variable "enable_auditing" {
  description = "Habilitar auditoria"
  type        = bool
  default     = true
}

variable "audit_filter" {
  description = "Filtro de auditoria"
  type        = string
  default     = "{\"atype\":{\"$in\":[\"createCollection\",\"dropCollection\",\"createIndex\",\"dropIndex\",\"insert\",\"update\",\"remove\"]}}"
}

variable "admin_password" {
  description = "Senha do usuário admin"
  type        = string
  sensitive   = true
}

variable "app_password" {
  description = "Senha do usuário app"
  type        = string
  sensitive   = true
}

variable "aws_account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "vpc_ids" {
  description = "IDs das VPCs por região"
  type        = map(string)
  default     = {}
}

variable "vpc_cidrs" {
  description = "CIDRs das VPCs por região"
  type        = map(string)
  default     = {}
}

variable "labels" {
  description = "Labels para o cluster"
  type        = map(string)
  default = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

variable "tags" {
  description = "Tags adicionais"
  type        = map(string)
  default     = {}
}
