# Sub-Spec: Epic L - Multi-região Deploy

## Objetivo

Configurar Terraform e Kubernetes para deploy multi-região do Neural Hive-Mind em 2+ regiões.

## Componentes

### 1. Terraform Multi-Region Configuration (NOVO)
**Diretório:** `infrastructure/terraform/environments/`

**Arquivos:**
- `prod-us-east-1/` - Configuração região primária (US East)
- `prod-us-west-2/` - Configuração região secundária (US West)
- `prod-eu-west-1/` - Configuração região terciária (Europa)

**Funcionalidades:**
- VPCs peering entre regiões
- Route53 hosted zones para DNS global
- Replicação de dados cross-region

```hcl
# prod-us-east-1/main.tf
module "vpc" {
  source = "../../../modules/vpc"
  region = "us-east-1"
  cidr = "10.0.0.0/16"
}

module "kubernetes_cluster" {
  source = "../../../modules/kubernetes-cluster"
  region = "us-east-1"
  cluster_name = "neural-hive-east"

  node_pools = {
    general = {
      min_size = 3
      max_size = 10
      instance_types = ["t3.xlarge"]
    }
  }
}

# DNS global
module "route53" {
  source = "../../../modules/route53"
  domain_name = "neural-hive.com"

  records = {
    "api" = {
      type = "CNAME"
      ttl = 60
      records = ["api-east.neural-hive.com", "api-west.neural-hive.com"]
      health_check = true
    }
  }
}
```

### 2. Kubernetes Multi-Cluster (NOVO)
**Diretório:** `k8s/multi-region/`

**Arquivos:**
- `context-east.yaml` - Configuração cluster US East
- `context-west.yaml` - Configuração cluster US West
- `context-eu.yaml` - Configuração cluster Europa

**Funcionalidades:**
- Contexts kubeconfig para cada cluster
- Service mesh entre regiões (Istio multi-cluster)
- Failover automático

```yaml
# context-east.yaml
apiVersion: v1
kind: Config
clusters:
  - name: neural-hive-east
    cluster:
      server: https://east.kubernetes.neural-hive.com
contexts:
  - name: neural-hive-east
    context:
      cluster: neural-hive-east
      user: neural-hive-admin
```

**Istio Multi-Cluster:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: istio-remote-secret-east
  namespace: istio-system
stringData:
  east.kubernetes.neural-hive.com: |
    apiVersion: v1
    clusters:
      - name: neural-hive-east
        cluster:
          certificate-authority-data: LS0tLS1...
```

### 3. Database Replication
**Arquivos:** `infrastructure/terraform/modules/database/`

**MongoDB Replica Set:**
```hcl
module "mongodb_replica_set" {
  source = "../mongodb"

  primary_region = "us-east-1"
  secondary_regions = ["us-west-2", "eu-west-1"]

  members = [
    {
      region = "us-east-1"
      node_type = "M50"
      priority = 1
    },
    {
      region = "us-west-2"
      node_type = "M50"
      priority = 2
    },
    {
      region = "eu-west-1"
      node_type = "M50"
      priority = 3
    }
  ]
}
```

**Redis Cluster:**
```hcl
module "redis_cluster" {
  source = "../redis"

  regions = ["us-east-1", "us-west-2", "eu-west-1"]

  cluster_mode = true
  shard_count = 3
  replicas_per_shard = 2
}
```

## Failover Automático

### Global Load Balancer
- Route53 latency-based routing
- Health checks ativos/passivos
- Automatic failover se região cair

### Service Mesh
- Istio multi-cluster mesh
- Traffic splitting por região
- Circuit breaker entre regiões

## Deploy Multi-Região

### 1. Setup Terraform
```bash
cd infrastructure/terraform/environments/prod-us-east-1
terraform init
terraform apply

cd ../prod-us-west-2
terraform init
terraform apply

cd ../prod-eu-west-1
terraform init
terraform apply
```

### 2. Setup Kubernetes Clusters
```bash
# Criar contextos
kubectl config use-context neural-hive-east
kubectl config use-context neural-hive-west
kubectl config use-context neural-hive-eu
```

### 3. Deploy Services
```bash
# Deploy em todas as regiões
kubectl apply -f services/gateway-intencoes/k8s/ --context=neural-hive-east
kubectl apply -f services/gateway-intencoes/k8s/ --context=neural-hive-west
kubectl apply -f services/gateway-intencoes/k8s/ --context=neural-hive-eu
```

### 4. Configure DNS
```bash
# Configurar Route53 para latency-based routing
terraform apply infrastructure/terraform/environments/route53/
```

### 5. Testar Failover
```bash
# Simular falha de região
kubectl scale deployment -n neural-hive-east --replicas=0

# Verificar traffic redirecionado
curl http://api.neural-hive.com/health
# Deve responder de outra região
```

## Verificação

```bash
# Verificar VPCs peering
aws ec2 describe-vpc-peering-connections

# Verificar Route53
aws route53 list-hosted-zones

# Verificar clusters
kubectl config get-contexts

# Verificar Istio mesh
istioctl mc remote list

# Testar failover
kubectl config use-context neural-hive-east
kubectl delete pod -n neural-hive -l app=gateway

# Verificar DNS
curl http://api.neural-hive.com/health
```

## Checklist

- [ ] VPCs criadas em 3 regiões
- [ ] VPC peering configurado
- [ ] Kubernetes clusters criados
- [ ] Route53 hosted zones configuradas
- [ ] MongoDB replica set configurado
- [ ] Redis cluster configurado
- [ ] Istio multi-cluster configurado
- [ ] Services deployados em 3 regiões
- [ ] Failover automático testado
- [ ] Latency-based routing testado
