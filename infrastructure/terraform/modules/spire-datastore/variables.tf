# Variables for SPIRE Datastore Module

variable "cluster_name" {
  description = "Nome do cluster EKS"
  type        = string

  validation {
    condition     = length(var.cluster_name) > 0
    error_message = "cluster_name não pode ser vazio"
  }
}

variable "vpc_id" {
  description = "ID da VPC onde o RDS será criado"
  type        = string

  validation {
    condition     = can(regex("^vpc-", var.vpc_id))
    error_message = "vpc_id deve começar com 'vpc-'"
  }
}

variable "private_subnet_ids" {
  description = "Lista de IDs de subnets privadas para RDS"
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Pelo menos 2 subnets privadas são necessárias para RDS Multi-AZ"
  }
}

variable "eks_security_group_id" {
  description = "ID do security group do cluster EKS para permitir acesso ao RDS"
  type        = string

  validation {
    condition     = can(regex("^sg-", var.eks_security_group_id))
    error_message = "eks_security_group_id deve começar com 'sg-'"
  }
}

variable "instance_class" {
  description = "Classe da instância RDS (ex: db.t3.medium, db.r6g.large)"
  type        = string
  default     = "db.t3.medium"

  validation {
    condition     = can(regex("^db\\.", var.instance_class))
    error_message = "instance_class deve começar com 'db.'"
  }
}

variable "allocated_storage" {
  description = "Armazenamento alocado para RDS em GB"
  type        = number
  default     = 20

  validation {
    condition     = var.allocated_storage >= 20 && var.allocated_storage <= 65536
    error_message = "allocated_storage deve estar entre 20 e 65536 GB"
  }
}

variable "multi_az" {
  description = "Habilitar Multi-AZ para alta disponibilidade"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "Número de dias para retenção de backups automáticos"
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 0 && var.backup_retention_days <= 35
    error_message = "backup_retention_days deve estar entre 0 e 35 dias"
  }
}

variable "environment" {
  description = "Ambiente (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment deve ser dev, staging ou prod"
  }
}

variable "tags" {
  description = "Tags adicionais para recursos AWS"
  type        = map(string)
  default     = {}
}
