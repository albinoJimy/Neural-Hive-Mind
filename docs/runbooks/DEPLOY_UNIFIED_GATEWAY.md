# Runbook: Deploy Unified Gateway

**Tipo:** Deploy / Operacional
**Severidade:** N/A (procedimento planeado)
**Componente:** Unified Gateway (`services/unified-gateway/`)
**Spec:** `.agent-os/specs/2026-05-01-unified-gateway-architecture/`
**Última atualização:** 2026-05-09

---

## Descrição

Este runbook cobre o procedimento de deploy do **Unified Gateway** em Kubernetes, incluindo serviços dependentes (`nlu-service`, `pii-service`), smoke tests, estratégia blue-green e rollback.

O Unified Gateway é o ponto de entrada unificado da plataforma Neural-Hive-Mind. Recebe pedidos no endpoint `POST /api/v1/nhm/request` e roteia para os gateways downstream (Flow A-F → `gateway-intencoes`, Flow G → `requirements-engineering`, Flow H → `doc-ingestion`) com base em classificação NLU.

## Pré-requisitos

Antes de iniciar o deploy, confirma os seguintes itens:

### 1. Imagem da Aplicação

- Imagem publicada no GHCR:
  - `ghcr.io/albinojimy/neural-hive-mind/unified-gateway:<tag>`
  - `ghcr.io/albinojimy/neural-hive-mind/nlu-service:<tag>`
  - `ghcr.io/albinojimy/neural-hive-mind/pii-service:<tag>`
- Tag corresponde ao commit/branch a deployar (ver `k8s/unified-gateway-deployment.yaml` linha `image:`).

### 2. Acesso ao Cluster Kubernetes

```bash
# Verificar contexto correto
kubectl config current-context

# Verificar permissões
kubectl auth can-i create deployments -n gateway
kubectl auth can-i create deployments -n nlu
kubectl auth can-i create deployments -n pii
```

### 3. Secrets e Dependências

- Secret `ghcr-secret` para imagePullSecrets nos namespaces `gateway`, `nlu` e `pii`:
  ```bash
  kubectl get secret ghcr-secret -n gateway
  kubectl get secret ghcr-secret -n nlu
  kubectl get secret ghcr-secret -n pii
  ```
- Secret `unified-gateway-secrets` com `MONGODB_USERNAME`, `MONGODB_PASSWORD`, `REDIS_PASSWORD`.
- Em produção, **JWT_SECRET** deve estar definido (não usar valor por defeito `change-me`).

### 4. Dependências Externas Acessíveis

| Dependência | Endereço esperado (cluster) | Verificação |
|-------------|------------------------------|-------------|
| Kafka | `neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092` | `kubectl get svc -n kafka` |
| Redis | `redis.redis-cluster.svc.cluster.local:6379` | `kubectl get svc -n redis-cluster` |
| MongoDB | `mongodb.mongodb-cluster.svc.cluster.local:27017` | `kubectl get svc -n mongodb-cluster` |
| Gateway Intenções (Flow A-F) | `gateway-intencoes:8000` | `kubectl get svc -n neural-hive` |
| Requirements Engineering (Flow G) | `requirements-engineering:8010` | `kubectl get svc -n neural-hive` |
| Doc Ingestion (Flow H) | `doc-ingestion:8018` | `kubectl get svc -n neural-hive` |

### 5. Pipeline CI/CD

- Branch alvo (main/staging) tem pipeline GitHub Actions verde.
- Build & push automático para GHCR foi concluído.

---

## Procedimento de Deploy

### 1. Build e Push da Imagem (CI/CD Automático)

O build é desencadeado por **commit + push** para o repositório:

```bash
git checkout main
git pull --rebase origin main
git push origin main
```

GitHub Actions trata de:
- Lint + tests
- Build da imagem Docker
- Push para GHCR com tag baseada no commit/branch

**Verificação:**

```bash
# Confirmar pipeline OK
gh run list --branch main --limit 5

# Confirmar imagem publicada
# (via UI do GHCR ou via crane/skopeo se disponível)
```

### 2. Aplicar Manifests Kubernetes

A ordem recomendada é deployar primeiro as dependências (NLU, PII) e só depois o gateway:

```bash
# 1. NLU Service (namespace nlu)
kubectl apply -f k8s/nlu-service-deployment.yaml

# 2. PII Service (namespace pii)
kubectl apply -f k8s/pii-service-deployment.yaml

# 3. Aguardar NLU e PII estarem ready
kubectl wait --for=condition=Available deployment/nlu-service -n nlu --timeout=180s
kubectl wait --for=condition=Available deployment/pii-service -n pii --timeout=180s

# 4. Unified Gateway (namespace gateway)
kubectl apply -f k8s/unified-gateway-deployment.yaml

# 5. Aguardar gateway ready
kubectl wait --for=condition=Available deployment/unified-gateway -n gateway --timeout=180s
```

### 3. Verificar Pods em Estado Ready

```bash
# Status dos pods (gateway)
kubectl get pods -n gateway -l app=unified-gateway

# Status dos pods (NLU e PII)
kubectl get pods -n nlu -l app=nlu-service
kubectl get pods -n pii -l app=pii-service

# Esperado: todos em Running, READY 1/1, RESTARTS 0
```

### 4. Smoke Tests Pós-Deploy

```bash
# 1. Port-forward para teste local
kubectl port-forward -n gateway svc/unified-gateway 7999:7999 &
PF_PID=$!

# 2. Health check (INV-10: deve devolver {status, version})
curl -s http://localhost:7999/health | jq

# Esperado:
# {
#   "status": "healthy",
#   "version": "1.0.0"
# }

# 3. Liveness e Readiness
curl -s http://localhost:7999/health/live | jq
curl -s http://localhost:7999/health/ready | jq

# 4. Métricas Prometheus expostas (default Python/process metrics + auto-instrumentation)
curl -s http://localhost:7999/metrics | head -30

# 5. Endpoint de capabilities (descobrimento)
curl -s http://localhost:7999/api/v1/nhm/capabilities | jq

# 6. Request E2E (com JWT se obrigatório - ajustar token)
curl -X POST http://localhost:7999/api/v1/nhm/request \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <jwt-token>" \
  -d '{
    "input": "Mostra-me o dashboard de vendas do último mês",
    "language": "pt"
  }' | jq

# Esperado: response com request_id, flow_type, status, processing_time_ms

# Cleanup port-forward
kill $PF_PID
```

---

## Estratégia Blue-Green (TICKET-035)

Conforme especificado em `[TICKET-035] Deploy produção (Blue-Green)`, o deploy em produção segue traffic shift gradual. A configuração atual define `replicas: 2` no deployment com HPA `minReplicas: 2` / `maxReplicas: 10`.

### Princípios

- **Zero downtime** durante a troca.
- **Rollback testado** antes do go-live.
- Traffic shift gradual: **10% → 50% → 100%**.

### Sequência (alto nível)

1. **Deploy "green" (nova versão)** ao lado da "blue" (versão atual):
   ```bash
   # Aplicar deployment com label de versão (assumindo Service mesh / Istio
   # ou helm chart com canary configurado em helm/production/)
   kubectl apply -f helm/production/unified-gateway-green.yaml
   ```

2. **Smoke tests internos** apenas no green (sem tráfego de utilizadores):
   - Repetir os smoke tests da secção anterior contra o pod green.

3. **Shift gradual de tráfego** (via VirtualService Istio, Service weighted, ou Helm values):
   - 10% → observar 5-10 minutos.
   - 50% → observar 10-15 minutos.
   - 100% → manter blue desligado por 1h antes de remover.

4. **Critérios de avanço entre fases:**
   - Taxa de erro 5xx < 0.5%.
   - Latência p95 sem degradação relativa ao baseline.
   - Sem alertas críticos disparados.

### Helm (referência futura)

Charts em `helm/unified-gateway/` e `helm/production/` (criados em TICKET-034/TICKET-035). Comando canónico:

```bash
helm upgrade --install unified-gateway helm/unified-gateway/ \
  -n gateway \
  -f helm/production/values.yaml \
  --set image.tag=<new-tag>
```

> **Nota:** Os charts Helm referenciados estão previstos em TICKET-034 e TICKET-035 e podem não estar 100% materializados na altura deste runbook. Quando estiverem, este runbook deve ser revisitado.

---

## Rollback

### Rollback Rápido (deployment Kubernetes)

Em caso de falha pós-deploy, reverter para a revisão anterior:

```bash
# 1. Ver histórico de revisões
kubectl rollout history deployment/unified-gateway -n gateway

# 2. Rollback para a revisão imediatamente anterior
kubectl rollout undo deployment/unified-gateway -n gateway

# 3. (Alternativa) Rollback para revisão específica
kubectl rollout undo deployment/unified-gateway -n gateway --to-revision=<N>

# 4. Aguardar rollout
kubectl rollout status deployment/unified-gateway -n gateway --timeout=180s
```

### Rollback de Dependências

Se o problema estiver no NLU ou PII service:

```bash
kubectl rollout undo deployment/nlu-service -n nlu
kubectl rollout undo deployment/pii-service -n pii
```

### Critérios para Rollback

Iniciar rollback se um destes for verdade:
- Taxa de erro 5xx > 5% durante mais de 2 minutos.
- Pods em CrashLoopBackOff sem recuperação após 5 minutos.
- Liveness probes a falhar de forma persistente.
- Latência p95 > 3x baseline durante mais de 5 minutos.
- Falhas em smoke tests pós-deploy.

---

## Verificação Pós-Deploy

Checklist para validar que o deploy está saudável:

### 1. Pods em Running e Ready

```bash
kubectl get pods -n gateway -l app=unified-gateway -o wide
kubectl get pods -n nlu -l app=nlu-service
kubectl get pods -n pii -l app=pii-service

# Esperado: STATUS=Running, READY=1/1, RESTARTS=0 em todos
```

### 2. Liveness e Readiness OK

```bash
# Para cada pod, verificar probes
for pod in $(kubectl get pods -n gateway -l app=unified-gateway -o jsonpath='{.items[*].metadata.name}'); do
  echo "=== $pod ==="
  kubectl exec -n gateway $pod -- curl -fsS localhost:7999/health
  echo ""
done
```

### 3. Métricas Expostas

```bash
# Confirmar que /metrics responde
kubectl exec -n gateway -l app=unified-gateway -- curl -s localhost:7999/metrics | wc -l
# Esperado: > 0 linhas (default Python/process metrics)
```

### 4. Logs Sem Erros Críticos

```bash
# Inspecionar últimos 200 logs de todos os pods
kubectl logs -n gateway -l app=unified-gateway --tail=200 --all-containers=true | grep -iE "error|critical|exception|traceback" | head -20

# Esperado: zero ou apenas erros transitórios benignos
# (ex.: aviso "neural_hive_observability not available" em ambiente sem OTel)
```

### 5. Dependências (NLU + PII) Healthy

```bash
# A partir de um pod do gateway, testar NLU
kubectl exec -n gateway -l app=unified-gateway -- curl -fsS http://nlu-service.nlu.svc.cluster.local:8020/health

# E PII
kubectl exec -n gateway -l app=unified-gateway -- curl -fsS http://pii-service.pii.svc.cluster.local:8021/health
```

### 6. Tópicos Kafka Recebem Eventos

```bash
# Tópico esperado: unifiedgateway_events (prefix "unified" + "gateway_events")
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list | grep -i gateway_events

# Confirmar que mensagens estão a fluir após enviar requests E2E
kubectl exec -n kafka neural-hive-kafka-kafka-0 -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic unifiedgateway_events \
  --from-beginning --max-messages 5
```

### 7. HPA Activo

```bash
kubectl get hpa -n gateway unified-gateway-hpa
kubectl get hpa -n nlu nlu-service-hpa
kubectl get hpa -n pii pii-service-hpa

# Esperado: TARGETS com valores actuais (não <unknown>)
```

---

## Comandos Úteis

### Diagnóstico Rápido

```bash
# Logs com follow
kubectl logs -n gateway -l app=unified-gateway -f --tail=100

# Eventos do namespace
kubectl get events -n gateway --sort-by='.lastTimestamp' | tail -30

# Describe de um pod problemático
kubectl describe pod -n gateway <pod-name>

# Recursos consumidos
kubectl top pods -n gateway -l app=unified-gateway
```

### Acesso Local via Port-Forward

```bash
# Gateway
kubectl port-forward -n gateway svc/unified-gateway 7999:7999

# NLU service (REST)
kubectl port-forward -n nlu svc/nlu-service 8020:8020

# PII service (REST)
kubectl port-forward -n pii svc/pii-service 8021:8021
```

### Exec Dentro do Pod

```bash
# Shell no pod
kubectl exec -it -n gateway <pod-name> -- /bin/sh

# Comando one-shot
kubectl exec -n gateway <pod-name> -- env | grep KAFKA
```

### Restart Forçado

```bash
# Rolling restart (preserva replicas, faz refresh)
kubectl rollout restart deployment/unified-gateway -n gateway

# Aguardar rollout
kubectl rollout status deployment/unified-gateway -n gateway
```

---

## Troubleshooting Rápido

Se algo correr mal durante ou após o deploy, consulta primeiro:

- **`docs/runbooks/TROUBLESHOOTING.md`** — guia transversal por sintoma para o Unified Gateway.

Se o problema persistir, escalar para a equipa DevOps e considerar **rollback** (ver secção acima).

---

## Referências

- **Spec:** `.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md`
- **OpenAPI:** `services/unified-gateway/openapi.yaml`
- **Código:** `services/unified-gateway/`
- **Manifests:**
  - `k8s/unified-gateway-deployment.yaml`
  - `k8s/nlu-service-deployment.yaml`
  - `k8s/pii-service-deployment.yaml`
- **Helm Charts (futuro):** `helm/unified-gateway/`, `helm/nlu-service/`, `helm/pii-service/`, `helm/production/`
- **TICKET-033:** Runbooks operacionais
- **TICKET-034:** Deploy staging
- **TICKET-035:** Deploy produção (Blue-Green)
- **Troubleshooting:** `docs/runbooks/TROUBLESHOOTING.md`
