# Multi-Cloud Abstraction - Neural Hive-Mind

## Visão Geral

O módulo de abstração multi-cloud permite deploy do Neural Hive-Mind em AWS, Azure ou GCP usando a mesma configuração Terraform, eliminando vendor lock-in e facilitando expansão geográfica.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     cloud-abstraction (main.tf)                         │
│                    Interface genérica multi-cloud                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
    ┌───────▼────────┐     ┌────────▼────────┐     ┌───────▼────────┐
    │  AWS Submodule  │     │ Azure Submodule │     │  GCP Submodule │
    │                 │     │                 │     │                 │
    │ - VPC/EIP       │     │ - VNet/Subnet   │     │ - VPC/Subnet   │
    │ - EKS Cluster   │     │ - AKS Cluster   │     │ - GKE Cluster  │
    │ - IRSA/OIDC     │     │ - Workload ID   │     │ - Workload ID  │
    └─────────────────┘     └─────────────────┘     └─────────────────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │   Kubernetes Provider          │
                    │   (configurado dinamicamente)   │
                    └────────────────────────────────┘
```

## Estrutura de Diretórios

```
infrastructure/terraform/modules/cloud-abstraction/
├── main.tf                    # Factory pattern + provider selection
├── variables.tf               # Variáveis independentes de provider
├── outputs.tf                 # Outputs padronizados
└── submodules/
    ├── aws/                   # Implementação AWS
    │   ├── network/
    │   │   ├── main.tf        # VPC, Subnets, NAT Gateway
    │   │   ├── variables.tf
    │   │   └── outputs.tf
    │   └── cluster/
    │       ├── main.tf        # EKS Cluster
    │       ├── variables.tf
    │       └── outputs.tf
    ├── azure/                 # Implementação Azure
    │   ├── network/
    │   │   ├── main.tf        # VNet, Subnets, NAT Gateway
    │   │   ├── variables.tf
    │   │   └── outputs.tf
    │   └── cluster/
    │       ├── main.tf        # AKS Cluster
    │       ├── variables.tf
    │       └── outputs.tf
    └── gcp/                   # Implementação GCP (TODO)
        └── ...
```

## Uso

### Deploy em AWS

```hcl
module "neural_hive_mind_aws" {
  source = "./modules/cloud-abstraction"

  cloud_provider = "aws"
  environment    = "prod"
  region         = "us-east-1"
  cluster_name   = "neural-hive-prod"

  kubernetes_version = "1.28.0"
  vpc_cidr          = "10.0.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

  node_instance_types = ["t3.medium"]
  min_nodes_per_zone  = 1
  max_nodes_per_zone  = 3
  desired_nodes_per_zone = 1

  tags = {
    Project = "Neural Hive-Mind"
    Owner   = "Platform Team"
  }
}
```

### Deploy em Azure

```hcl
module "neural_hive_mind_azure" {
  source = "./modules/cloud-abstraction"

  cloud_provider = "azure"
  environment    = "prod"
  region         = "us-east-1"  # Mapeado para "eastus"
  cluster_name   = "neural-hive-prod-azure"

  kubernetes_version = "1.28.0"
  vpc_cidr          = "10.0.0.0/16"
  availability_zones = ["1", "2", "3"]

  node_instance_types = ["Standard_DS2_v2"]
  min_nodes_per_zone  = 1
  max_nodes_per_zone  = 3
  desired_nodes_per_zone = 1

  tags = {
    Project = "Neural Hive-Mind"
    Owner   = "Platform Team"
  }
}
```

### Deploy em GCP

```hcl
module "neural_hive_mind_gcp" {
  source = "./modules/cloud-abstraction"

  cloud_provider = "gcp"
  environment    = "prod"
  region         = "us-east-1"  # Mapeado para "us-east1"
  cluster_name   = "neural-hive-prod-gcp"

  kubernetes_version = "1.28.0"
  vpc_cidr          = "10.0.0.0/16"
  availability_zones = ["a", "b", "c"]

  node_instance_types = ["e2-medium"]
  min_nodes_per_zone  = 1
  max_nodes_per_zone  = 3
  desired_nodes_per_zone = 1

  tags = {
    project = "neural-hive-mind"
    owner   = "platform-team"
  }
}
```

## Mapeamento de Regiões

Cada provider tem convenções diferentes para nomes de regiões. O módulo faz o mapeamento automaticamente:

| AWS        | Azure        | GCP              |
|-----------|--------------|------------------|
| us-east-1 | eastus       | us-east1         |
| us-west-2 | westus2      | us-west2         |
| eu-west-1 | westeurope   | europe-west1     |
| eu-central-1 | germanywestcentral | europe-central1 |

## Mapeamento de Tipos de Instância

Tamanhos equivalentes de VM por provider:

| AWS           | Azure              | GCP        | vCPU | RAM  |
|--------------|--------------------|-----------|------|------|
| t3.medium    | Standard_DS2_v2    | e2-medium | 2    | 4GB  |
| t3.large     | Standard_DS3_v2    | e2-standard-2 | 2  | 8GB  |
| t3.xlarge    | Standard_DS4_v2    | e2-standard-4 | 4  | 16GB |
| m5.large     | Standard_E4_v3     | e2-highmem-4 | 2 | 32GB |

## Outputs Padronizados

Todos os providers retornam os mesmos outputs, garantindo consistência:

- `cluster_endpoint`: Endpoint da API do cluster
- `cluster_ca_certificate`: Certificado CA
- `cluster_name`: Nome do cluster
- `cluster_id`: ID único do cluster
- `vpc_id`: ID da VPC/VNet
- `private_subnet_ids`: Lista de IDs das subnets privadas
- `public_subnet_ids`: Lista de IDs das subnets públicas
- `node_security_group_id`: ID do security group dos nós
- `oidc_provider_arn`: ARN do provider OIDC (para IRSA)
- `oidc_provider_url`: URL do provider OIDC

## Migração entre Clouds

Para migrar de AWS para Azure (exemplo):

1. **Fazer backup do estado atual**
   ```bash
   terraform state pull > backup.tfstate
   ```

2. **Reconfigurar módulo para Azure**
   ```hcl
   cloud_provider = "azure"  # Era "aws"
   region = "eastus"         # Era "us-east-1"
   node_instance_types = ["Standard_DS2_v2"]  # Era ["t3.medium"]
   ```

3. **Aplicar mudança**
   ```bash
   terraform init
   terraform apply
   ```

## Diferenças por Provider

### AWS (EKS)
- **VPC**: Suporta 5 subnets privadas por AZ
- **IAM**: IRSA (IAM Roles for Service Accounts)
- **CNI**: AWS VPC CNI (um IP por pod)
- **Storage**: EBS, EFS, S3

### Azure (AKS)
- **VNet**: Suporta até 1000 subnets
- **Identity**: Workload Identity (Azure AD)
- **CNI**: Azure CNI ou kubenet
- **Storage**: Azure Disk, Azure Files, Blob

### GCP (GKE)
- **VPC**: Redes VPC globais
- **Identity**: Workload Identity (GCP IAM)
- **CNI**: GKE Dataplane V2 (eBPF)
- **Storage**: Persistent Disk, Filestore, Cloud Storage

## Limitações Atuais

1. **GCP**: Implementação pendente (EPIC-401-03)
2. **Storage**: Apenas volumes padrão, sem storage classes avançadas
3. **LB Controller**: AWS ALB apenas, outros providers pendentes
4. **Ingress**: NGINX default, cert-manager pendente

## Próximos Passos

1. Implementar módulo GCP (GKE)
2. Adicionar suporte para EKSAnywhere
3. Implementar storage classes avançadas por provider
4. Adicionar LB/Ingress controller por provider

## Referências

- [AWS EKS Documentation](https://docs.aws.amazon.com/eks/)
- [Azure AKS Documentation](https://docs.microsoft.com/azure/aks/)
- [GCP GKE Documentation](https://cloud.google.com/kubernetes-engine)
