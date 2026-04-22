# =============================================================================
# Neural Hive-Mind - Variáveis Produção EU West 1
# =============================================================================

variable "vpc_peer_ids" {
  description = "IDs das VPCs peer das outras regiões"
  type        = map(string)
  default = {
    "us-east-1" = ""
    "us-west-2" = ""
  }
}

variable "tags" {
  description = "Tags adicionais"
  type        = map(string)
  default     = {}
}

variable "enable_gdpr_services" {
  description = "Habilitar serviços específicos para compliance GDPR"
  type        = bool
  default     = true
}
