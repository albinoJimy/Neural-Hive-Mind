# Variáveis Root - Neural Hive-Mind Infrastructure

# Configurações gerais
variable "environment" {
  description = "Ambiente (dev, qa, staging, prod)"
  type        = string
}

variable "name_prefix" {
  description = "Prefixo para nomear recursos"
  type        = string
}

variable "tags" {
  description = "Tags a serem aplicadas a todos os recursos"
  type        = map(string)
  default     = {}
}

# Configurações de rede
variable "vpc_cidr" {
  description = "CIDR block para VPC principal"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Lista de zonas de disponibilidade"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks para subnets públicas"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks para subnets privadas"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
}

variable "enable_nat_gateway" {
  description = "Habilitar NAT Gateway para subnets privadas"
  type        = bool
  default     = true
}

variable "enable_vpc_endpoints" {
  description = "Habilitar VPC endpoints para serviços AWS"
  type        = bool
  default     = true
}

variable "enable_flow_logs" {
  description = "Habilitar VPC Flow Logs"
  type        = bool
  default     = true
}

variable "flow_logs_retention_days" {
  description = "Dias de retenção para VPC Flow Logs"
  type        = number
  default     = 30
}

# Configurações do cluster Kubernetes
variable "cluster_name" {
  description = "Nome do cluster EKS"
  type        = string
}

variable "kubernetes_version" {
  description = "Versão do Kubernetes"
  type        = string
  default     = "1.28"
}

variable "node_instance_types" {
  description = "Tipos de instâncias para nós worker"
  type        = list(string)
  default     = ["t3.medium", "t3.large"]
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
  default     = 2
}

variable "disk_size_gb" {
  description = "Tamanho do disco em GB para nós worker"
  type        = number
  default     = 100
}

variable "enable_cluster_autoscaler" {
  description = "Habilitar cluster autoscaler"
  type        = bool
  default     = true
}

variable "enable_load_balancer_controller" {
  description = "Habilitar AWS Load Balancer Controller"
  type        = bool
  default     = true
}

variable "enable_private_endpoint" {
  description = "Habilitar endpoint privado do cluster"
  type        = bool
  default     = true
}

variable "enable_public_endpoint" {
  description = "Habilitar endpoint público do cluster"
  type        = bool
  default     = true
}

variable "public_access_cidrs" {
  description = "CIDRs permitidos para acesso público"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "enabled_log_types" {
  description = "Tipos de logs habilitados para o cluster"
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

# Configurações do container registry
variable "registry_name" {
  description = "Nome do registry ECR"
  type        = string
}

variable "repository_names" {
  description = "Lista de nomes de repositórios ECR"
  type        = list(string)
  default     = []
}

variable "enable_vulnerability_scanning" {
  description = "Habilitar scanning de vulnerabilidades"
  type        = bool
  default     = true
}

variable "block_critical_vulnerabilities" {
  description = "Bloquear imagens com vulnerabilidades críticas"
  type        = bool
  default     = false
}

variable "critical_severity_threshold" {
  description = "Limite de vulnerabilidades críticas"
  type        = number
  default     = 5
}

variable "image_tag_mutability" {
  description = "Mutabilidade das tags de imagem (MUTABLE ou IMMUTABLE)"
  type        = string
  default     = "IMMUTABLE"
}

variable "image_retention_count" {
  description = "Número de imagens a manter"
  type        = number
  default     = 30
}

variable "untagged_retention_days" {
  description = "Dias para manter imagens sem tag"
  type        = number
  default     = 7
}

variable "enable_image_signing" {
  description = "Habilitar assinatura de imagens"
  type        = bool
  default     = false
}

variable "allowed_registries" {
  description = "Lista de registries permitidos"
  type        = list(string)
  default     = []
}

# Configurações OIDC (para image signing)
variable "oidc_provider_arn" {
  description = "ARN do provider OIDC do cluster EKS"
  type        = string
  default     = ""
}

variable "oidc_issuer_url" {
  description = "URL do issuer OIDC do cluster EKS"
  type        = string
  default     = ""
}

variable "signing_namespace" {
  description = "Namespace para assinatura de imagens"
  type        = string
  default     = "image-signing"
}

# Configurações da Camada de Memória

# MongoDB Configuration
variable "mongodb_version" {
  description = "Versão do MongoDB"
  type        = string
  default     = "7.0.5"
}

variable "mongodb_root_password" {
  description = "Senha root do MongoDB"
  type        = string
  sensitive   = true
}

# Neo4j Configuration
variable "neo4j_version" {
  description = "Versão do Neo4j"
  type        = string
  default     = "5.15.0"
}

variable "neo4j_password" {
  description = "Senha do usuário neo4j"
  type        = string
  sensitive   = true
}

# ClickHouse Configuration
variable "clickhouse_version" {
  description = "Versão do ClickHouse"
  type        = string
  default     = "23.8"
}

variable "clickhouse_admin_password" {
  description = "Senha admin do ClickHouse"
  type        = string
  sensitive   = true
}

variable "clickhouse_readonly_password" {
  description = "Senha usuário readonly do ClickHouse"
  type        = string
  sensitive   = true
}

variable "clickhouse_writer_password" {
  description = "Senha usuário writer do ClickHouse"
  type        = string
  sensitive   = true
}

# StorageClass comum para todos os módulos de memória
variable "storage_class" {
  description = "StorageClass para PVCs da camada de memória"
  type        = string
  default     = "gp3-ssd"
}

# SPIRE Datastore Configuration
variable "spire_db_instance_class" {
  description = "Classe da instância RDS para SPIRE datastore"
  type        = string
  default     = "db.t3.medium"
}

variable "spire_db_allocated_storage" {
  description = "Armazenamento alocado para SPIRE RDS em GB"
  type        = number
  default     = 20
}