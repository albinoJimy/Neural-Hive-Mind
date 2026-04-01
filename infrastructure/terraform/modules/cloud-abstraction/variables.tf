# Variables para Cloud Abstraction Module
# Define parâmetros independentes de provider para deploy multi-cloud

variable "cloud_provider" {
  description = "Provider de cloud a utilizar"
  type        = string
  validation {
    condition     = contains(["aws", "azure", "gcp"], var.cloud_provider)
    error_message = "cloud_provider deve ser 'aws', 'azure' ou 'gcp'."
  }
}

variable "environment" {
  description = "Ambiente de deploy (dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "Região para deploy de recursos"
  type        = string
  default     = ""
}

variable "cluster_name" {
  description = "Nome do cluster Kubernetes"
  type        = string
}

variable "kubernetes_version" {
  description = "Versão do Kubernetes"
  type        = string
  default     = "1.28.0"
}

variable "vpc_cidr" {
  description = "CIDR block para VPC/VNet"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Zonas de disponibilidade"
  type        = list(string)
  default     = ["1", "2", "3"]
}

variable "node_instance_types" {
  description = "Tipos de instância para nós do cluster"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "min_nodes_per_zone" {
  description = "Número mínimo de nós por zona"
  type        = number
  default     = 1
}

variable "max_nodes_per_zone" {
  description = "Número máximo de nós por zona"
  type        = number
  default     = 3
}

variable "desired_nodes_per_zone" {
  description = "Número desejado de nós por zona"
  type        = number
  default     = 1
}

variable "enable_private_cluster" {
  description = "Habilitar cluster privado (sem endpoint público)"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags comuns para todos os recursos"
  type        = map(string)
  default     = {}
}
