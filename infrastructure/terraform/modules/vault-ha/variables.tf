# Variables para módulo Vault HA

variable "cluster_name" {
  description = "Nome do cluster EKS"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "oidc_provider_arn" {
  description = "ARN do OIDC provider do EKS para IRSA"
  type        = string
}

variable "oidc_provider_url" {
  description = "URL do OIDC provider do EKS"
  type        = string
}

variable "enable_audit_logs" {
  description = "Habilitar S3 bucket para audit logs"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags para recursos AWS"
  type        = map(string)
  default     = {}
}
