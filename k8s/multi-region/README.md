# Neural Hive-Mind - Deploy Multi-Região

## Visão Geral

Este documento descreve a arquitetura e procedimentos para deploy do Neural Hive-Mind em multi-região (3 regiões AWS).

### Regiões Configuradas

| Região | Papel | CIDR | Cluster EKS |
|--------|-------|------|-------------|
| us-east-1 | Primária | 10.0.0.0/16 | neural-hive-east |
| us-west-2 | Secundária | 10.1.0.0/16 | neural-hive-west |
| eu-west-1 | Terciária (GDPR) | 10.2.0.0/16 | neural-hive-eu |

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                         Route53 Global DNS                      │
│                   (Latency + Failover Routing)                  │
└─────────────────────────────────────────────────────────────────┘
         │                              │                          │
         ▼                              ▼                          ▼
┌──────────────────┐        ┌──────────────────┐       ┌──────────────────┐
│   us-east-1      │◄───────│   us-west-2      │◄──────│   eu-west-1      │
│   (Primary)      │        │   (Secondary)    │       │   (GDPR)         │
└──────────────────┘        └──────────────────┘       └──────────────────┘
│                  │        │                  │       │                  │
│ ┌──────────────┐ │        │ ┌──────────────┐ │       │ ┌──────────────┐ │
│ │EKS:          │ │        │ │EKS:          │ │       │ │EKS:          │ │
│ │east          │ │        │ │west          │ │       │ │eu            │ │
│ │Node pools:   │ │        │ │Node pools:   │ │       │ │Node pools:   │ │
│ │- general(3)  │ │        │ │- general(2)  │ │       │ │- general(2)  │ │
│ │- compute(2)  │ │        │ │- compute(1)  │ │       │ │- compliance(1)│
│ │- ml(1)       │ │        │ │              │ │       │ │              │ │
│ └──────────────┘ │        │ └──────────────┘ │       │ └──────────────┘ │
│                  │        │                  │       │                  │
│ ┌──────────────┐ │        │                  │       │                  │
│ │MongoDB       │ │        │                  │       │                  │
│ │Atlas Primary │ │────────┤ ◄────────────────┼───────┤ ◄───────────────│
│ │(Member 1)    │ │        │ Member 2         │       │ Member 3         │
│ └──────────────┘ │        │                  │       │                  │
│                  │        │                  │       │                  │
│ ┌──────────────┐ │        │ ┌──────────────┐ │       │ ┌──────────────┐ │
│ │Redis         │ │────────┤ │Redis          │ │───────┤ │Redis          │ │
│ │Primary       │ │        │ │Secondary      │ │       │ │Secondary      │ │
│ │(Global DS)   │ │        │ │               │ │       │ │               │ │
│ └──────────────┘ │        │ └──────────────┘ │       │ └──────────────┘ │
└──────────────────┘        └──────────────────┘       └──────────────────┘
         │                              │                          │
         └────────────── VPC Peering ─────────────────────────────┘
```

## Pré-requisitos

### Ferramentas Necessárias
- Terraform >= 1.5.0
- kubectl >= 1.28
- awscli >= 2.0
- helm >= 3.0
- istioctl >= 1.20

### Permissões AWS
- AdministratorAccess (ou policy específica)
- Permissões para EKS, VPC, Route53, ElastiCache, MongoDB Atlas

## Procedimento de Deploy

### 1. Configurar Variáveis de Ambiente

```bash
export TF_STATE_BUCKET=neural-hive-mind-terraform-state
export AWS_PROFILE=seu-profile
export DOMAIN_NAME=neural-hive.com
export MONGODB_ATLAS_PROJECT_ID=seu-project-id
export MONGODB_ATLAS_PUBLIC_KEY=sua-public-key
export MONGODB_ATLAS_PRIVATE_KEY=seu-private-key
```

### 2. Deploy Infraestrutura Terraform

```bash
# Região primária
cd infrastructure/terraform/environments/prod-us-east-1
terraform init
terraform apply

# Capturar outputs
terraform output -json > ../outputs-east.json

# Repetir para outras regiões
cd ../prod-us-west-2
terraform init
terraform apply

cd ../prod-eu-west-1
terraform init
terraform apply
```

### 3. Configurar Contexts Kubernetes

```bash
./k8s/multi-region/deploy-multi-region.sh contexts
```

### 4. Instalar Istio Multi-Cluster

```bash
./k8s/multi-region/deploy-multi-region.sh istio
```

### 5. Deploy Aplicações

```bash
# Deploy completo
./k8s/multi-region/deploy-multi-region.sh deploy

# Ou deploy regiões individualmente
for region in east west eu; do
    kubectl config use-context neural-hive-$region
    helm install neural-hive-mind ../../helm-charts/neural-hive-mind \
        --namespace neural-hive-mind \
        --set global.region=$region
done
```

## Failover e Recuperação de Desastre

### Failover Automático

O sistema utiliza:
- **Route53 Health Checks**: Verificação a cada 30s
- **Istio Circuit Breakers**: Detecção de falhas em 10s
- **MongoDB Atlas**: Auto-failover em < 60s
- **Redis Global Datastore**: Replicação < 1s

### Testar Failover

```bash
# Simular falha do primário
kubectl scale deployment gateway-intencoes \
    --context=neural-hive-east \
    --namespace neural-hive-mind \
    --replicas=0

# Verificar tráfego no secundário
kubectl get pods --context=neural-hive-west -n neural-hive-mind

# Restaurar
kubectl scale deployment gateway-intencoes \
    --context=neural-hive-east \
    --namespace neural-hive-mind \
    --replicas=3
```

### Comandos de Emergência

```bash
# Verificar saúde de todos os clusters
./k8s/multi-region/deploy-multi-region.sh health

# Promover secondary para primary
kubectl annotate node --context=neural-hive-west \
    --all failover.primary=true

# Rotear tráfego manualmente via Route53
aws route53 change-resource-record-sets \
    --hosted-zone $ZONE_ID \
    --change-batch file://failover-change.json
```

## Monitoramento

### Métricas Multi-Região

```bash
# Latência cross-region
istioctl proxy-status neural-hive-east

# Tráfego entre clusters
kubectl get servicestate --all-namespaces

# Health endpoints
curl https://api.neural-hive.com/health
curl https://api-west.neural-hive.com/health
curl https://api-eu.neural-hive.com/health
```

## Troubleshooting

### Problemas Conhecidos

1. **VPC Peering Não Conecta**
   ```bash
   # Verificar route tables
   aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID"
   ```

2. **MongoDB Replica Set Atrasado**
   ```bash
   # Verificar status
   mongosh "mongodb+srv://.../admin?replicaSet=rs0" --eval "db.adminCommand({replSetGetStatus: 1})"
   ```

3. **Istio Mesh Não Comunica**
   ```bash
   # Verificar secrets
   kubectl get secret --namespace=istio-system
   kubectl get secret istio-remote-secret-west -n istio-system -o yaml
   ```

## Estrutura de Arquivos Criados

### Terraform
```
infrastructure/terraform/
├── environments/
│   ├── prod-us-east-1/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── backend.tf
│   ├── prod-us-west-2/
│   │   └── (mesma estrutura)
│   └── prod-eu-west-1/
│       └── (mesma estrutura)
└── modules/
    ├── vpc_peering/
    ├── route53/
    ├── mongodb/
    └── redis/
```

### Kubernetes
```
k8s/multi-region/
├── context-east.yaml
├── context-west.yaml
├── context-eu.yaml
├── istio-multi-cluster.yaml
├── failover-policy.yaml
├── deploy-multi-region.sh
└── README.md (este arquivo)
```

## Referências

- [AWS EKS Multi-Region](https://docs.aws.amazon.com/eks/latest/userguide/multi-region.html)
- [Istio Multi-Cluster](https://istio.io/latest/docs/setup/install/multicluster/)
- [MongoDB Atlas Global Clusters](https://docs.atlas.mongodb.com/reference/global-clusters/)
- [ElastiCache Global Datastore](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/Redis-Global-Datastore.html)
