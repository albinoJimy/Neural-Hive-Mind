# Variáveis do Módulo de Rede - Neural Hive-Mind

variable "name_prefix" {
  description = "Prefixo para nomear recursos"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, qa, staging, prod)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block para VPC principal"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "CIDR block VPC deve ser válido."
  }
}

variable "availability_zones" {
  description = "Lista de zonas de disponibilidade para distribuir recursos"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks para subnets públicas (uma por AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]

}

variable "private_subnet_cidrs" {
  description = "CIDR blocks para subnets privadas (uma por AZ)"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]

}

variable "enable_nat_gateway" {
  description = "Habilitar NAT Gateway para acesso à internet de subnets privadas"
  type        = bool
  default     = true
}

variable "enable_vpc_endpoints" {
  description = "Habilitar VPC Endpoints para serviços AWS (S3, ECR, DynamoDB, KMS) para reduzir latência e custos"
  type        = bool
  default     = true
}

variable "enable_flow_logs" {
  description = "Habilitar VPC Flow Logs para auditoria, segurança e análise de tráfego de rede"
  type        = bool
  default     = true
}

variable "flow_logs_retention_days" {
  description = "Dias de retenção para logs VPC Flow Logs"
  type        = number
  default     = 30
}

variable "cluster_name" {
  description = "Nome do cluster EKS para tags Kubernetes"
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