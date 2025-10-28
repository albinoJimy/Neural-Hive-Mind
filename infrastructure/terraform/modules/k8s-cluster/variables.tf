# Variáveis do Módulo Cluster Kubernetes - Neural Hive-Mind

variable "cluster_name" {
  description = "Nome do cluster EKS"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, qa, staging, prod)"
  type        = string
}

variable "kubernetes_version" {
  description = "Versão do Kubernetes"
  type        = string
  default     = "1.28"
}

variable "vpc_id" {
  description = "ID da VPC onde o cluster será criado"
  type        = string
}

variable "private_subnet_ids" {
  description = "IDs das subnets privadas para os node groups"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "IDs das subnets públicas para load balancers"
  type        = list(string)
}

variable "availability_zones" {
  description = "Zonas de disponibilidade para distribuir node groups"
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == length(var.private_subnet_ids)
    error_message = "availability_zones e private_subnet_ids devem ter o mesmo tamanho."
  }
}

variable "node_instance_types" {
  description = "Tipos de instância EC2 para os nodes"
  type        = list(string)
  default     = ["t3.large", "t3a.large"]
}

variable "min_nodes_per_zone" {
  description = "Número mínimo de nodes por zona"
  type        = number
  default     = 1
}

variable "max_nodes_per_zone" {
  description = "Número máximo de nodes por zona"
  type        = number
  default     = 5
}

variable "desired_nodes_per_zone" {
  description = "Número desejado de nodes por zona"
  type        = number
  default     = 2
}

variable "disk_size_gb" {
  description = "Tamanho do disco EBS para cada node em GB"
  type        = number
  default     = 100
}

variable "enable_cluster_autoscaler" {
  description = "Habilitar Cluster Autoscaler"
  type        = bool
  default     = true
}

variable "enable_load_balancer_controller" {
  description = "Habilitar AWS Load Balancer Controller"
  type        = bool
  default     = true
}

variable "enable_private_endpoint" {
  description = "Habilitar endpoint privado para API do cluster"
  type        = bool
  default     = true
}

variable "enable_public_endpoint" {
  description = "Habilitar endpoint público para API do cluster"
  type        = bool
  default     = true
}

variable "public_access_cidrs" {
  description = "CIDRs permitidos para acesso público ao cluster"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "enabled_log_types" {
  description = "Tipos de logs do control plane para habilitar"
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

variable "map_roles" {
  description = "Roles IAM adicionais para mapear no ConfigMap aws-auth"
  type = list(object({
    rolearn  = string
    username = string
    groups   = list(string)
  }))
  default = []
}

variable "map_users" {
  description = "Usuários IAM para mapear no ConfigMap aws-auth"
  type = list(object({
    userarn  = string
    username = string
    groups   = list(string)
  }))
  default = []
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