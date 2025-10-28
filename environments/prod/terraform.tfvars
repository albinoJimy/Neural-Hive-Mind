# Configurações Terraform para ambiente PRODUCTION - Neural Hive-Mind

# Configurações gerais
environment  = "prod"
name_prefix = "neural-hive-prod"

# Configurações de rede para produção
vpc_cidr = "10.10.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

public_subnet_cidrs = [
  "10.10.1.0/24",   # us-east-1a
  "10.10.2.0/24",   # us-east-1b
  "10.10.3.0/24"    # us-east-1c
]

private_subnet_cidrs = [
  "10.10.11.0/24",  # us-east-1a
  "10.10.12.0/24",  # us-east-1b
  "10.10.13.0/24"   # us-east-1c
]

# VPC Features de produção
enable_nat_gateway    = true
enable_vpc_endpoints  = true
enable_flow_logs     = true
flow_logs_retention_days = 90  # Retenção longa para auditoria

# Configurações do cluster Kubernetes para produção
cluster_name       = "neural-hive-prod"
kubernetes_version = "1.28"

# Node groups otimizados para produção
node_instance_types = ["m5.large", "m5.xlarge", "c5.large"]  # Instâncias otimizadas
min_nodes_per_zone  = 2  # Mínimo 2 por zona para HA
max_nodes_per_zone  = 10  # Scale up significativo
desired_nodes_per_zone = 3  # 3 por zona = 9 nodes total

# Storage otimizado para produção
disk_size_gb = 100

# Features do cluster habilitadas
enable_cluster_autoscaler      = true
enable_load_balancer_controller = true
enable_private_endpoint        = true
enable_public_endpoint         = false  # Apenas acesso privado em prod

# Acesso público restrito - apenas IPs corporativos
public_access_cidrs = [
  "203.0.113.0/24",    # Escritório principal
  "198.51.100.0/24"    # VPN corporativa
]

# Logs completos habilitados para auditoria
enabled_log_types = [
  "api",
  "audit",
  "authenticator",
  "controllerManager",
  "scheduler"
]

# Configurações do container registry para produção
registry_name = "neural-hive-prod"

# Repositórios de produção
repository_names = [
  "cognitive-processor",
  "orchestration-engine",
  "execution-agent",
  "memory-store",
  "event-bus"
]

# Security scanning rigoroso em produção
enable_vulnerability_scanning = true
block_critical_vulnerabilities = true
critical_severity_threshold = 0  # Zero vulnerabilidades críticas

# Tags imutáveis em produção
image_tag_mutability = "IMMUTABLE"

# Retenção maior para produção
image_retention_count = 50
untagged_retention_days = 1  # Limpeza rápida de untagged

# Image signing obrigatório em produção
enable_image_signing = true

# Registries permitidos mais restritivos em produção
allowed_registries = [
  "public.ecr.aws/",
  "k8s.gcr.io/",
  "registry.k8s.io/"
]

# Tags obrigatórias para governança e compliance
tags = {
  Environment = "production"
  Project     = "neural-hive-mind"
  Owner       = "platform-team"
  CostCenter  = "neural-hive-operations"
  Compliance  = "required"
  Purpose     = "neural-hive-foundation"

  # Tags de compliance
  DataClassification = "confidential"
  SecurityLevel      = "high"
  BackupRequired     = "true"
  MonitoringRequired = "critical"

  # Tags de governance
  ChangeManagement = "required"
  MaintenanceWindow = "sunday-0200-0600-utc"
  SLA = "99.9"
  DisasterRecovery = "cross-region"

  # Tags de automação
  AutoShutdown = "disabled"
  BackupPolicy = "comprehensive"
  MonitoringLevel = "critical"
  AlertEscalation = "oncall-primary"

  # Tags de auditoria
  CreatedBy      = "terraform"
  CreatedDate    = "2024-01-15"
  LastUpdated    = "2024-01-15"
  ReviewRequired = "quarterly"
  ComplianceAudit = "soc2-pci"

  # Tags de operação
  MaintenanceTeam = "platform-ops"
  OnCallGroup     = "neural-hive-sre"
  Documentation   = "confluence.company.com/neural-hive"
  RunbookLocation = "oncall-wiki/neural-hive-runbooks"

  # Tags de business
  BusinessUnit = "ai-platform"
  CostAllocation = "neural-hive-prod"
  BillingAccount = "ai-platform-prod"
  ProfitCenter   = "artificial-intelligence"
}

# Configurações da Camada de Memória - Prod

# MongoDB Configuration - Prod
mongodb_version = "7.0.5"
# mongodb_root_password deve ser definido via AWS Secrets Manager ou variável de ambiente

# Neo4j Configuration - Prod
neo4j_version = "5.15.0"
# neo4j_password deve ser definido via AWS Secrets Manager ou variável de ambiente

# ClickHouse Configuration - Prod
clickhouse_version = "23.8"
# Senhas devem ser gerenciadas via AWS Secrets Manager ou variáveis de ambiente seguras

# StorageClass para camada de memória
storage_class = "gp3-ssd"