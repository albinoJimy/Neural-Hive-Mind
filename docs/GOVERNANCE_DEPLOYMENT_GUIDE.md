# Guia de Deployment - Governança e Compliance
## Neural Hive-Mind Fase 1

---

## Visão Geral

Este guia descreve o processo de deployment da camada de governança do Neural Hive-Mind, incluindo OPA Gatekeeper, políticas de compliance, validação de integridade do ledger cognitivo, e geração de relatórios de compliance.

## Componentes

### 1. OPA Gatekeeper
- **Policy Engine**: Validação de políticas via admission webhooks
- **Audit**: Auditoria contínua de recursos existentes
- **Enforcement Modes**: warn (log only) → deny (block)

### 2. Políticas de Compliance
- **Resource Limits**: Todos os containers devem ter limits/requests
- **Data Governance**: Labels obrigatórias (data-owner, classification, sla-tier)
- **mTLS Required**: PeerAuthentication STRICT (Fase 2)
- **Image Signature**: Validação de assinaturas Sigstore (Fase 2)

### 3. Ledger Cognitivo
- **Integridade**: Hash SHA-256 em todos os registros
- **Explicabilidade**: Token único para cada decisão
- **Imutabilidade**: Flag immutable=true
- **Auditoria**: 100% dos registros auditáveis

### 4. Feromônios Digitais
- **Comunicação**: Coordenação de enxame via Redis
- **Decay**: Temporal com taxa de 10%/hora
- **TTL**: 3600s (1 hora)

## Deployment - Ambiente Local

### Passo 1: Verificar Pré-requisitos

```bash
# Verificar cluster
kubectl cluster-info

# Verificar infraestrutura
kubectl get pods -n mongodb-cluster
kubectl get pods -n redis-cluster
kubectl get pods -n neural-hive-observability

# Verificar ferramentas
which helm jq mongosh redis-cli
```

### Passo 2: Deploy OPA Gatekeeper

```bash
# Executar script automatizado
./scripts/deploy/deploy-opa-gatekeeper-local.sh

# OU deploy manual:
helm repo add gatekeeper https://open-policy-agent.github.io/gatekeeper/charts
helm repo update

helm upgrade --install opa-gatekeeper ./helm-charts/opa-gatekeeper \
  --namespace opa-gatekeeper \
  --create-namespace \
  --values environments/dev/helm-values/opa-gatekeeper-values.yaml \
  --wait --timeout=10m
```

### Passo 3: Aplicar Políticas

```bash
# Aplicar ConstraintTemplates
kubectl apply -f policies/constraint-templates/

# Aguardar processamento
sleep 30

# Verificar templates
kubectl get constrainttemplates

# Aplicar Constraints (apenas aplicáveis para Fase 1)
kubectl apply -f policies/constraints/data-governance-validation.yaml
kubectl apply -f policies/constraints/enforce-resource-limits.yaml

# Verificar constraints
kubectl get constraints -A
```

### Passo 4: Validar Deployment

```bash
# Executar validação de políticas
./scripts/validation/validate-policy-enforcement.sh

# Verificar violações
kubectl get constraints -A -o custom-columns=NAME:.metadata.name,VIOLATIONS:.status.totalViolations
```

**Resultado esperado**: 0 violações deny, <20 violações warn

### Passo 5: Executar Teste de Governança

```bash
# Executar teste completo
./tests/governance-compliance-test.sh

# Verificar relatórios gerados
ls -la tests/results/governance-compliance-*
```

### Passo 6: Gerar Relatório Executivo

```bash
# Gerar relatório consolidado
./scripts/governance/generate-compliance-report.sh \
  --input-json tests/results/governance-compliance-report-<timestamp>.json

# Visualizar relatório
cat tests/results/GOVERNANCE_COMPLIANCE_EXECUTIVE_REPORT.md
```

## Validações Manuais

### Verificar Integridade do Ledger

```bash
# Executar script de verificação
./scripts/governance/verify-ledger-integrity.sh

# OU verificar manualmente via Python
python3 scripts/governance/verify-hash-integrity.py \
  --mongo-uri "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin" \
  --database neural_hive \
  --collection consensus_decisions \
  --sample-size 10
```

### Consultar Feromônios

```bash
# Listar feromônios
REDIS_POD=$(kubectl get pods -n redis-cluster -l app=redis -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli KEYS 'pheromone:*'

# Ver feromônio específico
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli GET 'pheromone:business:workflow-analysis:success'
```

### Verificar Métricas de Governança

```bash
# Port-forward Prometheus
kubectl port-forward -n neural-hive-observability svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090 &

# Auditability Score
curl -s 'http://localhost:9090/api/v1/query?query=(rate(neural_hive_ledger_writes_total[5m])/(rate(neural_hive_ledger_writes_total[5m])+0.01))*100' | jq .

# Compliance Score
curl -s 'http://localhost:9090/api/v1/query?query=(1-(sum(gatekeeper_constraint_violations{enforcement_action="deny"})/(sum(gatekeeper_constraint_violations)+1)))*100' | jq .

# Matar port-forward
kill %1
```

## Troubleshooting

### Problema 1: OPA Gatekeeper em CrashLoopBackOff

**Diagnóstico**:
```bash
kubectl logs -n opa-gatekeeper -l gatekeeper.sh/operation=webhook --previous
kubectl describe pod -n opa-gatekeeper -l gatekeeper.sh/operation=webhook
```

**Soluções**:
- Verificar recursos disponíveis (CPU/RAM)
- Verificar se CRDs foram instalados corretamente
- Verificar logs por erros de certificado TLS

### Problema 2: ConstraintTemplate não aceito

**Diagnóstico**:
```bash
kubectl describe constrainttemplate <template-name>
kubectl logs -n opa-gatekeeper -l gatekeeper.sh/operation=webhook | grep -i error
```

**Soluções**:
- Verificar sintaxe Rego (usar `opa test` localmente)
- Verificar schema OpenAPI v3
- Verificar compatibilidade com versão do Gatekeeper

### Problema 3: Hashes Inválidos no Ledger

**Diagnóstico**:
```bash
python3 scripts/governance/verify-hash-integrity.py --collection consensus_decisions --sample-size 100
```

**Soluções**:
- Identificar registros com hash inválido
- Verificar se algoritmo de hash mudou
- Investigar adulteração de dados
- Restaurar de backup se necessário

### Problema 4: Explicabilidade Ausente

**Diagnóstico**:
```bash
# Verificar feature flag
kubectl get configmap -n consensus-engine consensus-engine-config -o yaml | grep enable_explainability

# Verificar logs
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine | grep explainability
```

**Soluções**:
- Habilitar feature flag se desabilitado
- Verificar conectividade com MongoDB
- Regenerar tokens ausentes (backfill)

## SLOs de Governança

| SLO | Target | Métrica Prometheus |
|-----|--------|--------------------|
| Auditabilidade | 100% | `neural_hive_ledger_writes_total` |
| Explicabilidade | 100% | `neural_hive_explainability_tokens_generated_total / neural_hive_consensus_decisions_total` |
| Divergência | <5% | `histogram_quantile(0.95, neural_hive_specialist_divergence_bucket)` |
| Confiança Agregada | ≥0.8 | `histogram_quantile(0.50, neural_hive_aggregated_confidence_bucket)` |
| Latência Consenso | <120ms | `histogram_quantile(0.95, neural_hive_consensus_duration_seconds_bucket)` |
| Fallback Rate | <3% | `rate(neural_hive_fallback_decisions_total[5m]) / rate(neural_hive_consensus_decisions_total[5m])` |
| Compliance | 100% | `1 - (sum(gatekeeper_constraint_violations{enforcement_action="deny"}) / sum(gatekeeper_constraint_violations))` |

## Comandos Úteis

### Verificar OPA Gatekeeper
```bash
# Status dos pods
kubectl get pods -n opa-gatekeeper

# Logs do webhook
kubectl logs -n opa-gatekeeper -l gatekeeper.sh/operation=webhook --tail=100

# Logs do audit
kubectl logs -n opa-gatekeeper -l gatekeeper.sh/operation=audit --tail=100

# Verificar webhook configurado
kubectl get validatingwebhookconfigurations gatekeeper-validating-webhook-configuration

# Verificar CRDs
kubectl get crd | grep gatekeeper
```

### Verificar ConstraintTemplates e Constraints
```bash
# Listar templates
kubectl get constrainttemplates

# Detalhar template específico
kubectl describe constrainttemplate neuralhivemtlsrequired

# Listar constraints
kubectl get constraints -A

# Verificar violações de constraint específico
kubectl get resourcelimitsrequired.constraints.gatekeeper.sh enforce-resource-limits -o yaml

# Extrair total de violações
kubectl get constraints -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.totalViolations}{"\n"}{end}'
```

### Consultar Ledger Cognitivo (MongoDB)
```bash
# Conectar ao MongoDB
MONGO_POD=$(kubectl get pods -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n mongodb-cluster $MONGO_POD -- \
  mongosh --username root --password local_dev_password --authenticationDatabase admin --eval "
    use neural_hive;

    // Total de registros
    print('cognitive_ledger:', db.cognitive_ledger.countDocuments({}));
    print('consensus_decisions:', db.consensus_decisions.countDocuments({}));
    print('explainability_ledger:', db.explainability_ledger.countDocuments({}));

    // Registros com hash
    print('Decisões com hash:', db.consensus_decisions.countDocuments({hash: {\$exists: true, \$ne: ''}}));

    // Decisões com explainability_token
    print('Decisões com token:', db.consensus_decisions.countDocuments({explainability_token: {\$exists: true, \$ne: ''}}));

    // Decisões imutáveis
    print('Decisões imutáveis:', db.consensus_decisions.countDocuments({immutable: true}));
  "
```

### Consultar Feromônios (Redis)
```bash
# Conectar ao Redis
REDIS_POD=$(kubectl get pods -n redis-cluster -l app=redis -o jsonpath='{.items[0].metadata.name}')

# Listar todos os feromônios
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli KEYS 'pheromone:*'

# Contar feromônios
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli KEYS 'pheromone:*' | wc -l

# Ver feromônio específico
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli GET 'pheromone:business:workflow-analysis:success'

# Verificar TTL
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli TTL 'pheromone:business:workflow-analysis:success'

# Listar feromônios de um specialist
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli KEYS 'pheromone:business:*'
```

### Consultar Métricas de Governança (Prometheus)
```bash
# Port-forward Prometheus
kubectl port-forward -n neural-hive-observability svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090 &
PF_PID=$!

# Auditability Score
curl -s 'http://localhost:9090/api/v1/query?query=(rate(neural_hive_ledger_writes_total[5m])/(rate(neural_hive_ledger_writes_total[5m])+0.01))*100' | jq -r '.data.result[0].value[1]'

# Explainability Coverage
curl -s 'http://localhost:9090/api/v1/query?query=(rate(neural_hive_explainability_tokens_generated_total[5m])/(rate(neural_hive_consensus_decisions_total[5m])+0.01))*100' | jq -r '.data.result[0].value[1]'

# Compliance Score
curl -s 'http://localhost:9090/api/v1/query?query=(1-(sum(gatekeeper_constraint_violations{enforcement_action="deny"})/(sum(gatekeeper_constraint_violations)+1)))*100' | jq -r '.data.result[0].value[1]'

# Violações OPA
curl -s 'http://localhost:9090/api/v1/query?query=sum(gatekeeper_constraint_violations)' | jq -r '.data.result[0].value[1]'

# Matar port-forward
kill $PF_PID
```

### Verificar Alertas de Governança
```bash
# Verificar PrometheusRule
kubectl get prometheusrule -n neural-hive-observability neural-hive-governance-alerts

# Listar alertas firing
kubectl port-forward -n neural-hive-observability svc/neural-hive-prometheus-kube-prometheus-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.neural_hive_layer=="governanca") | {alert: .labels.alertname, state: .state, value: .value}'
kill %1
```

### Aplicar Políticas Manualmente
```bash
# Aplicar ConstraintTemplates
kubectl apply -f policies/constraint-templates/

# Aguardar processamento
sleep 30

# Aplicar Constraints
kubectl apply -f policies/constraints/data-governance-validation.yaml
kubectl apply -f policies/constraints/enforce-resource-limits.yaml

# Verificar aplicação
kubectl get constrainttemplates
kubectl get constraints -A
```

### Testar Violação de Política
```bash
# Criar deployment sem resource limits (deve gerar violação)
kubectl create namespace policy-test
kubectl label namespace policy-test neural-hive.io/managed=true

cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-no-limits
  namespace: policy-test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    metadata:
      labels:
        app: test
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        # SEM resource limits/requests
EOF

# Aguardar audit
sleep 60

# Verificar violações
kubectl get resourcelimitsrequired.constraints.gatekeeper.sh enforce-resource-limits -o jsonpath='{.status.totalViolations}'

# Limpar
kubectl delete namespace policy-test
```

## Referências

- [Governance Operations Guide](./operations/governance-operations.md)
- [OPA Gatekeeper Documentation](https://open-policy-agent.github.io/gatekeeper/)
- [Documento 04 - Segurança e Governança](../documento-04-seguranca-governanca-neural-hive-mind.md)
- [Phase 1 Testing Guide](./PHASE1_TESTING_GUIDE.md)
- [Checklist de Deployment](../CHECKLIST_GOVERNANCE_DEPLOYMENT.md)
