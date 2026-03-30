# =============================================================================
# Neural Hive-Mind - Redis Variables
# =============================================================================

variable "cluster_name" {
  description = "Nome do cluster Redis"
  type        = string
}

variable "node_type" {
  description = "Tipo de nó (instance type)"
  type        = string
  default     = "cache.r6g.xlarge"
}

variable "engine_version" {
  description = "Versão do Redis"
  type        = string
  default     = "7.1"
}

variable "port" {
  description = "Porta do Redis"
  type        = number
  default     = 6379
}

variable "num_cache_nodes" {
  description = "Número de nós de cache primários"
  type        = number
  default     = 3
}

variable "replicas_per_node" {
  description = "Número de réplicas por nó primário"
  type        = number
  default     = 1
}

variable "shard_count" {
  description = "Número de shards (cluster mode)"
  type        = number
  default     = 3
}

variable "replicas_per_shard" {
  description = "Réplicas por shard (cluster mode)"
  type        = number
  default     = 2
}

variable "cluster_mode_enabled" {
  description = "Habilitar modo cluster"
  type        = bool
  default     = true
}

variable "automatic_failover_enabled" {
  description = "Habilitar failover automático"
  type        = bool
  default     = true
}

variable "multi_az_enabled" {
  description = "Habilitar multi-AZ"
  type        = bool
  default     = true
}

variable "snapshot_window" {
  description = "Janela de snapshot (UTC)"
  type        = string
  default     = "03:00-05:00"
}

variable "snapshot_retention_limit" {
  description = "Limite de retenção de snapshots (dias)"
  type        = number
  default     = 7
}

variable "maintenance_window" {
  description = "Janela de manutenção"
  type        = string
  default     = "sun:03:00-sun:04:00"
}

variable "transit_encryption_enabled" {
  description = "Habilitar criptografia em trânsito"
  type        = bool
  default     = true
}

variable "at_rest_encryption_enabled" {
  description = "Habilitar criptografia em repouso"
  type        = bool
  default     = true
}

variable "auth_token" {
  description = "Token de autenticação (null para gerar automaticamente)"
  type        = string
  sensitive   = true
  default     = null
}

variable "global_replication_enabled" {
  description = "Habilitar replicação global (multi-região)"
  type        = bool
  default     = true
}

variable "parameter_group_family" {
  description = "Família do parameter group"
  type        = string
  default     = "redis7"
}

variable "parameter_group_parameters" {
  description = "Parâmetros do parameter group"
  type = list(object({
    name  = string
    value = string
  }))
  default = [
    {
      name  = "maxmemory-policy"
      value = "allkeys-lru"
    },
    {
      name  = "timeout"
      value = "300"
    },
    {
      name  = "notify-keyspace-events"
      value = "Ex"
    }
  ]
}

variable "vpc_id" {
  description = "ID da VPC"
  type        = string
}

variable "subnet_ids" {
  description = "IDs das subnets"
  type        = list(string)
}

variable "allowed_security_groups" {
  description = "Security groups permitidos a acessar o Redis"
  type        = list(string)
  default     = []
}

variable "peered_vpc_cidrs" {
  description = "CIDRs das VPCs peered (para acesso cross-region)"
  type        = list(string)
  default     = []
}

variable "notification_topic_arn" {
  description = "ARN do SNS topic para notificações"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags adicionais"
  type        = map(string)
  default     = {}
}
