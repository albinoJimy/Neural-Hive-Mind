# Configuração Principal - Neural Hive-Mind Infrastructure

# Dados locais para reutilização
locals {
  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
      Project     = "neural-hive-mind"
      ManagedBy   = "terraform"
      CreatedBy   = "root-infrastructure"
    }
  )
}

# Módulo de Rede
module "network" {
  source = "./modules/network"

  # Configurações gerais
  name_prefix = var.name_prefix
  environment = var.environment
  tags        = local.common_tags

  # Configurações de rede
  vpc_cidr                  = var.vpc_cidr
  availability_zones        = var.availability_zones
  public_subnet_cidrs       = var.public_subnet_cidrs
  private_subnet_cidrs      = var.private_subnet_cidrs
  enable_nat_gateway        = var.enable_nat_gateway
  enable_vpc_endpoints      = var.enable_vpc_endpoints
  enable_flow_logs         = var.enable_flow_logs
  flow_logs_retention_days = var.flow_logs_retention_days

  # Garante que a descoberta de subnets do EKS funcione
  cluster_name = var.cluster_name
}

# Módulo Cluster Kubernetes
# Definido primeiro pois o container-registry depende dos outputs do cluster
module "k8s-cluster" {
  source = "./modules/k8s-cluster"

  # Configurações gerais
  name_prefix = var.name_prefix
  environment = var.environment
  tags        = local.common_tags

  # Configurações de rede (conectar com módulo network)
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  public_subnet_ids  = module.network.public_subnet_ids

  # Parâmetro obrigatório que estava faltando - zonas de disponibilidade
  availability_zones = var.availability_zones

  # Configurações do cluster
  cluster_name                    = var.cluster_name
  kubernetes_version              = var.kubernetes_version
  enable_private_endpoint         = var.enable_private_endpoint
  enable_public_endpoint          = var.enable_public_endpoint
  public_access_cidrs            = var.public_access_cidrs
  enabled_log_types              = var.enabled_log_types

  # Configurações dos nós
  node_instance_types            = var.node_instance_types
  min_nodes_per_zone            = var.min_nodes_per_zone
  max_nodes_per_zone            = var.max_nodes_per_zone
  desired_nodes_per_zone        = var.desired_nodes_per_zone
  disk_size_gb                  = var.disk_size_gb

  # Add-ons
  enable_cluster_autoscaler      = var.enable_cluster_autoscaler
  enable_load_balancer_controller = var.enable_load_balancer_controller
}

# Módulo Container Registry
# Depende do cluster K8s para configurações OIDC
module "container-registry" {
  source = "./modules/container-registry"

  # Configurações gerais
  environment = var.environment
  tags        = local.common_tags

  # Configurações do registry
  registry_name                   = var.registry_name
  repository_names               = var.repository_names
  enable_vulnerability_scanning  = var.enable_vulnerability_scanning
  block_critical_vulnerabilities = var.block_critical_vulnerabilities
  critical_severity_threshold    = var.critical_severity_threshold
  image_tag_mutability          = var.image_tag_mutability
  image_retention_count         = var.image_retention_count
  untagged_retention_days       = var.untagged_retention_days
  enable_image_signing          = var.enable_image_signing

  # Configurações OIDC - populadas após criação do cluster
  oidc_provider_arn = module.k8s-cluster.oidc_provider_arn
  oidc_issuer_url   = module.k8s-cluster.oidc_issuer_url
  signing_namespace = var.signing_namespace
}

# Módulo Sigstore IRSA
# Configura IAM Role for Service Account para Sigstore Policy Controller
module "sigstore-irsa" {
  source = "./modules/sigstore-irsa"

  # Dependências do cluster K8s
  cluster_name      = var.cluster_name
  oidc_provider_arn = module.k8s-cluster.oidc_provider_arn
  oidc_provider_url = module.k8s-cluster.oidc_issuer_url

  # Configurações do service account
  namespace            = "cosign-system"
  service_account_name = "sigstore-policy-controller"

  # Tags comuns
  tags = local.common_tags

  # Garantir que o cluster seja criado antes
  depends_on = [module.k8s-cluster]
}

# Módulo MongoDB Cluster
# Camada de memória operacional (30 dias de retenção)
module "mongodb_cluster" {
  source = "./modules/mongodb-cluster"

  cluster_name    = "neural-hive-mongodb-${var.environment}"
  namespace       = "mongodb-cluster"
  mongodb_version = var.mongodb_version
  replica_count   = var.environment == "prod" ? 3 : 3  # Mínimo 3 sempre
  storage_size    = var.environment == "prod" ? "100Gi" : "20Gi"
  storage_class   = var.storage_class

  root_password  = var.mongodb_root_password
  tls_enabled    = true
  backup_enabled = var.environment == "prod"

  common_labels = {
    environment = var.environment
    project     = "neural-hive-mind"
  }
  environment = var.environment

  depends_on = [module.k8s-cluster]
}

# Módulo Neo4j Cluster
# Knowledge Graph semântico
module "neo4j_cluster" {
  source = "./modules/neo4j-cluster"

  cluster_name  = "neural-hive-neo4j-${var.environment}"
  namespace     = "neo4j-cluster"
  neo4j_version = var.neo4j_version
  edition       = "community" # MVP com community, migrar para enterprise depois
  core_servers  = var.environment == "prod" ? 3 : 3
  read_replicas = var.environment == "prod" ? 2 : 1

  core_storage_size    = var.environment == "prod" ? "100Gi" : "20Gi"
  replica_storage_size = var.environment == "prod" ? "50Gi" : "10Gi"
  storage_class        = var.storage_class

  neo4j_password  = var.neo4j_password
  tls_enabled     = true
  plugins_enabled = ["apoc", "graph-data-science", "neosemantics"]
  backup_enabled  = var.environment == "prod"

  common_labels = {
    environment = var.environment
    project     = "neural-hive-mind"
  }
  environment = var.environment

  depends_on = [module.k8s-cluster]
}

# Módulo ClickHouse Cluster
# Analytics histórico (18 meses de retenção)
module "clickhouse_cluster" {
  source = "./modules/clickhouse-cluster"

  cluster_name       = "neural-hive-clickhouse-${var.environment}"
  namespace          = "clickhouse-cluster"
  clickhouse_version = var.clickhouse_version
  shards             = var.environment == "prod" ? 3 : 2
  replicas           = var.environment == "prod" ? 2 : 2

  storage_size  = var.environment == "prod" ? "200Gi" : "30Gi"
  storage_class = var.storage_class

  admin_password    = var.clickhouse_admin_password
  readonly_password = var.clickhouse_readonly_password
  writer_password   = var.clickhouse_writer_password

  tls_enabled    = true
  ttl_days       = 540 # 18 meses conforme documento 08
  backup_enabled = var.environment == "prod"

  common_labels = {
    environment = var.environment
    project     = "neural-hive-mind"
  }
  environment = var.environment

  depends_on = [module.k8s-cluster]
}