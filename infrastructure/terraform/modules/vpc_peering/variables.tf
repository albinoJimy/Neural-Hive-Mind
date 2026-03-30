# =============================================================================
# Neural Hive-Mind - VPC Peering Variables
# =============================================================================

variable "requester_vpc_id" {
  description = "ID da VPC solicitante"
  type        = string
}

variable "requester_region" {
  description = "Região da VPC solicitante"
  type        = string
}

variable "requester_route_table_ids" {
  description = "IDs das route tables da VPC solicitante"
  type        = list(string)
  default     = []
}

variable "accepter_vpc_id" {
  description = "ID da VPC aceptora"
  type        = string
}

variable "accepter_region" {
  description = "Região da VPC aceptora"
  type        = string
}

variable "accepter_account" {
  description = "Account ID da VPC aceptora"
  type        = string
}

variable "accepter_route_table_ids" {
  description = "IDs das route tables da VPC aceptora"
  type        = list(string)
  default     = []
}

variable "auto_accept" {
  description = "Aceitar automaticamente o peering"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags para o peering connection"
  type        = map(string)
  default     = {}
}
