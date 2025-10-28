# Variáveis do Módulo Container Registry - Neural Hive-Mind

variable "registry_name" {
  description = "Nome base do registry ECR"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, qa, staging, prod)"
  type        = string
}

variable "repository_names" {
  description = "Lista de nomes de repositórios a criar"
  type        = list(string)
  default = [
    "cognitive-processor",
    "orchestration-engine",
    "execution-agent",
    "memory-store",
    "event-bus"
  ]
}

variable "enable_vulnerability_scanning" {
  description = "Habilitar scanning automático de vulnerabilidades"
  type        = bool
  default     = true
}

variable "block_critical_vulnerabilities" {
  description = "Bloquear imagens com vulnerabilidades críticas"
  type        = bool
  default     = true
}

variable "critical_severity_threshold" {
  description = "Número máximo de vulnerabilidades críticas permitidas"
  type        = number
  default     = 0
}

variable "image_tag_mutability" {
  description = "Mutabilidade de tags de imagem (MUTABLE ou IMMUTABLE)"
  type        = string
  default     = "IMMUTABLE"
}

variable "image_retention_count" {
  description = "Número de imagens tagged para manter"
  type        = number
  default     = 20
}

variable "untagged_retention_days" {
  description = "Dias para manter imagens untagged"
  type        = number
  default     = 7
}

variable "enable_image_signing" {
  description = "Habilitar assinatura de imagens com Sigstore/Notation"
  type        = bool
  default     = true
}

variable "signing_namespace" {
  description = "Namespace Kubernetes para service account de assinatura"
  type        = string
  default     = "neural-hive-system"
}

variable "allowed_registries" {
  description = "Lista de registries externos permitidos"
  type        = list(string)
  default = [
    "public.ecr.aws",
    "docker.io",
    "gcr.io",
    "ghcr.io"
  ]
}

variable "oidc_provider_arn" {
  description = "ARN do OIDC provider do cluster EKS"
  type        = string
  default     = ""
}

variable "oidc_issuer_url" {
  description = "URL do OIDC issuer do cluster EKS"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags obrigatórias para governança"
  type        = map(string)
  default = {
    CostCenter = "neural-hive"
    Owner      = "platform-team"
    Compliance = "required"
  }
}