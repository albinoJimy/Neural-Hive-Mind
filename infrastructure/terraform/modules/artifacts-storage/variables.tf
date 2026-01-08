# Variables para módulo artifacts-storage

variable "cluster_name" {
  description = "Nome do cluster EKS"
  type        = string
}

variable "environment" {
  description = "Ambiente de execução"
  type        = string
  default     = "production"
}

variable "oidc_provider_arn" {
  description = "ARN do OIDC provider do EKS"
  type        = string
}

variable "oidc_provider_url" {
  description = "URL do OIDC provider do EKS"
  type        = string
}

variable "enable_versioning" {
  description = "Habilitar versionamento do bucket"
  type        = bool
  default     = true
}

variable "lifecycle_glacier_days" {
  description = "Dias para transição para Glacier"
  type        = number
  default     = 90
}

variable "lifecycle_expiration_days" {
  description = "Dias para expiração de versões antigas"
  type        = number
  default     = 365
}

variable "tags" {
  description = "Tags para recursos"
  type        = map(string)
  default     = {}
}
