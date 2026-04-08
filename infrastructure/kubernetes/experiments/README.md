# Safe Experimentation Environment (EXPERIMENT-001)

## Visão Geral

Este diretório contém os manifests Kubernetes para o ambiente isolado de experimentos do Neural-Hive-Mind.

**Componente:** Safe Experimentation Environment
**Especificação:** `docs/superpowers/specs/2026-04-07-fase4-evolucao/EXPERIMENT-001-safe-environment-spec.md`
**Data de Criação:** 2026-04-08

## Estrutura

```
infrastructure/kubernetes/experiments/
├── README.md                 # Este ficheiro
├── kustomization.yaml        # Configuração Kustomize
├── namespace.yaml            # Namespace nhm-experiments
├── resourcequota.yaml        # Quotas de recursos
├── networkpolicy.yaml        # Políticas de rede
├── limitrange.yaml           # Limites de recursos padrão
├── rbac.yaml                 # Controlo de acesso (RBAC)
└── secrets.yaml              # Gestão de secrets
```

## Recursos Implementados

### Namespace (`namespace.yaml`)
- **Nome:** `nhm-experiments`
- **Labels:** `environment=experiments`, `managed-by=nhm`, `component=safe-experimentation`, `tier=isolation`
- **Isolamento:** Namespace dedicado para experimentos

### ResourceQuota (`resourcequota.yaml`)
- **CPU:** requests=8, limits=12
- **Memória:** requests=16Gi, limits=24Gi
- **Pods:** máximo 20
- **PVCs:** máximo 5
- **Services:** máximo 10 (LoadBalancers=2, NodePorts=5)

### NetworkPolicy (`networkpolicy.yaml`)
- `experiments-deny-all` - Bloqueia todo o tráfego por padrão
- `experiments-allow-internal` - Permite comunicação entre pods do namespace
- `experiments-allow-dns` - Permite consultas DNS (UDP/TCP 53)
- `experiments-allow-nhm-services` - Permite acesso a Kafka, MongoDB, Redis
- `experiments-allow-internet` - Permite egress para internet (HTTPS/HTTP)
- `experiments-allow-monitoring` - Permite que Prometheus colete métricas

### LimitRange (`limitrange.yaml`)
- **Defaults:** CPU=100m, Memory=128Mi (requests)
- **Defaults:** CPU=500m, Memory=512Mi (limits)
- **Máximo:** CPU=2, Memory=4Gi por container
- **Máximo:** CPU=4, Memory=8Gi por pod
- **Limite Small:** CPU=200m/50m, Memory=256Mi/64Mi (limit/request)

### RBAC (`rbac.yaml`)
- **Roles:**
  - `experiments-admin` - Permissões completas (sem RBAC)
  - `experiments-viewer` - Apenas leitura
  - `experiments-executor` - Execução de experimentos
  - `experiments-secret-admin` - Gestão de secrets
- **ServiceAccount:** `experiment-pod`
- **RoleBindings:** Vinculação de grupos OIDC/LDAP às roles
- **ClusterRole:** `experiments-cluster-viewer` para recursos cluster-wide

### Secrets (`secrets.yaml`)
- **SecretStore:** Configuração para External Secrets Operator
- **ExternalSecrets:** API keys, credenciais de base de dados
- **SecretPolicy:** Políticas Kyverno para validação de secrets
- **CronJob:** Verificação de expiração de secrets
- **LimitRange:** Limites específicos para pods de sync de secrets

## Deploy

### Pré-requisitos
- Kubernetes 1.25+
- Kustomize 3.0+
- External Secrets Operator (opcional, para secrets.yaml)
- Kyverno (opcional, para políticas de secrets)

### Deploy com kubectl
```bash
cd infrastructure/kubernetes/experiments
kubectl apply -k .
```

### Deploy com Kustomize
```bash
kustomize build . | kubectl apply -f -
```

### Verificar Deploy
```bash
# Verificar namespace
kubectl get namespace nhm-experiments

# Verificar quotas
kubectl get resourcequota -n nhm-experiments

# Verificar network policies
kubectl get networkpolicy -n nhm-experiments

# Verificar limit ranges
kubectl get limitrange -n nhm-experiments

# Verificar RBAC
kubectl get role,rolebinding,serviceaccount -n nhm-experiments
```

## Ajuste de Quotas

As quotas podem ser ajustadas editando o ConfigMap `experiments-config`:

```bash
kubectl edit configmap experiments-config -n nhm-experiments
```

Ou editando o `resourcequota.yaml` diretamente antes do deploy.

## Testes

Os testes de integração estão localizados em:
```
tests/integration/experiments/
├── conftest.py               # Fixtures comuns
├── test_namespace.py         # Testes do namespace
├── test_resourcequota.py     # Testes de quotas
├── test_networkpolicy.py     # Testes de políticas de rede
├── test_limitrange.py        # Testes de limites de recursos
└── test_rbac.py              # Testes de RBAC
```

### Executar Testes
```bash
# Todos os testes de experimentos
pytest tests/integration/experiments/ -v -m integration -m k8s

# Teste específico
pytest tests/integration/experiments/test_namespace.py -v

# Testes com report de cobertura
pytest tests/integration/experiments/ --cov=tests/integration/experiments --cov-report=html
```

## Tickets Completos

- ✅ EXPERIMENT-001-01: Criar namespace `nhm-experiments` dedicado
- ✅ EXPERIMENT-001-02: Definir ResourceQuota para experiments
- ✅ EXPERIMENT-001-03: Criar NetworkPolicy para isolamento
- ✅ EXPERIMENT-001-04: Implementar LimitRange para pods
- ✅ EXPERIMENT-001-05: Criar RoleBinding para acesso específico
- ✅ EXPERIMENT-001-06: Isolar secrets por ambiente de experimento
- ✅ EXPERIMENT-001-07 a 10: Criar testes para manifests Kubernetes

## Próximos Passos

Os seguintes tickets (EXPERIMENT-001-11 a 28) ainda estão pendentes:

- Integração com ExperimentationEngine para criar namespace dinamicamente
- Notificação Kafka quando experimento é criado/destruído
- Métricas Prometheus de resource usage por namespace
- Spans OpenTelemetry para criação/destruição de namespace
- Logs estruturados para operações de namespace

## Troubleshooting

### Pods não escalonam
Verificar se a quota de pods foi atingida:
```bash
kubectl describe resourcequota experiments-quota -n nhm-experiments
```

### Tráfego bloqueado
Verificar as NetworkPolicies aplicadas:
```bash
kubectl get networkpolicy -n nhm-experiments -o yaml
```

### Permissões negadas
Verificar as Roles e RoleBindings:
```bash
kubectl get role,rolebinding -n nhm-experiments -o yaml
```

## Contacto

Para questões relacionadas a este ambiente:
- **Email:** nhm-platform-team@example.com
- **Spec:** `docs/superpowers/specs/2026-04-07-fase4-evolucao/EXPERIMENT-001-safe-environment-spec.md`
- **Ticket:** EXPERIMENT-001
