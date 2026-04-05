# Guia de Finalizacao e Deployment - Neural Hive Mind

**Data:** 2026-04-04
**Versao:** 1.0
**Status:** Ready for Deployment
**Completude:** 97.5%

---

## Resumo Executivo

Este guia fornece um roteiro completo para finalizacao e deployment do Neural Hive Mind, um sistema de IA distribuido multi-agente com 26 servicos, 4 Epics principais e ~883 testes implementados.

### Arquitetura Core

```
User Intent -> Gateway -> STE -> Consensus -> Orchestrator -> Workers -> Result
              ↓           ↓         ↓           ↓          ↓
           (NLU)    (Translate) (Merge)   (Tickets)  (Exec)
```

### Status dos Epics

| Epic ID | Descricao | Completude | Status |
|---------|-----------|------------|--------|
| **INFRA-001** | Queen MCP Server & Infraestrutura | 100% | ✅ Completo |
| **INFRA-002** | Metrics Dashboard, OPA, Gatekeeper | 100% | ✅ Completo |
| **TEST-001** | Testes E2E e Cobertura | 95% | ⚠️ Quase completo |
| **ML-001** | Modelos ML e Active Learning | 95% | ⚠️ Quase completo |

---

## Parte 1: Checklist de Verificacao por Epic

### EPIC-001: Queen MCP Server (INFRA-001) - 100%

**Objetivo:** Implementar servidor MCP central para orquestracao de agentes.

#### Checklist de Finalizacao

- [x] **MCP Server Core**
  - [x] API gRPC implementada
  - [x] Conexao com Queen Agent
  - [x] Descoberta de servicos
  - [x] Health checks

- [x] **Infraestrutura**
  - [x] Helm chart criado (`helm/queen-agent/`)
  - [x] Dockerfile configurado
  - [x] ServiceMonitor para Prometheus
  - [x] Network policies aplicadas

- [x] **Testes**
  - [x] Testes unitarios (~50 testes)
  - [x] Testes de integracao
  - [x] Testes E2E com Kafka

- [x] **Documentacao**
  - [x] README.md atualizado
  - [x] Especificacao gRPC
  - [x] Runbooks de operacao

#### Validacao

```bash
# Verificar health do Queen MCP Server
curl http://queen-agent:8006/health

# Verificar conexao com servicos
kubectl get pods -n neural-hive -l app=queen-agent

# Executar testes
pytest services/queen-agent/tests/ -v
```

---

### EPIC-002: Metrics Dashboard & OPA (INFRA-002) - 100%

**Objetivo:** Implementar observabilidade e autorizacao com OPA.

#### Checklist de Finalizacao

- [x] **Metrics Dashboard**
  - [x] Grafana dashboards criados
  - [x] Prometheus exporters configurados
  - [x] Alertas definidos
  - [x] SLA monitoring ativo

- [x] **OPA Integration**
  - [x] Policy bundles implementados
  - [x] FastAPI middleware criado
  - [x] Gatekeeper constraints aplicadas
  - [x] Testes de autorizacao

- [x] **Testes**
  - [x] Testes de policies (~30 testes)
  - [x] Testes de middleware
  - [x] Validacao de OPA

#### Validacao

```bash
# Verificar dashboards
kubectl get configmaps -n neural-hive | grep grafana

# Validar OPA policies
kubectl get constrainttemplate -n neural-hive

# Testar autorizacao
curl -H "Authorization: Bearer <token>" http://gateway:8000/api/v1/intent
```

---

### EPIC-003: Testes E2E e Cobertura (TEST-001) - 95%

**Objetivo:** Garantir qualidade com testes abrangentes.

#### Checklist de Finalizacao

- [x] **Testes Unitarios**
  - [x] ~600 testes unitarios implementados
  - [x] Coverage atual: ~82%

- [x] **Testes de Integracao**
  - [x] Testes com Docker Compose
  - [x] Testes de Kafka
  - [x] Testes de MongoDB
  - [x] Testes de Redis

- [x] **Testes E2E**
  - [x] Fluxo A (NLU + STE)
  - [x] Fluxo B (Consensus)
  - [x] Fluxo C (Orchestration)
  - [x] Testes de aprovacao

- [ ] **Tarefas Restantes (5%)**
  - [ ] Aumentar cobertura para 85%
  - [ ] Completar testes de edge cases
  - [ ] Testes de performance automatizados

#### Validacao

```bash
# Executar suite de testes completa
pytest tests/ -v --cov --cov-report=html

# Executar apenas E2E
pytest tests/e2e/ -v -m e2e

# Verificar coverage
pytest tests/ --cov-report=term-missing
```

---

### EPIC-004: Modelos ML e Active Learning (ML-001) - 95%

**Objetivo:** Implementar ML com active learning e feedback.

#### Checklist de Finalizacao

- [x] **Approval Model**
  - [x] Modelo v7 implementado
  - [x] NLP feature extractor
  - [x] Pipeline de retraining
  - [x] SHAP values para explicabilidade

- [x] **Active Learning**
  - [x] Balance analyzer implementado
  - [x] Learning strategy calculator
  - [x] Feedback queue criada
  - [x] API endpoints configurados

- [x] **Feature Store**
  - [x] MongoDB schema criado
  - [x] Indexes configurados
  - [x] Pipeline de features

- [ ] **Tarefas Restantes (5%)**
  - [ ] Coletar mais feedbacks balanceados
  - [ ] Retrain com 46 samples com semantic features
  - [ ] Validar F1-score > 0.7

#### Validacao

```bash
# Verificar modelo approval
curl http://approval-service:8004/api/v1/health

# Verificar active learning metrics
curl http://approval-service:8004/api/v1/active-learning/metrics

# Executar ML tests
pytest ml_pipelines/tests/ -v
```

---

## Parte 2: Deploy para Staging

### Pre-requisitos

1. **Cluster Kubernetes** funcional
2. **kubectl** configurado
3. **Helm 3.x** instalado
4. **Secrets** configurados (ver abaixo)
5. **CI/CD** configurado (GitHub Actions)

### Passo 1: Preparar Secrets

```bash
# Criar namespace de staging
kubectl create namespace neural-hive-staging

# Configurar secrets
kubectl create secret generic mongodb-secret \
  --from-literal=uri="mongodb://<user>:<password>@<host>:27017/neural_hive_staging?authSource=admin" \
  -n neural-hive-staging

kubectl create secret generic redis-secret \
  --from-literal=url="redis://<host>:6379" \
  -n neural-hive-staging

kubectl create secret generic kafka-secret \
  --from-literal=servers="<kafka-broker1>:9092,<kafka-broker2>:9092" \
  -n neural-hive-staging

# Configurar GHCR secret para pull de imagens
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  -n neural-hive-staging
```

### Passo 2: Deploy de Infraestrutura

```bash
# Aplicar CRDs necessarios
kubectl apply -f k8s/infrastructure/crds/

# Deploy Kafka (usando Strimzi ou similar)
helm install kafka bitnami/kafka \
  -n neural-hive-staging \
  --set replicaCount=3 \
  --set zookeeper.replicaCount=3

# Deploy MongoDB (usando operator ou helm)
helm install mongodb bitnami/mongodb \
  -n neural-hive-staging \
  --set auth.rootPassword=<password> \
  --set architecture=replicaset \
  --set replicaCount=3

# Deploy Redis
helm install redis bitnami/redis \
  -n neural-hive-staging \
  --set architecture=standalone \
  --set auth.enabled=true
```

### Passo 3: Deploy dos Servicos (Helm)

```bash
# Servicos Core (ordem importa!)
helm install gateway-intencoes helm-charts/gateway-intencoes \
  -n neural-hive-staging \
  --set image.tag=latest \
  --set env.KAFKA_BROKERS=kafka.neural-hive-staging.svc.cluster.local:9092 \
  --set env.REDIS_HOST=redis.neural-hive-staging.svc.cluster.local

helm install semantic-translation-engine helm-charts/semantic-translation-engine \
  -n neural-hive-staging \
  --set image.tag=latest

helm install consensus-engine helm-charts/consensus-engine \
  -n neural-hive-staging \
  --set image.tag=latest

helm install orchestrator-dynamic helm-charts/orchestrator-dynamic \
  -n neural-hive-staging \
  --set image.tag=latest \
  --set env.TEMPORAL_HOST=temporal.neural-hive-staging.svc.cluster.local

# Servicos de Agentes
helm install queen-agent helm-charts/queen-agent \
  -n neural-hive-staging \
  --set image.tag=latest

helm install worker-agents helm-charts/worker-agents \
  -n neural-hive-staging \
  --set image.tag=latest

helm install scout-agents helm-charts/scout-agents \
  -n neural-hive-staging \
  --set image.tag=latest

helm install analyst-agents helm-charts/analyst-agents \
  -n neural-hive-staging \
  --set image.tag=latest

helm install optimizer-agents helm-charts/optimizer-agents \
  -n neural-hive-staging \
  --set image.tag=latest

helm install guard-agents helm-charts/guard-agents \
  -n neural-hive-staging \
  --set image.tag=latest

# Servicos de Suporte
helm install approval-service helm-charts/approval-service \
  -n neural-hive-staging \
  --set image.tag=latest

helm install execution-ticket-service helm-charts/execution-ticket-service \
  -n neural-hive-staging \
  --set image.tag=latest

helm install mcp-tool-catalog helm-charts/mcp-tool-catalog \
  -n neural-hive-staging \
  --set image.tag=latest

helm install explainability-api helm-charts/explainability-api \
  -n neural-hive-staging \
  --set image.tag=latest

helm install self-healing-engine helm-charts/self-healing-engine \
  -n neural-hive-staging \
  --set image.tag=latest
```

### Passo 4: Configurar Ingress

```bash
# Install NGINX Ingress Controller (se nao existir)
helm install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace

# Aplicar ingress para servicos externos
kubectl apply -f k8s/ingress/
```

### Passo 5: Verificar Deploy

```bash
# Verificar todos os pods
kubectl get pods -n neural-hive-staging

# Verificar services
kubectl get svc -n neural-hive-staging

# Verificar deployments
kubectl get deployments -n neural-hive-staging

# Verificar logs
kubectl logs -f deployment/gateway-intencoes -n neural-hive-staging

# Verificar HPA (se configurado)
kubectl get hpa -n neural-hive-staging
```

### Passo 6: Executar Testes em Staging

```bash
# Teste de saude dos servicos
for svc in gateway-intencoes consensus-engine orchestrator-dynamic queen-agent worker-agents; do
  kubectl exec -it deployment/$svc -n neural-hive-staging -- curl localhost:8000/health
done

# Teste E2E via API
curl -X POST http://<gateway-url>/api/v1/intent \
  -H "Content-Type: application/json" \
  -d '{"text": "Analisar dados de vendas do ultimo trimestre"}'

# Verificar logs no Kafka
kubectl exec -it kafka-0 -n neural-hive-staging -- \
  kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic cognitive.plans --from-beginning
```

---

## Parte 3: Guia de Rollback

### Cenario 1: Rollback de Servico Individual

```bash
# Verificar historico de deployments
kubectl rollout history deployment/gateway-intencoes -n neural-hive-staging

# Rollback para versao anterior
kubectl rollout undo deployment/gateway-intencoes -n neural-hive-staging

# Rollback para revisao especifica
kubectl rollout undo deployment/gateway-intencoes -n neural-hive-staging --to-revision=3

# Verificar status do rollout
kubectl rollout status deployment/gateway-intencoes -n neural-hive-staging
```

### Cenario 2: Rollback via Helm

```bash
# Listar releases helm
helm list -n neural-hive-staging

# Reverter para versao anterior
helm rollback gateway-intencoes -n neural-hive-staging

# Reverter para revisao especifica
helm rollback gateway-intencoes 2 -n neural-hive-staging
```

### Cenario 3: Rollback Completo

```bash
# Reverter todos os servicos
SERVICES=(
  "gateway-intencoes"
  "semantic-translation-engine"
  "consensus-engine"
  "orchestrator-dynamic"
  "queen-agent"
  "worker-agents"
  "analyst-agents"
  "optimizer-agents"
  "guard-agents"
)

for svc in "${SERVICES[@]}"; do
  echo "Rolling back $svc..."
  kubectl rollout undo deployment/$svc -n neural-hive-staging
done

# Aguardar todos ficarem ready
kubectl wait --for=condition=available deployment --all -n neural-hive-staging --timeout=600s
```

### Cenario 4: Rollback de Emergencia

```bash
# Escalar para zero (parar tudo)
kubectl scale deployment --all -n neural-hive-staging --replicas=0

# Restaurar backup do MongoDB (se necessario)
kubectl exec -it mongodb-0 -n neural-hive-staging -- mongorestore --drop /backup/

# Escalar de volta
kubectl scale deployment --all -n neural-hive-staging --replicas=1

# Forcar rollback para tag anterior
for svc in "${SERVICES[@]}"; do
  kubectl set image deployment/$svc $svc=ghcr.io/<owner>/neural-hive-mind/$svc:<previous-tag> -n neural-hive-staging
done
```

---

## Parte 4: Riscos e Mitigacoes para Producao

### Risco 1: Falha em Cascade entre Microservicos

**Descricao:** Um servico falhando pode causar falhas em cascata em servicos dependentes.

**Probabilidade:** Alta
**Impacto:** Critico

#### Mitigacao

- [x] **Circuit Breakers** implementados via `neural_hive_resilience`
- [x] **Timeouts** configurados em todas as chamadas gRPC/Kafka
- [x] **Retry Policies** com exponential backoff
- [x] **Fallback Stubs** para especialistas criticos
- [x] **Health Checks** ativos em todos os servicos

```python
# Exemplo de configuracao de circuit breaker
from neural_hive_resilience import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception
)
```

#### Monitoramento

```bash
# Verificar circuit breakers
kubectl get cm circuit-breaker-config -n neural-hive

# Metrics do circuit breaker
curl http://prometheus:9090/api/v1/query?query=circuit_breaker_state
```

---

### Risco 2: Esgotamento de Recursos no Kafka

**Descricao:** Alto volume de mensagens pode saturar o cluster Kafka.

**Probabilidade:** Media
**Impacto:** Alto

#### Mitigacao

- [x] **Particionamento** adequado dos topicos
- [x] **Retention Policies** configuradas (7 dias)
- [x] **Consumer Groups** balanceados
- [x] **Rate Limiting** no gateway
- [x] **Dead Letter Queues** para mensagens falhas

```yaml
# Exemplo de configuracao de topico
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: cognitive.plans
spec:
  partitions: 12  # Ajustar conforme throughput
  replicas: 3
  config:
    retention.ms: 604800000  # 7 dias
```

#### Monitoramento

```bash
# Verificar lag de consumidores
kubectl exec -it kafka-0 -n neural-hive -- \
  kafka-consumer-groups --bootstrap-server localhost:9092 \
  --describe --group orchestrator-group

# Metrics do Kafka
curl http://prometheus:9090/api/v1/query?query=kafka_consumergroup_lag
```

---

### Risco 3: Falha de Modelo ML em Producao

**Descricao:** Modelo de aprovacao com baixa performance pode causar decisoes incorretas.

**Probabilidade:** Media
**Impacto:** Alto

#### Mitigacao

- [x] **Shadow Mode** para novos modelos
- [x] **A/B Testing** framework implementado
- [x] **Human Approval** para casos duvidosos
- [x] **Active Learning** para coletar feedback
- [x] **Continuous Monitoring** de metricas ML

```python
# Exemplo de shadow mode
if SHADOW_MODE_ENABLED:
    # Modelo novo roda em paralelo sem afetar decisoes
    new_prediction = new_model.predict(features)
    log_prediction(new_prediction, label="shadow")

# Decisao continua sendo feita pelo modelo antigo
prediction = old_model.predict(features)
```

#### Monitoramento

```bash
# Verificar metricas do modelo
curl http://approval-service:8004/api/v1/metrics

# Verificar active learning balance
curl http://approval-service:8004/api/v1/active-learning/metrics
```

---

### Risco 4: Excesso de Latencia no Cognitive Pipeline

**Descricao:** Pipeline end-to-end pode exceder SLA de 30 segundos.

**Probabilidade:** Media
**Impacto:** Medio

#### Mitigacao

- [x] **Async Processing** via Kafka
- [x] **Parallel Execution** de especialistas
- [x] **Caching** de resultados comuns
- [x] **Timeouts** agressivos em cada etapa
- [x] **SLA Monitoring** proativo

```python
# Timeout配置 para cada etapa
TIMEOUTS = {
    "nlu": 2.0,           # Gateway -> NLU
    "translation": 3.0,   # STE
    "consensus": 10.0,    # Consensus Engine
    "orchestration": 5.0, # Orchestrator
    "execution": 10.0     # Workers
}
# Total maximo: 30 segundos
```

#### Monitoramento

```bash
# Verificar SLA breaches
curl http://prometheus:9090/api/v1/query?query=sla_breach_total

# Latencia por etapa
curl http://prometheus:9090/api/v1/query?query=pipeline_latency_seconds
```

---

### Risco 5: Vulnerabilidades de Seguranca

**Descricao:** Dependencias ou configuracoes podem ter vulnerabilidades.

**Probabilidade:** Baixa
**Impacto:** Critico

#### Mitigacao

- [x] **OPA Policies** para autorizacao
- [x] **Gatekeeper Constraints** para Kubernetes
- [x] **Network Policies** para segmentacao
- [x] **Secret Scanning** no CI/CD
- [x] **SBOM Generation** para todas as imagens
- [x] **Trivy Scans** no pipeline

```bash
# Scan de vulnerabilidades
trivy image ghcr.io/<owner>/neural-hive-mind/gateway-intencoes:latest

# Verificar OPA policies
kubectl get constrainttemplate -n neural-hive

# Verificar network policies
kubectl get networkpolicies -n neural-hive
```

---

### Risco 6: Perda de Dados no MongoDB

**Descricao:** Falha no cluster MongoDB pode causar perda de dados.

**Probabilidade:** Baixa
**Impacto:** Critico

#### Mitigacao

- [x] **Replica Set** com 3 nos
- [x] **Backups Diarios** automatizados
- [x] **Persistent Volumes** com alta disponibilidade
- [x] **Write Concern** majority
- [x] **Journaling** ativado

```yaml
# Configuracao de backup
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mongodb-backup
spec:
  schedule: "0 2 * * *"  # 2 AM diariamente
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: mongo:7.0
            command:
            - mongodump
            - --uri=mongodb://mongodb-0.mongodb.neural-hive.svc.cluster.local:27017
            - --archive=/backup/mongo-$(date +%Y%m%d).gz
            volumeMounts:
            - name: backup
              mountPath: /backup
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: mongodb-backup-pvc
```

#### Monitoramento

```bash
# Verificar status do replica set
kubectl exec -it mongodb-0 -n neural-hive -- mongosh --eval "rs.status()"

# Verificar backups
kubectl get cronjobs -n neural-hive
kubectl logs -n neural-hive job/mongodb-backup-<timestamp>
```

---

### Risco 7: Timeout em Workflows Temporal Longos

**Descricao:** Workflows de longa duracao podem expirar.

**Probabilidade:** Media
**Impacto:** Medio

#### Mitigacao

- [x] **Long Poll Intervals** configurados (6h)
- [x] **Heartbeats** ativos em atividades
- [x] **Retry Policies** para falhas temporarias
- [x] **Saga Compensation** para rollback
- [x] **SLA Checkpoints** proativos

```python
# Configuracao de long running workflow
@workflow.defn
class OrchestrationWorkflow:
    @workflow.run
    async def run(self, intent: dict) -> dict:
        # Configurar polling intervalo longo
        await asyncio.sleep(3600)  # Checkpoint a cada hora

        # Executar atividades com heartbeat
        result = await workflow.execute_activity(
            execute_long_task,
            args=[intent],
            start_to_close_timeout=21600,  # 6 horas
            heartbeat_timeout=300,         # 5 minutos
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0
            )
        )
```

---

## Parte 5: Checklist Pre-Producao

### Validacao Tecnica

- [ ] Todos os testes unitarios passando (~600 testes)
- [ ] Todos os testes de integracao passando (~200 testes)
- [ ] Testes E2E passando em staging (~50 testes)
- [ ] Coverage >= 82% (target: 85%)
- [ ] Zero vulnerabilidades criticas (Trivy scan)
- [ ] Zero warnings de deprecation
- [ ] Helm charts testados em staging
- [ ] Rollback testado e documentado

### Validacao de Infraestrutura

- [ ] Cluster Kubernetes funcional
- [ ] Kafka cluster com 3 brokers
- [ ] MongoDB replica set com 3 nos
- [ ] Redis cluster configurado
- [ ] Persistent volumes provisionados
- [ ] Ingress configurado com SSL
- [ ] Monitoring (Prometheus/Grafana) ativo
- [ ] Alertas configurados (PagerDuty/Slack)
- [ ] Log aggregation (Loki/ELK) configurado

### Validacao de Seguranca

- [ ] Secrets geridos via External Secrets Operator
- [ ] Network policies aplicadas
- [ ] OPA policies ativas
- [ ] RBAC configurado
- [ ] Image scan sem vulnerabilidades criticas
- [ ] TLS ativo em todas as conexoes
- [ ] Audit logging ativado

### Validacao de Operacao

- [ ] Runbooks criados para cada servico
- [ ] On-call configurado
- [ ] Dashboards de monitoracao criados
- [ ] SLOs definidos (99.9% uptime)
- [ ] SLAs documentados
- [ ] Procedimentos de rollback testados
- [ ] Capacity planning realizado

---

## Parte 6: Comandos Uteis

### Diagnostico

```bash
# Ver saude de todos os pods
kubectl get pods -n neural-hive -o wide

# Ver pods com problemas
kubectl get pods -n neural-hive --field-selector=status.phase!=Running

# Logs de um pod com erro
kubectl logs <pod-name> -n neural-hive --previous

# Descrever pod para ver eventos
kubectl describe pod <pod-name> -n neural-hive

# Ver resource usage
kubectl top pods -n neural-hive
kubectl top nodes
```

### Debugging

```bash
# Executar shell em container
kubectl exec -it <pod-name> -n neural-hive -- /bin/bash

# Port forward para servico
kubectl port-forward svc/gateway-intencoes 8000:8000 -n neural-hive

# Ver configuracao de deployment
kubectl get deployment gateway-intencoes -n neural-hive -o yaml

# Ver eventos do namespace
kubectl get events -n neural-hive --sort-by=.metadata.creationTimestamp
```

### Performance

```bash
# Ver HPA status
kubectl get hpa -n neural-hive

# Ver metrics do Prometheus
kubectl port-forward svc/prometheus 9090:9090 -n monitoring

# Ver Grafana
kubectl port-forward svc/grafana 3000:3000 -n monitoring

# Verificar latencia
curl -w "@curl-format.txt" -o /dev/null -s http://gateway:8000/health
```

---

## Parte 7: Suporte e Contingencia

### Suporte N1 (Tier 1)

**Responsabilidade:** Monitoramento e triagem inicial

**Acoes:**
- Verificar dashboards
- Confirmar alertas
- Tentar restart de pods
- Escalar para N2 se necessario

```bash
# Restart de pod
kubectl delete pod <pod-name> -n neural-hive

# Restart de deployment
kubectl rollout restart deployment/<service> -n neural-hive
```

### Suporte N2 (Tier 2)

**Responsabilidade:** Diagnostico e resolucao

**Acoes:**
- Analisar logs detalhados
- Verificar configuracoes
- Executar runbooks
- Escalar para N3 se necessario

### Suporte N3 (Tier 3)

**Responsabilidade:** Problemas complexos e arquiteturais

**Acoes:**
- Deep debugging
- Mudancas de configuracao
- Hotfixes
- Comunicacao com stakeholders

### Escalacao

```
N1 (15min) -> N2 (30min) -> N3 (1h) -> Management (critical)
```

---

## Anexos

### A. Referencias de Documentacao

- **Arquitetura:** `docs/ANALISE_COMPLETA_GERACAO_CODIGO_NHM.md`
- **Testes:** `docs/PLANO_TESTE_MANUAL_FLUXOS_A_C.md`
- **ML:** `docs/RELATORIO_FINAL_PROJETO_ML_NHM.md`
- **K8s:** `k8s/README.md`
- **Especs:** `.agent-os/specs/HANDOFF_CONSOLIDADO.md`

### B. Links Externos

- **Repository:** https://github.com/albinoJimy/Neural-Hive-Mind
- **Helm Charts:** `helm-charts/`
- **CI/CD:** `.github/workflows/`

### C. Contatos

- **Tech Lead:** [Contacto]
- **On-call:** [PagerDuty/Slack]
- **Emergencia:** [Contacto direto]

---

**Documento v1.0 - 2026-04-04**
**Status:** Ready for Deployment
**Proximo Passo:** Executar deploy para staging e validar checklist pre-producao.
