# Registro de Teste Manual - Fluxos A, B e C

> **Início:** 2026-01-30
> **Executor:** Claude Code / QA Team
> **Status:** EM EXECUÇÃO

---

## Tabela de Anotações Principal

| Campo | Valor | Timestamp |
|-------|-------|-----------|
| `intent_id` | __________________ | __________ |
| `correlation_id` | __________________ | __________ |
| `trace_id` | __________________ | __________ |
| `plan_id` | __________________ | __________ |
| `decision_id` | __________________ | __________ |
| `ticket_id` (primeiro) | __________________ | __________ |
| `opinion_id` (business) | __________________ | __________ |
| `opinion_id` (technical) | __________________ | __________ |
| `opinion_id` (behavior) | __________________ | __________ |
| `opinion_id` (evolution) | __________________ | __________ |
| `opinion_id` (architecture) | __________________ | __________ |

## Campos Adicionais para C3-C6

| Campo | Valor | Timestamp |
|-------|-------|-----------|
| `worker_id` (primeiro) | __________________ | __________ |
| `workers_discovered` | __________________ | __________ |
| `tickets_assigned` | __________________ | __________ |
| `tickets_completed` | __________________ | __________ |
| `tickets_failed` | __________________ | __________ |
| `telemetry_event_id` | __________________ | __________ |
| `total_duration_ms` | __________________ | __________ |

---

# Seção 2: Preparação do Ambiente

## 2.1 Verificação de Pré-requisitos

### 2.1.1 Checklist de Ferramentas

#### INPUT:
```bash
# Verificar kubectl
kubectl version --client

# Verificar curl
curl --version

# Verificar jq
jq --version
```

#### OUTPUT:
```
Client Version: v1.35.0
curl 7.81.0
jq-1.6
```

#### ANÁLISE PROFUNDA:
Todas as ferramentas estão instaladas e com versões compatíveis.

#### EXPLICABILIDADE:
Verificação básica de ferramentas necessárias para executar os testes manuais.

#### STATUS: [x] OK / [ ] FALHA

---

### 2.1.2 Verificar Pods em Todos os Namespaces

#### INPUT:
```bash
# Gateway de Intenções
kubectl get pods -n neural-hive -l app=gateway-intencoes

# Semantic Translation Engine
kubectl get pods -n neural-hive -l app=semantic-translation-engine

# Consensus Engine
kubectl get pods -n neural-hive -l app=consensus-engine

# Orchestrator Dynamic
kubectl get pods -n neural-hive -l app=orchestrator-dynamic

# Kafka
kubectl get pods -n kafka -l app=kafka

# MongoDB
kubectl get pods -n mongodb-cluster -l app=mongodb

# Redis
kubectl get pods -n redis-cluster -l app=redis

# Observabilidade
kubectl get pods -n observability
```

#### OUTPUT:
**Namespace neural-hive:**
- gateway-intencoes-76bcc5647f-gqdvp: 1/1 Running ✓
- semantic-translation-engine-7dcf87bc96-qcktw: 1/1 Running ✓
- consensus-engine-6cdf86b947-sjvtq: 1/1 Running ✓
- orchestrator-dynamic-d5ff7c648-nkcks: 1/1 Running ✓
- specialist-business-5fc9c85f85-wpgm9: 1/1 Running ✓
- specialist-technical-78fcfc4b7b-xqmlv: 1/1 Running ✓
- specialist-behavior-6749795c8b-mnmvz: 1/1 Running ✓
- specialist-evolution-764696c4b9-k45kv: 1/1 Running ✓
- specialist-architecture-c76688787-vsqqv: 1/1 Running ✓
- service-registry-56df7d8dc9-bjsmp: 1/1 Running ✓

**Namespace kafka:**
- neural-hive-kafka-broker-0: 1/1 Running ✓

**Namespace mongodb-cluster:**
- mongodb-677c7746c4-tkh9k: 2/2 Running ✓

**Namespace redis-cluster:**
- redis-66b84474ff-nfth2: 1/1 Running ✓

**Namespace observability:**
- Prometheus, Jaeger, Grafana, Loki, OTEL: Todos Running ✓

#### ANÁLISE PROFUNDA:
Todos os pods estão em estado Running e Ready. A infraestrutura está disponível para execução dos testes.

#### CRITÉRIOS DE SUCESSO:
- Todos os pods em status `Running` e `Ready`

#### CRITÉRIOS DE FALHA:
- Pods em `CrashLoopBackOff`, `Pending`, ou `Error`

#### STATUS: [x] OK / [ ] FALHA

---

### 2.1.3 Verificar Status Geral

#### INPUT:
```bash
kubectl get pods -A | grep -E "gateway|semantic|consensus|orchestrator|kafka|mongo|redis|jaeger|prometheus" | grep -v "Running" || echo "Todos os pods estão Running"
```

#### OUTPUT:
[TODO: Registrar resultado]

#### STATUS: [ ] OK / [ ] FALHA

---

## 2.2 Configuração de Port-Forwards

### Terminal 1 - Prometheus

#### INPUT:
```bash
kubectl port-forward -n observability svc/prometheus-server 9090:9090
```

#### OUTPUT:
[TODO: Verificar se porta 9090 está acessível]

#### VALIDAÇÃO:
http://localhost:9090 (deve abrir UI)

#### STATUS: [ ] OK / [ ] FALHA

---

### Terminal 2 - Jaeger

#### INPUT:
```bash
kubectl port-forward -n observability svc/jaeger-query 16686:16686
```

#### OUTPUT:
[TODO: Verificar se porta 16686 está acessível]

#### VALIDAÇÃO:
http://localhost:16686 (deve abrir UI)

#### STATUS: [ ] OK / [ ] FALHA

---

### Terminal 3 - Grafana (Opcional)

#### INPUT:
```bash
kubectl port-forward -n observability svc/grafana 3000:3000
```

#### OUTPUT:
[TODO: Verificar se porta 3000 está acessível]

#### VALIDAÇÃO:
http://localhost:3000 (deve abrir UI)

#### STATUS: [ ] OK / [ ] FALHA

---

## 2.3 Preparação de Payloads de Teste

### 2.3.1 Payload 1 - Domínio TECHNICAL (Análise de Viabilidade)

#### INPUT:
```bash
cat > /tmp/intent-technical.json << 'EOF'
{
  "text": "Analisar viabilidade técnica de migração do sistema de autenticação para OAuth2 com suporte a MFA",
  "context": {
    "session_id": "test-session-001",
    "user_id": "qa-tester-001",
    "source": "manual-test",
    "metadata": {
      "test_run": "fluxo-a-b-c",
      "environment": "staging"
    }
  },
  "constraints": {
    "priority": "high",
    "security_level": "confidential",
    "deadline": "2026-02-01T00:00:00Z"
  }
}
EOF
```

#### OUTPUT:
[TODO: Verificar criação do arquivo]

#### VALIDAÇÃO:
```bash
jq . /tmp/intent-technical.json > /dev/null && echo "Payload 1 (TECHNICAL): OK"
```

#### STATUS: [ ] OK / [ ] FALHA

---

### 2.3.2 Payload 2 - Domínio BUSINESS (Análise de ROI)

#### INPUT:
```bash
cat > /tmp/intent-business.json << 'EOF'
{
  "text": "Avaliar retorno sobre investimento da implementação de cache distribuído para reduzir custos de infraestrutura",
  "context": {
    "session_id": "test-session-002",
    "user_id": "qa-tester-001",
    "source": "manual-test",
    "metadata": {
      "test_run": "fluxo-a-b-c",
      "environment": "staging"
    }
  },
  "constraints": {
    "priority": "normal",
    "security_level": "internal",
    "deadline": "2026-03-01T00:00:00Z"
  }
}
EOF
```

#### OUTPUT:
[TODO: Verificar criação do arquivo]

#### VALIDAÇÃO:
```bash
jq . /tmp/intent-business.json > /dev/null && echo "Payload 2 (BUSINESS): OK"
```

#### STATUS: [ ] OK / [ ] FALHA

---

### 2.3.3 Payload 3 - Domínio INFRASTRUCTURE (Análise de Escalabilidade)

#### INPUT:
```bash
cat > /tmp/intent-infrastructure.json << 'EOF'
{
  "text": "Projetar estratégia de auto-scaling para microserviços com base em métricas de CPU e memória",
  "context": {
    "session_id": "test-session-003",
    "user_id": "qa-tester-001",
    "source": "manual-test",
    "metadata": {
      "test_run": "fluxo-a-b-c",
      "environment": "staging"
    }
  },
  "constraints": {
    "priority": "high",
    "security_level": "internal",
    "deadline": "2026-02-15T00:00:00Z"
  }
}
EOF
```

#### OUTPUT:
[TODO: Verificar criação do arquivo]

#### VALIDAÇÃO:
```bash
jq . /tmp/intent-infrastructure.json > /dev/null && echo "Payload 3 (INFRASTRUCTURE): OK"
```

#### STATUS: [ ] OK / [ ] FALHA

---

## 2.5 Identificar Pods para Comandos

#### INPUT:
```bash
export GATEWAY_POD=$(kubectl get pods -n gateway-intencoes -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}')
export STE_POD=$(kubectl get pods -n semantic-translation -l app=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}')
export CONSENSUS_POD=$(kubectl get pods -n consensus-engine -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}')
export ORCHESTRATOR_POD=$(kubectl get pods -n orchestrator-dynamic -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}')
export KAFKA_POD=$(kubectl get pods -n kafka -l app=kafka -o jsonpath='{.items[0].metadata.name}')
export MONGO_POD=$(kubectl get pods -n mongodb -l app=mongodb -o jsonpath='{.items[0].metadata.name}')
export REDIS_POD=$(kubectl get pods -n redis -l app=redis -o jsonpath='{.items[0].metadata.name}')
export SERVICE_REGISTRY_POD=$(kubectl get pods -n neural-hive -l app=service-registry -o jsonpath='{.items[0].metadata.name}')
export WORKER_POD=$(kubectl get pods -n neural-hive -l app=code-forge-worker -o jsonpath='{.items[0].metadata.name}')

echo "Gateway: $GATEWAY_POD"
echo "STE: $STE_POD"
echo "Consensus: $CONSENSUS_POD"
echo "Orchestrator: $ORCHESTRATOR_POD"
echo "Kafka: $KAFKA_POD"
echo "MongoDB: $MONGO_POD"
echo "Redis: $REDIS_POD"
echo "Service Registry: $SERVICE_REGISTRY_POD"
echo "Worker: $WORKER_POD"
```

#### OUTPUT:
[TODO: Registrar nomes dos pods]

#### STATUS: [ ] OK / [ ] FALHA

---

# FLUXO A - Gateway de Intenções → Kafka

## 3.1 Health Check do Gateway

### INPUT:
```bash
kubectl exec -n neural-hive gateway-intencoes-76bcc5647f-gqdvp -- curl -s http://localhost:8000/health
```

### OUTPUT:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-30T19:30:22.633205",
  "version": "1.0.0",
  "service_name": "gateway-intencoes",
  "neural_hive_component": "gateway",
  "neural_hive_layer": "experiencia",
  "components": {
    "redis": { "status": "healthy" },
    "asr_pipeline": { "status": "healthy" },
    "nlu_pipeline": { "status": "healthy" },
    "kafka_producer": { "status": "healthy" },
    "oauth2_validator": { "status": "healthy" }
  }
}
```

### ANÁLISE PROFUNDA:
Todos os 5 componentes estão healthy:
- Redis: healthy (cache e sessão)
- asr_pipeline: healthy (pipeline de reconhecimento de fala)
- nlu_pipeline: healthy (pipeline de NLU)
- kafka_producer: healthy (produtor Kafka)
- oauth2_validator: healthy (validador OAuth2)

### VALIDAÇÃO DE CAMPOS:
- [x] `status` = "healthy"
- [x] `version` presente
- [x] `service_name` = "gateway-intencoes"
- [x] Todos os componentes com `status` = "healthy"

### CRITÉRIOS DE SUCESSO:
- [x] Status HTTP 200
- [x] `status` = "healthy"
- [x] Todos os componentes "healthy"

### CRITÉRIOS DE FALHA:
- Status HTTP != 200
- Qualquer componente "unhealthy"
- Timeout na requisição

### STATUS: [x] PASSOU

---

## 3.2 Enviar Intenção (Payload 1 - TECHNICAL)

### INPUT:
```bash
TIMESTAMP=$(date +%s)
kubectl exec -n neural-hive gateway-intencoes-76bcc5647f-gqdvp -- curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: manual-test-$TIMESTAMP" \
  -d @/tmp/intent.json \
  http://localhost:8000/intentions
```

### OUTPUT:
```json
{
  "detail": "Erro processando intenção: 500: Erro processando intenção: 'NoneType' object has no attribute 'service_name'"
}
```

### ANÁLISE PROFUNDA (BUG ENCONTRADO):

**Erro:** `AttributeError: 'NoneType' object has no attribute 'service_name'`

**Stack Trace:**
```
File "/usr/local/lib/python3.11/site-packages/neural_hive_observability/context.py", line 179, in inject_http_headers
    new_headers["X-Neural-Hive-Source"] = self.config.service_name
                                          ^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'service_name'
```

**Localização do Bug:**
- Arquivo: `neural_hive_observability/context.py`
- Linha: 179
- Método: `inject_http_headers`
- Classe: `ContextManager`
- Propriedade: `self.config` está `None`

**Logs do Gateway:**
```
[KAFKA-DEBUG] _process_text_intention_with_context INICIADO - intent_id=b2eb33b5-5465-498c-9e26-b919339b2193
[KAFKA-DEBUG] Enviando para Kafka - HIGH confidence: 0.95
{"intent_id": "b2eb33b5-5465-498c-9e26-b919339b2193", "domain": "SECURITY", "error": "'NoneType' object has no attribute 'service_name'"...}
```

**Análise:**
1. A intenção foi criada com sucesso (intent_id gerado)
2. O NLU classificou corretamente: domain=SECURITY, confidence=0.95
3. O erro ocorre APENAS na tentativa de publicar no Kafka
4. O contexto de observabilidade não está configurado corretamente

**Impacto:**
- Fluxo A não pode ser completado
- Todas as intenções falharão ao tentar publicar no Kafka
- Traceability comprometido

### CRITÉRIOS DE SUCESSO:
- [ ] Status HTTP 200
- [ ] `confidence` > 0.7
- [ ] `domain` = "technical"
- [ ] `status` = "accepted"

### CRITÉRIOS DE FALHA:
- [x] Status HTTP 500
- [x] Erro interno de servidor

### STATUS: [ ] FALHOU - **BUG CRÍTICO ENCONTRADO**

---

## RECOMENDAÇÃO: REVIEW_REQUIRED

### Bug Crítico: Observabilidade Kafka não configurada

**Severity:** CRITICAL
**Impacto:** Impossibilita qualquer fluxo A → B → C
**Workaround:** Nenhum disponível sem correção de código

**Recomendação de Correção:**
1. Verificar configuração do `ContextManager` no `neural_hive_observability/context.py`
2. Garantir que `self.config` seja inicializado antes de usar em `inject_http_headers`
3. Adicionar validação defensiva: `if self.config and hasattr(self.config, 'service_name'):`
4. Revisar como o context manager é instanciado no `kafka_instrumentation.py`

**Tempo estimado de correção:** 2-4 horas

**Ação requerida:**
- [ ] Corrigir bug de configuração
- [ ] Redploy do Gateway
- [ ] Retestar Fluxo A

---

# FLUXO B - STE → Plano Cognitivo

[TODO: Documentar execução do Fluxo B - STE]

# FLUXO B - Specialists

[TODO: Documentar execução do Fluxo B - Specialists]

# FLUXO C - Consensus Engine

[TODO: Documentar execução do Fluxo C - Consensus]

# FLUXO C - Orchestrator Dynamic

[TODO: Documentar execução do Fluxo C - Orchestrator]

# VALIDAÇÃO END-TO-END

[TODO: Documentar validação E2E]

# CHECKLISTS CONSOLIDADOS

## Checklist Fluxo A

| # | Validação | Status |
|---|-----------|--------|
| 1 | Health check passou | [x] |
| 2 | Intenção aceita (Status 200) | [ ] |
| 3 | Logs confirmam publicação Kafka | [ ] |
| 4 | Mensagem presente no Kafka | [ ] |
| 5 | Cache presente no Redis | [ ] |
| 6 | Métricas incrementadas no Prometheus | [ ] |
| 7 | Trace completo no Jaeger | [ ] |

**Status Fluxo A:** [ ] PASSOU / [x] FALHOU - BUG CRÍTICO ENCONTRADO

## Issues Encontradas

| # | Descrição | Severidade | Status |
|---|-----------|------------|--------|
| 1 | Bug em neural_hive_observability/context.py - self.config está None | CRITICAL | ABERTO |

## Recomendações

[TODO: Preencher ao final]

## Aprovações

| Role | Nome | Data | Assinatura |
|------|------|------|------------|
| QA Lead | | | |
| Tech Lead | | | |
| Product Owner | | | |

---

*Documento gerado automaticamente durante execução do teste manual*
