# =============================================================================
# Neural Hive-Mind - Variáveis Produção US East 1
# =============================================================================

variable "domain_name" {
  description = "Domínio principal para Route53"
  type        = string
  default     = "neural-hive.com"
}

variable "atlas_project_id" {
  description = "MongoDB Atlas Project ID"
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

variable "redis_auth_token" {
  description = "Token de autenticação Redis"
  type        = string
  sensitive   = true
}

variable "vpc_peer_ids" {
  description = "IDs das VPCs peer das outras regiões"
  type = map(string)
  default = {
    "us-west-2" = ""
    "eu-west-1" = ""
  }
}

variable "redis_secondary_ids" {
  description = "IDs dos clusters Redis secundários"
  type = map(string)
  default = {
    "us-west-2" = ""
    "eu-west-1" = ""
  }
}

variable "tags" {
  description = "Tags adicionais"
  type        = map(string)
  default     = {}
}

variable "kubernetes_cluster_west_endpoint" {
  description = "Endpoint do cluster US West (para DNS)"
  type        = string
  default     = ""
}

variable "kubernetes_cluster_eu_endpoint" {
  description = "Endpoint do cluster EU West (para DNS)"
  type        = string
  default     = ""
}
