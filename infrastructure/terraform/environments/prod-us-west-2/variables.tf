# =============================================================================
# Neural Hive-Mind - Variáveis Produção US West 2
# =============================================================================

variable "vpc_peer_ids" {
  description = "IDs das VPCs peer das outras regiões"
  type        = map(string)
  default = {
    "us-east-1" = ""
    "eu-west-1" = ""
  }
}

variable "tags" {
  description = "Tags adicionais"
  type        = map(string)
  default     = {}
}
