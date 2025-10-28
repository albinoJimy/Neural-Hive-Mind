# Configurações Terraform para ambiente DEV - Neural Hive-Mind

# Configurações gerais
environment   = "dev"
name_prefix  = "neural-hive-dev"

# Configurações de rede
vpc_cidr = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

public_subnet_cidrs = [
  "10.0.1.0/24",   # us-east-1a
  "10.0.2.0/24",   # us-east-1b
  "10.0.3.0/24"    # us-east-1c
]

private_subnet_cidrs = [
  "10.0.11.0/24",  # us-east-1a
  "10.0.12.0/24",  # us-east-1b
  "10.0.13.0/24"   # us-east-1c
]

# VPC Features
enable_nat_gateway    = true
enable_vpc_endpoints  = true
enable_flow_logs     = true
flow_logs_retention_days = 7  # Menor retenção para dev

# Configurações do cluster Kubernetes
cluster_name       = "neural-hive-dev"
kubernetes_version = "1.28"

# Node groups otimizados para desenvolvimento
node_instance_types = ["t3.medium", "t3.large"]  # Instâncias menores para dev
min_nodes_per_zone  = 1
max_nodes_per_zone  = 3
desired_nodes_per_zone = 1

# Storage menor para desenvolvimento
disk_size_gb = 50

# Features do cluster
enable_cluster_autoscaler      = true
enable_load_balancer_controller = true
enable_private_endpoint        = true
enable_public_endpoint         = true

# Acesso público mais liberal para desenvolvimento
public_access_cidrs = ["0.0.0.0/0"]

# Logs habilitados para debug
enabled_log_types = [
  "api",
  "audit",
  "authenticator",
  "controllerManager",
  "scheduler"
]

# Configurações do container registry
registry_name = "neural-hive-dev"

# Repositórios básicos para desenvolvimento
repository_names = [
  "cognitive-processor",
  "orchestration-engine",
  "execution-agent",
  "memory-store",
  "event-bus",
  "test-runner"
]

# Security scanning habilitado mesmo em dev
enable_vulnerability_scanning = true
# Não bloquear vulnerabilidades em dev para agilizar testes
block_critical_vulnerabilities = false
critical_severity_threshold = 10

# Tags mutáveis em dev para iteração rápida
image_tag_mutability = "MUTABLE"

# Retenção menor para desenvolvimento
image_retention_count = 10
untagged_retention_days = 3

# Image signing opcional em dev
enable_image_signing = false

# Registries permitidos para desenvolvimento
allowed_registries = [
  "public.ecr.aws/",
  "docker.io/",
  "gcr.io/",
  "ghcr.io/",
  "quay.io/",
  "k8s.gcr.io/",
  "registry.k8s.io/"
]

# Tags obrigatórias para governança
tags = {
  Environment = "dev"
  Project     = "neural-hive-mind"
  Owner       = "platform-team"
  CostCenter  = "engineering"
  Compliance  = "development"
  Purpose     = "neural-hive-foundation"

  # Tags para automação
  AutoShutdown = "enabled"
  BackupPolicy = "basic"
  MonitoringLevel = "standard"

  # Tags de ciclo de vida
  CreatedBy   = "terraform"
  CreatedDate = "2024-01-15"
  LastUpdated = "2024-01-15"
}

# Configurações da Camada de Memória - Dev

# MongoDB Configuration - Dev
mongodb_version = "7.0.5"
# mongodb_root_password deve ser definido via variável de ambiente TF_VAR_mongodb_root_password

# Neo4j Configuration - Dev
neo4j_version = "5.15.0"
# neo4j_password deve ser definido via variável de ambiente TF_VAR_neo4j_password

# ClickHouse Configuration - Dev
clickhouse_version = "23.8"
# Senhas devem ser definidas via variáveis de ambiente:
# TF_VAR_clickhouse_admin_password
# TF_VAR_clickhouse_readonly_password
# TF_VAR_clickhouse_writer_password

# StorageClass para camada de memória
storage_class = "gp3-ssd"