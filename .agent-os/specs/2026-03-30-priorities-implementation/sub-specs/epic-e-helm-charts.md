# Sub-Spec: Epic E - Helm Charts para Serviços Core

## Objetivo

Criar Helm charts para 6 serviços core (gateway-intencoes, consensus-engine, orchestrator-dynamic, approval-service, worker-agents, queen-agent) para facilitar deployment em Kubernetes.

## Padrão de Helm Chart

Cada Helm chart deve conter:

### Estrutura
```
services/{nome-do-servico}/helm/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml (opcional)
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── serviceaccount.yaml
│   ├── hpa.yaml (HorizontalPodAutoscaler)
│   ├── pdb.yaml (PodDisruptionBudget)
│   └── networkpolicy.yaml
└── templates/tests/
    └── test.yaml
```

### Componentes Obrigatórios

#### 1. Deployment
- Replicas: 2 (mínimo para HA)
- Resources limits/requests:
  - CPU: request=100m, limit=500m
  - Memory: request=256Mi, limit=512Mi
- Liveness/Readiness probes
- Image pull policy: IfNotPresent

#### 2. Service
- Type: ClusterIP (ou LoadBalancer para gateway)
- Ports: configuráveis via values.yaml

#### 3. ConfigMap
- Variáveis de ambiente não-sensíveis
- Configurações por ambiente (dev/staging/prod)

#### 4. Secret
- Variáveis de ambiente sensíveis (passwords, tokens)
- Montado como volumes ou env vars

#### 5. ServiceAccount
- RBAC configurado
- annotations para IRSA (AWS) ou Workload Identity (GKE)

#### 6. HPA (HorizontalPodAutoscaler)
- Min replicas: 2
- Max replicas: 10
- Target CPU: 70%
- Target Memory: 80%

#### 7. PDB (PodDisruptionBudget)
- Min available: 1
- Max unavailable: 25%

### Componentes Opcionais

#### Ingress (para serviços públicos)
- Host: configurável
- TLS: configurável
- Annotations para cert-manager

#### NetworkPolicy
- Default deny all ingress
- Allow from specific namespaces

## Serviços

### 1. gateway-intencoes
**Particularidades:**
- Service type: LoadBalancer
- Ingress: não necessário (LoadBalancer expõe diretamente)
- HPA: Max replicas 20 (alto tráfego)

### 2. consensus-engine
**Particularidades:**
- HPA: Max replicas 5
- PDB: Min available 2 (quorum)

### 3. orchestrator-dynamic
**Particularidades:**
- HPA: Max replicas 10
- ConfigMap para Temporal server connection
- Secret para Temporal credentials

### 4. approval-service
**Particularidades:**
- HPA: Max replicas 5
- Secret para MLflow tracking
- ConfigMap para Active Learning toggle

### 5. worker-agents
**Particularidades:**
- HPA: Max replicas 20 (podem escalar muito)
- ServiceAccount com permissões especiais (Pod exec, patch)
- PDB: Min available 1

### 6. queen-agent
**Particularidades:**
- HPA: Não aplicável (apenas 1 réplica com leader election)
- PDB: Não aplicável
- ConfigMap para Redis connection (leader election)

## Exemplo: Chart.yaml

```yaml
apiVersion: v2
name: consensus-engine
description: Helm chart para Neural Hive Mind - Consensus Engine
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - neural-hive-mind
  - consensus
  - ai
maintainers:
  - name: Neural Hive Team
    email: team@neural-hive.com
```

## Exemplo: values.yaml

```yaml
# General
replicaCount: 2
image:
  repository: ghcr.io/neural-hive/consensus-engine
  tag: "1.0.0"
  pullPolicy: IfNotPresent

# Resources
resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 256Mi

# Autoscaling
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

# Pod Disruption Budget
podDisruptionBudget:
  enabled: true
  minAvailable: 2

# Service
service:
  type: ClusterIP
  port: 8002

# Config
config:
  ENVIRONMENT: "production"
  KAFKA_BOOTSTRAP_SERVERS: "kafka.neural-hive.svc.cluster.local:9092"
  MONGODB_URI: "mongodb://mongodb-0.mongo.neural-hive.svc.cluster.local:27017"

# Secrets
secrets:
  enabled: true
  mongodbPassword: "change-me"
```

## Verificação

```bash
# Validar Helm chart
helm lint helm/consensus-engine/

# Testar install (dry-run)
helm install consensus-engine helm/consensus-engine/ --dry-run --debug

# Install em test namespace
helm install consensus-engine helm/consensus-engine/ --namespace test --create-namespace

# Verificar deployment
kubectl get deployment consensus-engine -n test

# Verificar HPA
kubectl get hpa -n test

# Verificar PDB
kubectl get pdb -n test

# Testar upgrade
helm upgrade consensus-engine helm/consensus-engine/ --namespace test

# Uninstall
helm uninstall consensus-engine -n test
```

## Checklist por Serviço

- [ ] Chart.yaml criado
- [ ] values.yaml criado
- [ ] deployment.yaml criado
- [ ] service.yaml criado
- [ ] configmap.yaml criado
- [ ] secret.yaml criado
- [ ] serviceaccount.yaml criado
- [ ] hpa.yaml criado
- [ ] pdb.yaml criado
- [ ] test.yaml criado
- [ ] Helm chart testado (helm lint + install)
