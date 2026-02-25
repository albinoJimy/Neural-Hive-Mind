# MODELO DE TESTE: WORKER AGENT - EXECUÇÃO DE TICKETS

**Versão:** 1.0
**Data de criação:** 2026-02-23
**Propósito:** Documentar e validar o fluxo completo de execução do Worker Agent

---

## PREPARAÇÃO DO AMBIENTE

### 1.1 Verificação de Pods (Execução Atual)

| Componente | Pod ID | Status | IP | Namespace | Age |
|------------|---------|--------|----|-----------|-----|
| Worker Agent (Replica 1) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Worker Agent (Replica 2) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| CodeForge (Replica 1) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive-execution | __h |
| CodeForge (Replica 2) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive-execution | __h |
| Kafka Broker | neural-hive-kafka-broker-0 | [ ] Running [ ] Error | 10.244.__.__ | kafka | __h |
| MongoDB | mongodb-677c7746c4-__________ | [ ] Running [ ] Error | 10.244.__.__ | mongodb-cluster | __h |
| Redis | redis-66b84474ff-__________ | [ ] Running [ ] Error | 10.244.__.__ | redis-cluster | __h |
| Service Registry | service-registry-68f587f66c-________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Execution Ticket Service | execution-ticket-service-________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Approval Service | approval-service-________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |

**STATUS GERAL:** [ ] Todos pods running [ ] Há pods com erro [ ] Há pods não listados

### 1.2 Credenciais e Endpoints Fixos (DADOS ESTÁTICOS)

**MongoDB Connection:**
```
URI: mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin
⚠️ IMPORTANTE: O parâmetro "authSource=admin" é obrigatório para autenticação correta.

Database: neural_hive
Collections disponíveis:
  - cognitive_ledger (planos cognitivos)
  - consensus_decisions (decisões do consenso)
  - specialist_opinions (opiniões dos especialistas)
  - execution_tickets (tickets de execução)
  - plan_approvals (aprovações de planos)
  - telemetry_buffer (eventos de telemetria)
  - insights (insights gerados)
  - incidents (incidentes reportados)
  - code_forge.artifacts (artefatos de build)
  - code_forge.pipelines (pipelines de build)
  - code_forge.validation_results (resultados de validação)

⚠️ NOTA: Use sempre "mongosh" (MongoDB Shell v6+) em vez de "mongo" (legado).
```

**Kafka Bootstrap:**
```
Bootstrap servers: neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092

Topics disponíveis:
  [ ] intentions.security
  [ ] intentions.technical
  [ ] intentions.business
  [ ] intentions.infrastructure
  [ ] intentions.validation
  [ ] plans.ready
  [ ] plans.consensus
  [ ] opinions.ready
  [ ] decisions.ready
  [ ] execution.tickets
  [ ] execution.tickets.dlq (Dead Letter Queue)
  [ ] execution.results
  [ ] workers.status
  [ ] workers.capabilities
  [ ] workers.discovery
  [ ] telemetry.events
```

**Redis Connection:**
```
Host: redis-redis-cluster.svc.cluster.local
Port: 6379
Password: (nenhum - sem autenticação)
```

**CodeForge Service:**
```
HTTP: http://code-forge.neural-hive-execution.svc.cluster.local:8000
APIs disponíveis:
  - POST /api/v1/pipelines (trigger pipeline)
  - GET /api/v1/pipelines/{pipeline_id} (get pipeline status)
  - POST /api/v1/generate (code generation request)
  - GET /api/v1/generate/{request_id} (get generation status)
  - GET /health (health check)
  - GET /ready (readiness check)
```

**Service Registry:**
```
Endpoint: http://service-registry.neural-hive.svc.cluster.local:8080
APIs disponíveis:
  - GET /services
  - GET /workers
  - GET /capabilities
  - POST /register
  - POST /heartbeat
```

**Execution Ticket Service:**
```
HTTP: http://execution-ticket-service.neural-hive.svc.cluster.local:8000
APIs disponíveis:
  - GET /api/v1/tickets/{ticket_id}
  - GET /api/v1/tickets
  - PATCH /api/v1/tickets/{ticket_id}/status
  - POST /api/v1/tickets/{ticket_id}/compensate
```

**Approval Service:**
```
HTTP: http://approval-service.neural-hive.svc.cluster.local:8080
APIs disponíveis:
  - GET /api/v1/approvals
  - GET /api/v1/approvals/requests
  - GET /api/v1/approvals/{plan_id}
  - POST /api/v1/approvals/{approval_id}/approve
  - POST /api/v1/approvals/{approval_id}/reject
```

### 1.3 Checklist Pré-Teste

[ ] Todos os pods estão Running
[ ] Port-forward CodeForge ativo (porta 8000:8000)
[ ] Port-forward Service Registry ativo (porta 8080:8080)
[ ] Port-forward Execution Ticket Service ativo (porta 8001:8000)
[ ] Port-forward Approval Service ativo (porta 8082:8080)
[ ] Acesso ao MongoDB verificado
   ⚠️ VERIFICAR: Usar "mongosh" com parâmetro "authSource=admin"
[ ] Acesso ao Redis verificado
[ ] Acesso ao Kafka verificado
[ ] Todos os topics Kafka existem
[ ] Consumer groups criados e ativos
[ ] Service Registry respondendo
[ ] CodeForge Service respondendo
[ ] Execution Ticket Service respondendo
[ ] Approval Service respondendo
[ ] Documento de teste preenchido e salvo

---

## METADADOS DO TESTE

**Executado por:** ________________________
**Data de execução:** 2026-__-__
**Ambiente:** [ ] dev [ ] staging [ ] prod
**Versão do Neural Hive:** ____________

**INTENÇÃO TESTADA:**
- **Texto:** ________________________
- **Domain:** ________________________
- **Classification:** ________________________
- **Confidence:** ________________________

**CRITÉRIOS DE ACEITAÇÃO:**
- [ ] Worker Agent consome tickets do Kafka
- [ ] Worker Agent processa tickets corretamente
- [ ] BuildExecutor gera artefatos com sucesso
- [ ] CodeForge executa pipeline completo
- [ ] Resultados são publicados no Kafka
- [ ] Dead Letter Queue é gerenciada corretamente
- [ ] Todos os dados são persistidos no MongoDB

---

## ÍNDICE

1. [Preparação do Ambiente](#preparacao-do-ambiente)
   - 1.1 Verificação de Pods
   - 1.2 Credenciais e Endpoints Fixos
   - 1.3 Checklist Pré-Teste
2. [Visão Geral dos Componentes](#visao-geral)
3. [Executores Disponíveis](#executores-disponiveis)
4. [D1: Ingestão de Tickets](#d1-ingestao)
5. [D2: Processamento de Tickets](#d2-processamento)
6. [D3: Build + Geração de Artefatos](#d3-build-artefatos)
   - 6.1 Arquitetura do BuildExecutor
   - 6.2 Parâmetros do Ticket de Build
   - 6.3 Análise de Build
   - 6.4 Estágios de Pipeline CI/CD
   - 6.5 Segurança e Validação
   - 6.6 Gerenciamento de Artefatos
7. [D4: Publicação de Resultados](#d4-publicacao)
8. [D5: Dead Letter Queue e Alertas](#d5-dlq)
9. [D6: Resumo da Execução](#d6-resumo)
10. [Análise Final](#analise-final)

---

## VISÃO GERAL DOS COMPONENTES

---

### 🔧 Visão Geral dos Componentes do Worker Agent

| Componente | Descrição | Status |
|-------------|------------|--------|
| KafkaTicketConsumer | Consome tickets do Kafka, valida, controla backpressure | [ ] OK [ ] Falha |
| ExecutionEngine | Gerencia execução, dependências, retry, preempção | [ ] OK [ ] Falha |
| DependencyCoordinator | Verifica dependências antes de executar | [ ] OK [ ] Falha |
| TaskExecutorRegistry | Registry de executores para cada task_type | [ ] OK [ ] Falha |
| KafkaResultProducer | Publica resultados no Kafka | [ ] OK [ ] Falha |
| Redis Client | Deduplicação, checkpoint, retry tracking | [ ] OK [ ] Falha |
| CodeForge Client | Integração com serviço de build | [ ] OK [ ] Falha |
| Vault Client | Credenciais, secrets dinâmicos | [ ] OK [ ] Falha |
| DLQ Alert Manager | Alertas SRE para Dead Letter Queue | [ ] OK [ ] Falha |

---

## EXECUTORES DISPONÍVEIS

---

### 🚀 Executores Disponíveis

| Executor | Task Type | Descrição | Clients | Status |
|----------|-----------|------------|---------|--------|
| BuildExecutor | BUILD | Compila código, cria containers | CodeForge | [ ] OK [ ] Falha |
| DeployExecutor | DEPLOY | Deploy GitOps (ArgoCD/Flux) | ArgoCD, Flux | [ ] OK [ ] Falha |
| TestExecutor | TEST | Executa testes | GitHub Actions, GitLab CI, Jenkins | [ ] OK [ ] Falha |
| ValidateExecutor | VALIDATE | Validações políticas/security | OPA | [ ] OK [ ] Falha |
| ExecuteExecutor | EXECUTE | Executa scripts/containers | Docker, K8s Jobs, Lambda, Local | [ ] OK [ ] Falha |
| CompensateExecutor | COMPENSATE | Rollback/compensação | ArgoCD, Flux | [ ] OK [ ] Falha |
| QueryExecutor | QUERY | Queries de dados | MongoDB, Redis, Neo4j | [ ] OK [ ] Falha |
| TransformExecutor | TRANSFORM | Transforma dados | MongoDB, Redis | [ ] OK [ ] Falha |

---

## D1: INGESTÃO DE TICKETS

---

### 🔄 D1: Worker Agent - Ingestão de Tickets

**Timestamp Execução:** 2026-__-__ __:__:__ UTC  
**Pod Worker:** _________________________________  
**Ticket ID (Capturado em C4):** ________________________

**INPUT (Comandos Executados):**
```
# Verificar status do pod Worker
kubectl get pod -n neural-hive _________________________________

# Logs de ingestão de tickets
kubectl logs --tail=200 -n neural-hive _________________________________ | \
  grep -E "(ticket.*consumed|ingestion|poll.*ticket|KafkaTicketConsumer)" | \
  tail -30
```

**OUTPUT (Logs de Ingestão - RAW):**
```
[INSERIR LOGS DE INGESTÃO DE TICKETS AQUI]
```

**ANÁLISE DE INGESTÃO:**

| Etapa | Timestamp | Ação | Status |
|-------|-----------|-------|--------|
| Poll execution.tickets | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Deserialização Avro/JSON | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Validação campos obrigatórios | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Normalização task_type | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Verificação status PENDING | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Aquisição semaphore | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Ticket não consumido: ________________________
[ ] Erro de deserialização: ________________________
[ ] Validação falhou: ________________________

---

## D2: PROCESSAMENTO DE TICKETS

---

### 🔄 D2: Worker Agent - Processamento de Tickets

**Timestamp Execução:** 2026-__-__ __:__:__ UTC  
**Pod Worker:** _________________________________  
**Ticket ID (Capturado em C4):** ________________________

**INPUT (Comandos Executados):**
```
# Logs de processamento de tickets
kubectl logs --tail=500 -n neural-hive _________________________________ | \
  grep -E "(ExecutionEngine|process_ticket|duplicate|dependencies)" | \
  tail -30

# Verificar duplicatas no Redis
kubectl exec -n redis-cluster _________________________________ -- \
  redis-cli KEYS "ticket:processed:*" | head -20

# Verificar tickets em processamento
kubectl exec -n redis-cluster _________________________________ -- \
  redis-cli KEYS "ticket:processing:*" | head -20
```

**OUTPUT (Logs de Processamento - RAW):**
```
[INSERIR LOGS DE PROCESSAMENTO AQUI]
```

**OUTPUT (Redis - Duplicatas):**
```
[INSERIR CHAVES DE TICKETS PROCESSADOS AQUI]
```

**OUTPUT (Redis - Em Processamento):**
```
[INSERIR CHAVES DE TICKETS EM PROCESSAMENTO AQUI]
```

**ANÁLISE DE PROCESSAMENTO:**

| Etapa | Timestamp | Ação | Status |
|-------|-----------|-------|--------|
| Verificação duplicata (Redis two-phase) | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Marcação ticket:processing (TTL 10min) | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Verificação de dependências | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Execução do ticket | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Atualização status → RUNNING | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Atualização status → COMPLETED/FAILED | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Publicação de resultado | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |
| Marcação ticket:processed (Redis) | 2026-__-__ __:__:__.___ | ________________________ | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Ticket duplicado detectado: ________________________
[ ] Dependências não satisfeitas: ________________________
[ ] Execução falhou: ________________________

---

## D3: BUILD + GERAÇÃO DE ARTEFATOS

---

### 🔄 D3: Worker Agent - Build + Geração de Artefatos

**Timestamp Execução:** 2026-__-__ __:__:__ UTC  
**Pod Worker:** _________________________________  
**Ticket ID (Capturado em C4):** ________________________  
**Task Type:** [ ] BUILD [ ] DEPLOY [ ] TEST [ ] VALIDATE [ ] EXECUTE [ ] COMPENSATE [ ] QUERY [ ] TRANSFORM

---

#### 🏗️ Arquitetura do BuildExecutor

**COMPONENTES DO BUILDEXECUTOR:**

| Componente | Descrição | Classe/Arquivo | Status |
|-----------|----------|----------------|--------|
| **BaseTaskExecutor** | Classe base abstrata para todos os executores | base_executor.py | [ ] OK |
| **BuildExecutor** | Executor especializado em builds CI/CD | build_executor.py | [ ] OK |
| **CodeForgeClient** | Cliente HTTP para serviço de build | code_forge_client.py | [ ] OK |
| **VaultClient** | Gerenciamento de secrets | vault_client.py | [ ] OK |
| **ExecutionEngine** | Orquestrador principal de tarefas | execution_engine.py | [ ] OK |
| **DependencyCoordinator** | Verificação de dependências | dependency_coordinator.py | [ ] OK |

**FLUXO DE EXECUÇÃO DO BUILDEXECUTOR:**

```
1. VALIDAÇÃO DO TICKET
   └─> validate_ticket(ticket)
       ├─> Verifica campos obrigatórios: ticket_id, task_id, task_type, parameters
       ├─> Valida task_type == "BUILD"
       └─> Lança ValidationError se inválido

2. EXTRAÇÃO DE PARÂMETROS
   ├─> ticket_id = ticket.get('ticket_id')
   ├─> artifact_id = parameters.get('artifact_id') or ticket_id
   ├─> branch = parameters.get('branch') or 'main'
   ├─> commit_sha = parameters.get('commit_sha') or None
   ├─> build_args = parameters.get('build_args') or {}
   ├─> env_vars = parameters.get('env') or {}
   ├─> pipeline_timeout = parameters.get('timeout_seconds') or 14400
   └─> poll_interval = parameters.get('poll_interval_seconds') or 30

3. VERIFICAÇÃO INTEGRAÇÃO CODEFORGE
   └─> if self.code_forge_client:
       ├─> MODO INTEGRADO
       │   ├─> trigger_pipeline(artifact_id) → pipeline_id
       │   ├─> wait_for_pipeline_completion(pipeline_id)
       │   │   ├─> Polling com intervalo configurável
       │   │   ├─> Timeout configurável (padrão 4h)
       │   │   └─> Retry para falhas transitórias (max 3 tentativas)
       │   └─> Coleta: status, stage, artifacts, sbom, signature
   │
   └─> else:
       └─> MODO SIMULAÇÃO (stub MVP)
           ├─> delay = random.uniform(2, 5)
           ├─> Simula build com sucesso
           └─> Gera artefatos stub

4. GERAÇÃO DE RESULTADO
   └─> Retorna {
       'success': bool,
       'output': {
           'pipeline_id': str,
           'artifact_id': str,
           'branch': str,
           'commit_sha': str,
           'artifacts': list,
           'sbom': dict,
           'signature': str
       },
       'metadata': {
           'executor': 'BuildExecutor',
           'simulated': bool,
           'duration_seconds': float
       },
       'logs': list[str]
   }

5. MÉTRICAS E TELEMETRIA
   ├─> build_tasks_executed_total{status="success|failed"}
   ├─> build_duration_seconds{stage}
   ├─> build_artifacts_generated_total{type}
   └─> code_forge_api_calls_total{method="trigger|status",status="success|error"}
```

**MODELOS DE DADOS (Pydantic):**

```python
# GenerationRequest
{
  "ticket_id": str,
  "template_id": str,
  "parameters": Dict[str, Any],
  "target_repo": str,
  "branch": str
}

# GenerationStatus
{
  "request_id": str,
  "status": str,
  "artifacts": list[Dict[str, Any]],
  "pipeline_id": Optional[str],
  "error": Optional[str]
}

# PipelineStatus
{
  "pipeline_id": str,
  "status": str,              # "completed" | "failed" | "cancelled" | "running"
  "stage": str,                # Stage atual do pipeline
  "duration_ms": int,
  "artifacts": list[Dict[str, Any]],
  "sbom": Optional[Dict[str, Any]],
  "signature": Optional[str]
}
```

**MECANISMOS DE RESILIÊNCIA:**

| Mecanismo | Descrição | Configuração |
|-----------|----------|--------------|
| **Retry transiente** | 3 tentativas para chamadas CodeForge | code_forge_retry_attempts |
| **Backoff exponencial** | 2s, 4s, 8s entre tentativas | retry_backoff_base_seconds |
| **Timeout de pipeline** | 4h por padrão (configurável) | code_forge_timeout_seconds |
| **Polling inteligente** | Intervalo de 30s (configurável) | poll_interval_seconds |
| **Fallback simulação** | Stub MVP se CodeForge indisponível | code_forge_client ausente |
| **Fail-open Vault** | Continua sem secrets se Vault falha | vault_fail_open |

---

#### 📊 Parâmetros do Ticket de Build

**INPUT (Parâmetros Esperados):**

| Parâmetro | Tipo | Descrição | Obrigatório | Exemplo |
|-----------|------|-----------|-------------|---------|
| artifact_id | str | Identificador do artefato | Não (usar ticket_id) | "myapp-api" |
| branch | str | Branch Git | Não ("main") | "feature/oauth2" |
| commit_sha | str | Commit SHA | Não | "abc123..." |
| build_args | dict | Argumentos de build | Não | {"dockerfile": "Dockerfile.prod"} |
| env | dict | Variáveis de ambiente | Não | {"NODE_ENV": "production"} |
| env_vars | dict | Variáveis de ambiente (alternativo) | Não | {"BUILD_NUMBER": "42"} |
| timeout_seconds | int | Timeout do pipeline | Não (14400=4h) | 3600 |
| poll_interval_seconds | int | Intervalo de polling | Não (30s) | 60 |

**INPUT (Comandos Executados):**
```
# Logs de BuildExecutor
kubectl logs --tail=500 -n neural-hive _________________________________ | \
  grep -E "(BuildExecutor|CodeForge|artifact|pipeline|build|build_started|build_completed|trigger_pipeline|wait_for_pipeline)" | \
  tail -50

# Verificar integração com CodeForge
kubectl logs --tail=300 -n neural-hive _________________________________ | \
  grep -E "(trigger_pipeline|wait_for_pipeline|poll.*status|pipeline_triggered|pipeline_completed)" | \
  tail -20

# Verificar tentativas de retry
kubectl logs --tail=200 -n neural-hive _________________________________ | \
  grep -E "(retry|backoff|code_forge_api_calls_total)" | \
  tail -10

# Verificar métricas
kubectl logs --tail=100 -n neural-hive _________________________________ | \
  grep -E "(build_tasks_executed_total|build_duration_seconds|build_artifacts_generated_total)" | \
  tail -20
```

**OUTPUT (Logs de Build - RAW):**
```
[INSERIR LOGS DE BUILD AQUI]

Deve conter:
- build_started
- Triggered pipeline {pipeline_id} for artifact {artifact_id}
- Pipeline status: {status} at stage {stage}
- Build completed successfully / Build failed
- build_completed ou build_failed
```

**OUTPUT (Artefatos Gerados - RAW JSON):**
```json
{
  "ticket_id": "________________________________",
  "task_type": "BUILD",
  "artifacts": [
    {
      "type": "CONTAINER",
      "uri": "ghcr.io/neural-hive/myapp-api:latest",
      "digest": "sha256:abc123...",
      "size_bytes": 123456789
    },
    {
      "type": "MANIFEST",
      "uri": "gs://artifacts/myapp/manifest.json"
    }
  ],
  "sbom": {
    "format": "SPDX",
    "version": "2.3",
    "uri": "gs://artifacts/myapp/sbom.spdx.json",
    "components_count": 42
  },
  "signature": {
    "algorithm": "SHA256",
    "value": "abc123...",
    "signed_at": "2026-__-__T__:__:__Z",
    "verified": true
  }
}
```

**OUTPUT (Resultado Completo - RAW JSON):**
```json
{
  "success": true,
  "output": {
    "pipeline_id": "pipeline-______________________",
    "artifact_id": "__________________________",
    "branch": "main",
    "commit_sha": "__________________________",
    "artifacts": [...],
    "sbom": {...},
    "signature": {...}
  },
  "metadata": {
    "executor": "BuildExecutor",
    "simulated": false,
    "duration_seconds": 123.456
  },
  "logs": [
    "Build started",
    "Triggered pipeline {pipeline_id} for artifact {artifact_id}",
    "Pipeline status: completed at stage final",
    "Build completed successfully via Code Forge"
  ]
}
```

---

#### ✅ Análise de Build

**STATUS DO BUILD:**

| Item | Valor | Status |
|------|-------|--------|
| Pipeline acionado no CodeForge? | [ ] Sim [ ] Não | [ ] OK |
| Modo de execução | [ ] Integrado [ ] Simulação [ ] OK |
| Status do pipeline | [ ] Sucesso [ ] Falha [ ] Em andamento | [ ] OK |
| Tempo de execução | _________ segundos | [ ] OK |
| Código do status | ____________ | [ ] OK |

**PIPELINE STATUS:**

| Campo | Valor | Status |
|-------|-------|--------|
| Pipeline ID | ____________________________ | [ ] OK |
| Status final | ____________ | [ ] OK |
| Stage final | ____________ | [ ] OK |
| Duration (ms) | ____________ | [ ] OK |

**ARTEFATOS:**

| Item | Valor | Status |
|------|-------|--------|
| Artefatos gerados? | [ ] Sim [ ] Não | [ ] OK |
| Número de artefatos | ______ artefatos | [ ] OK |
| Container image | ________________________ | [ ] OK |
| Image digest | ________________________ | [ ] OK |
| Tamanho da imagem | _________ bytes | [ ] OK |

**SBOM (Software Bill of Materials):**

| Item | Valor | Status |
|------|-------|--------|
| SBOM gerado? | [ ] Sim [ ] Não | [ ] OK |
| Formato do SBOM | [ ] SPDX [ ] CycloneDX [ ] Outro | [ ] OK |
| Versão do SBOM | ______.__ | [ ] OK |
| URI do SBOM | ________________________ | [ ] OK |
| Componentes no SBOM | ______ componentes | [ ] OK |

**ASSINATURA DIGITAL:**

| Item | Valor | Status |
|------|-------|--------|
| Assinatura gerada? | [ ] Sim [ ] Não | [ ] OK |
| Algoritmo | [ ] SHA256 [ ] SHA512 [ ] Outro | [ ] OK |
| Assinatura verificada? | [ ] Sim [ ] Não | [ ] OK |
| Timestamp da assinatura | 2026-__-__ __:__:__ | [ ] OK |

**MÉTRICAS REGISTRADAS:**

| Métrica | Valor | Status |
|---------|-------|--------|
| build_tasks_executed_total{success} | _____ | [ ] OK |
| build_tasks_executed_total{failed} | _____ | [ ] OK |
| build_duration_seconds{stage} | _____ s | [ ] OK |
| build_artifacts_generated_total{CONTAINER} | _____ | [ ] OK |
| build_artifacts_generated_total{SBOM} | _____ | [ ] OK |
| code_forge_api_calls_total{trigger,success} | _____ | [ ] OK |
| code_forge_api_calls_total{trigger,error} | _____ | [ ] OK |
| code_forge_api_calls_total{status,success} | _____ | [ ] OK |

**RETRY E BACKOFF:**

| Item | Valor | Status |
|------|-------|--------|
| Tentativas de retry | _____ / 3 | [ ] OK |
| Backoff utilizado | [ ] 2s [ ] 4s [ ] 8s | [ ] OK |
| Falhas transitórias recuperadas | _____ | [ ] OK |
| Último erro | [ ] Nenhum | [ ] OK |

**ARTEFATOS GERADOS (DETALHADO):**

| Tipo | URI | Digest | Size | Status |
|------|-----|--------|------|--------|
| CONTAINER | ________________________ | ________________________ | _______ | [ ] OK |
| MANIFEST | ________________________ | ________________________ | _______ | [ ] OK |
| SBOM | ________________________ | ________________________ | _______ | [ ] OK |
| Outro 1 | ________________________ | ________________________ | _______ | [ ] OK |
| Outro 2 | ________________________ | ________________________ | _______ | [ ] OK |

**TELEMETRIA E TRACING:**

| Item | Trace ID | Span ID | Status |
|------|----------|---------|--------|
| task_execution | ____________________________ | ________________________ | [ ] OK |
| neural.hive.task_id | ________________________ | ________________________ | [ ] OK |
| neural.hive.task_type | BUILD | ________________________ | [ ] OK |
| neural.hive.executor | BuildExecutor | ________________________ | [ ] OK |
| neural.hive.execution_status | [ ] success [ ] failed | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Pipeline falhou: ________________________
[ ] Artefatos não gerados: ________________________
[ ] SBOM inválido: ________________________
[ ] Assinatura inválida: ________________________
[ ] Timeout de pipeline excedido: ________________________
[ ] Máximo de tentativas de retry atingido: ________________________
[ ] CodeForge indisponível (modo simulação): ________________________

---

#### 🚀 Estágios de Pipeline CI/CD

**ESTÁGIOS PADRÃO DO BUILDEXECUTOR:**

| Stage | Descrição | Tempo Esperado | Status |
|-------|----------|----------------|--------|
| 1. **Setup** | Configuração do ambiente de build | 30-120s | [ ] OK |
| 2. **Restore Cache** | Restauração de cache de dependências | 10-60s | [ ] OK |
| 3. **Install Dependencies** | Instalação de dependências | 60-300s | [ ] OK |
| 4. **Build** | Compilação/Build do projeto | 120-600s | [ ] OK |
| 5. **Test** | Execução de testes unitários/integração | 60-300s | [ ] OK |
| 6. **Package** | Empacotamento dos artefatos | 30-120s | [ ] OK |
| 7. **Scan** | Varredura de segurança (SBOM, SAST) | 60-240s | [ ] OK |
| 8. **Push** | Publicação de artefatos no registry | 30-180s | [ ] OK |

**VALIDAÇÃO DE CADA STAGE:**

| Stage | Critérios de Sucesso | Observações |
|-------|-------------------|-------------|
| Setup | Ambiente configurado com sucesso | Variáveis de ambiente setadas |
| Restore Cache | Cache restaurado ou fresh build | Reduz tempo de build em ~70% |
| Install Deps | Todas dependências instaladas | Sem conflitos de versão |
| Build | Binários gerados sem erros | Compilação bem-sucedida |
| Test | Todos os testes passando | Cobertura mínima alcançada |
| Package | Artefatos empacotados | Formato correto (tar, zip, docker) |
| Scan | Sem vulnerabilidades críticas | SAST/SCA passando |
| Push | Artefatos publicados no registry | URL acessível |

**ANÁLISE DE TEMPOS POR STAGE:**

| Stage | Início | Fim | Duração | SLO | Desvio | Status |
|-------|--------|-----|----------|-----|-------|--------|
| Setup | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <120s | ___% | [ ] ✅ [ ] ❌ |
| Restore Cache | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <60s | ___% | [ ] ✅ [ ] ❌ |
| Install Deps | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <300s | ___% | [ ] ✅ [ ] ❌ |
| Build | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <600s | ___% | [ ] ✅ [ ] ❌ |
| Test | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <300s | ___% | [ ] ✅ [ ] ❌ |
| Package | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <120s | ___% | [ ] ✅ [ ] ❌ |
| Scan | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <240s | ___% | [ ] ✅ [ ] ❌ |
| Push | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | ___ s | <180s | ___% | [ ] ✅ [ ] ❌ |

**TEMPO TOTAL DE BUILD:**
- Tempo registrado: _________ segundos
- SLO de build: <1800s (30 minutos)
- Desvio: _____ % [ ] Aceitável [ ] Excedido

---

#### 🔒 Segurança e Validação

**VALIDAÇÃO DE ARTEFATOS:**

| Tipo de Validação | Implementado? | Status | Observações |
|------------------|--------------|--------|-------------|
| **Digest verification** | [ ] Sim [ ] Não | [ ] OK | Verificação SHA256/SHA512 |
| **Signature verification** | [ ] Sim [ ] Não | [ ] OK | Assinatura digital verificada |
| **SBOM validation** | [ ] Sim [ ] Não | [ ] OK | Formato SPDX/CycloneDX válido |
| **Vulnerability scan** | [ ] Sim [ ] Não | [ ] OK | Sem CVEs críticas |
| **License compliance** | [ ] Sim [ ] Não | [ ] OK | Licenças compatíveis |
| **Provenance check** | [ ] Sim [ ] Não | [ ] OK | Rastreabilidade de origem |

**SBOM DETALHES:**

| Campo | Valor | Status |
|-------|-------|--------|
| Formato | [ ] SPDX [ ] CycloneDX [ ] Outro | [ ] OK |
| Versão | ______.__ | [ ] OK |
| Número de componentes | ______ componentes | [ ] OK |
| Licenças identificadas | ______ licenças | [ ] OK |
| Vulnerabilidades encontradas | ______ CVEs | [ ] OK |
| Licenças não permitidas | ______ licenças | [ ] OK |

**VULNERABILIDADES DETECTADAS:**

| CVE/ID | Severidade | Pacote | Versão | Status |
|---------|-----------|--------|--------|--------|
| CVE-_____-_____ | [ ] Crítico [ ] Alto [ ] Médio [ ] Baixo | ________________________ | _________ | [ ] OK |
| CVE-_____-_____ | [ ] Crítico [ ] Alto [ ] Médio [ ] Baixo | ________________________ | _________ | [ ] OK |
| CVE-_____-_____ | [ ] Crítico [ ] Alto [ ] Médio [ ] Baixo | ________________________ | _________ | [ ] OK |

**POLICY CHECKS (OPA/OPAL):**

| Política | Resultado | Violações | Status |
|----------|---------|----------|--------|
| image-trust-policy | [ ] Pass [ ] Fail | ______ | [ ] OK |
| license-policy | [ ] Pass [ ] Fail | ______ | [ ] OK |
| vulnerability-policy | [ ] Pass [ ] Fail | ______ | [ ] OK |
| provenance-policy | [ ] Pass [ ] Fail | ______ | [ ] OK |

---

#### 📦 Gerenciamento de Artefatos

**TIPOS DE ARTEFATOS SUPORTADOS:**

| Tipo | Descrição | Exemplo de URI | Status |
|------|----------|---------------|--------|
| **CONTAINER** | Imagem Docker/OCI | ghcr.io/org/app:tag | [ ] OK |
| **MANIFEST** | Manifesto Kubernetes | gs://artifacts/app/manifest.yaml | [ ] OK |
| **HELM CHART** | Chart Helm | gs://artifacts/app/chart.tgz | [ ] OK |
| **BINARY** | Executável nativo | gs://artifacts/app/bin/app | [ ] OK |
| **ARCHIVE** | Arquivo tar/zip | gs://artifacts/app/dist.tar.gz | [ ] OK |
| **SBOM** | Bill of Materials | gs://artifacts/app/sbom.spdx.json | [ ] OK |
| **SIGNATURE** | Assinatura digital | gs://artifacts/app/signature.sig | [ ] OK |

**ARTEFATO REGISTRY:**

| Registry | Tipo | Status | Configuração |
|----------|------|--------|--------------|
| **GitHub Container Registry** | OCI | [ ] OK | ghcr.io |
| **Google Artifact Registry** | Multi-formato | [ ] OK | pkg.dev |
| **AWS ECR** | OCI | [ ] OK | ecr.aws.com |
| **Docker Hub** | OCI | [ ] OK | docker.io |
| **Custom S3/GCS** | Blobs | [ ] OK | gs://, s3:// |

**METADADOS DE ARTEFATOS:**

| Metadado | Valor | Status |
|----------|-------|--------|
| artifact_id | ________________________ | [ ] OK |
| build_id | ________________________ | [ ] OK |
| git_commit_sha | ________________________ | [ ] OK |
| git_branch | ________________________ | [ ] OK |
| build_timestamp | 2026-__-__T__:__:__Z | [ ] OK |
| builder_info | ________________________ | [ ] OK |
| build_environment | ________________________ | [ ] OK |

**TAGGING DE ARTEFATOS:**

| Tag | Significado | Exemplo | Status |
|-----|------------|--------|--------|
| **:latest** | Última versão | app:latest | [ ] OK |
| **:v1.2.3** | Versão específica | app:v1.2.3 | [ ] OK |
| **:sha256-abc** | SHA256 do digest | app@sha256:abc... | [ ] OK |
| **:feature-xxx** | Feature branch | app:feature-oauth2 | [ ] OK |
| **:PR-123** | Pull request | app:pr-123 | [ ] OK |

---

## D4: PUBLICAÇÃO DE RESULTADOS

---

### 🔄 D4: Worker Agent - Publicação de Resultados

**Timestamp Execução:** 2026-__-__ __:__:__ UTC  
**Pod Worker:** _________________________________  
**Ticket ID (Capturado em C4):** ________________________

**INPUT (Comandos Executados):**
```
# Logs de KafkaResultProducer
kubectl logs --tail=200 -n neural-hive _________________________________ | \
  grep -E "(KafkaResultProducer|publish_result|execution.results)" | \
  tail -20

# Verificar resultados no Kafka
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.results \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true \
  --property key.separator=" : "
```

**OUTPUT (Logs de Publicação - RAW):**
```
[INSERIR LOGS DE PUBLICAÇÃO AQUI]
```

**OUTPUT (Resultados no Kafka - RAW):**
```
[INSERIR RESULTADOS NO KAFKA AQUI]
```

**ANÁLISE DE PUBLICAÇÃO:**

| Item | Valor | Status |
|------|-------|--------|
| Resultado publicado? | [ ] Sim [ ] Não | [ ] OK |
| Topic de destino | execution.results | [ ] OK |
| Formato da mensagem | [ ] Avro [ ] JSON | [ ] OK |
| Acknowledgment recebido? | [ ] Sim [ ] Não | [ ] OK |
| Flush realizado? | [ ] Sim [ ] Não | [ ] OK |

**CAMPOS DO RESULTADO:**

| Campo | Valor | Status |
|-------|-------|--------|
| ticket_id | ________________________ | [ ] OK |
| task_type | ________________________ | [ ] OK |
| status | [ ] COMPLETED [ ] FAILED | [ ] OK |
| execution_time_ms | _________ | [ ] OK |
| artifacts | [ ] Presentes [ ] Ausentes | [ ] OK |
| error_message | [ ] Ausente [ ] Presente | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Resultado não publicado: ________________________
[ ] Acknowledgment não recebido: ________________________
[ ] Mensagem com erro: ________________________

---

## D5: DEAD LETTER QUEUE E ALERTAS

---

### 🔄 D5: Worker Agent - Dead Letter Queue e Alertas

**Timestamp Execução:** 2026-__-__ __:__:__ UTC  
**Pod Worker:** _________________________________

**INPUT (Comandos Executados):**
```
# Verificar DLQ
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets.dlq \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true

# Logs de DLQ Alert Manager
kubectl logs --tail=100 -n neural-hive _________________________________ | \
  grep -E "(DLQ|dead.*letter|alert|SRE)" | \
  tail -20
```

**OUTPUT (DLQ - RAW):**
```
[INSERIR MENSAGENS NA DLQ AQUI]
```

**OUTPUT (Alertas SRE - RAW):**
```
[INSERIR ALERTAS SRE AQUI]
```

**ANÁLISE DE DLQ:**

| Item | Valor | Status |
|------|-------|--------|
| Mensagens na DLQ? | [ ] Sim [ ] Não | [ ] OK |
| Número de mensagens | _____ mensagens | [ ] OK |
| Alertas SRE gerados? | [ ] Sim [ ] Não | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Mensagens presas na DLQ: ________________________
[ ] Alertas SRE não gerados: ________________________

---

## D6: RESUMO DA EXECUÇÃO

---

### 🔄 D6: Worker Agent - Resumo da Execução

**Timestamp Execução:** 2026-__-__ __:__:__ UTC  
**Pod Worker:** _________________________________

**RESUMO DA EXECUÇÃO:**

| Métrica | Valor | Status |
|----------|-------|--------|
| Tickets consumidos | _____ tickets | [ ] OK |
| Tickets processados com sucesso | _____ tickets | [ ] OK |
| Tickets falharam | _____ tickets | [ ] OK |
| Tickets na DLQ | _____ tickets | [ ] OK |
| Tempo médio de execução | _________ ms | [ ] OK |
| Taxa de sucesso | _________ % | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Alta taxa de falhas: ________________________
[ ] Backpressure detectado: ________________________

---

## ANÁLISE FINAL

---

### 5.1 Correlação de IDs de Ponta a Ponta

**MATRIZ DE CORRELAÇÃO:**

| ID | Tipo | Capturado em | Propagou para | Status |
|----|------|-------------|----------------|--------|
| Intent ID | intent_id | Seção 2.2 | STE, Kafka, Redis | [ ] ✅ [ ] ❌ |
| Correlation ID | correlation_id | Seção 2.2 | Gateway, Kafka, Redis | [ ] ✅ [ ] ❌ |
| Trace ID | trace_id | Seção 2.2 | Gateway, Jaeger | [ ] ✅ [ ] ❌ |
| Plan ID | plan_id | Seção 3.3 | Kafka, MongoDB | [ ] ✅ [ ] ❌ |
| Decision ID | decision_id | Seção C2 | Kafka, Orchestrator | [ ] ✅ [ ] ❌ |
| Ticket IDs | ticket_ids | Seção C4 | Kafka, MongoDB | [ ] ✅ [ ] ❌ |
| Worker IDs | worker_ids | Seção C5 | Service Registry, Orchestrator | [ ] ✅ [ ] ❌ |
| Telemetry IDs | telemetry_ids | Seção C6 | Kafka, MongoDB | [ ] ✅ [ ] ❌ |

**RESUMO DE PROPAGAÇÃO:**
- IDs propagados com sucesso: _____ / 8
- IDs não propagados: _____ / 8
- Quebras na cadeia de rastreamento: [ ] Nenhuma [ ] Descrever: ________________________

---

### 5.2 Timeline de Latências End-to-End

**TIMELINE COMPLETA:**

| Etapa | Início | Fim | Duração | SLO | Status |
|-------|--------|------|----------|-----|--------|
| Worker - Ingestão de Tickets | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <500ms | [ ] ✅ [ ] ❌ |
| Worker - Processamento de Tickets | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <5000ms | [ ] ✅ [ ] ❌ |
| Worker - Build + Artefatos | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <30000ms | [ ] ✅ [ ] ❌ |
| Worker - Publicação Resultados | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <500ms | [ ] ✅ [ ] ❌ |

**RESUMO DE SLOS:**
- SLOs passados: _____ / 20
- SLOs excedidos: _____ / 20
- Tempo total end-to-end: _____ segundos

**GARGALOS IDENTIFICADOS:**
1. Etapa mais lenta: ________________________ (_____ ms)
2. Etapa com mais violações de SLO: ________________________
3. Anomalias de latência: ________________________

---

### 5.3 Matriz de Qualidade de Dados

**QUALIDADE POR ETAPA:**

| Etapa | Completude | Consistência | Integridade | Validade | Pontuação |
|-------|-----------|--------------|------------|---------|----------|
| Worker - Ingestão de Tickets | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Worker - Processamento de Tickets | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Worker - Build + Artefatos | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Worker - Resultados Kafka | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Worker - DLQ e Alertas | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |

**RESUMO DE QUALIDADE:**
- Pontuação máxima possível: 20 pontos
- Pontuação obtida: _____ pontos (_____ %)
- Qualidade geral: [ ] Excelente (>80%) [ ] Boa (60-80%) [ ] Média (40-60%) [ ] Baixa (<40%)

---

### 5.4 Matriz de Validação - Critérios de Aceitação

**CRITÉRIOS FUNCIONAIS:**

| Critério | Especificado | Resultado | Status |
|----------|-------------|-----------|--------|
| Worker consome tickets | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Worker processa tickets | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| BuildExecutor gera build + artefatos | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Worker gera build + artefatos | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Worker publica resultados | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Worker gerencia DLQ | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |

**RESUMO DE VALIDAÇÃO:**
- Critérios funcionais passados: _____ / 7
- Critérios de performance passados: _____ / 4
- Taxa geral de sucesso: _____ % (_____ / 11)

**CRITÉRIOS DE PERFORMANCE:**

| Critério | Especificado | Resultado | Status |
|----------|-------------|-----------|--------|
| Worker ingestão latência < 500ms | Sim | _____ ms | [ ] ✅ [ ] ❌ |
| Worker processamento latência < 5s | Sim | _____ ms | [ ] ✅ [ ] ❌ |
| Worker build latência < 30s | Sim | _____ ms | [ ] ✅ [ ] ❌ |
| Worker publicação latência < 500ms | Sim | _____ ms | [ ] ✅ [ ] ❌ |

---

### 5.5 Problemas e Anomalias Identificadas

**PROBLEMAS CRÍTICOS (Bloqueadores):**

| ID | Problema | Severidade | Etapa Afetada | Impacto | Status |
|----|----------|-------------|----------------|---------|--------|
| P1 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| P2 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| P3 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |

**PROBLEMAS NÃO CRÍTICOS (Observabilidade):**

| ID | Problema | Severidade | Etapa Afetada | Impacto | Status |
|----|----------|-------------|----------------|---------|--------|
| O1 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| O2 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| O3 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |

**ANOMALIAS DE PERFORMANCE:**

| Etapa | Problema | Medido | Esperado | Desvio | Status |
|-------|----------|---------|----------|--------|--------|
| ____________ | ________________________ | _____ ms | _____ ms | _____ % | [ ] Investigado [ ] Aceito |
| ____________ | ________________________ | _____ ms | _____ ms | _____ % | [ ] Investigado [ ] Aceito |
| ____________ | ________________________ | _____ ms | _____ ms | _____ % | [ ] Investigado [ ] Aceito |

---

## CONCLUSÃO FINAL

### 6.1 Status Geral do Worker Agent

**RESULTADO DO TESTE:**

| Fluxo | Status | Taxa de Sucesso | Observações |
|-------|--------|------------------|-------------|
| D1 (Ingestão de Tickets) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| D2 (Processamento de Tickets) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| D3 (Build + Artefatos) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| D4 (Publicação de Resultados) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| D5 (DLQ e Alertas) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| Worker Agent Completo | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |

**VEREDITO FINAL:**
[ ] ✅ **APROVADO** - Worker Agent funcionando conforme especificação
[ ] ⚠️ **APROVADO COM RESERVAS** - Worker Agent funcionando mas com problemas menores
[ ] ❌ **REPROVADO** - Worker Agent com bloqueadores críticos

---

### 6.2 Recomendações

**RECOMENDAÇÕES IMEDIATAS (Bloqueadores Críticos):**

1. [ ] ________________________
   - Prioridade: [ ] P0 (Crítica) [ ] P1 (Alta)
   - Responsável: ________________________
   - Estimativa: ______ horas

2. [ ] ________________________
   - Prioridade: [ ] P0 (Crítica) [ ] P1 (Alta)
   - Responsável: ________________________
   - Estimativa: ______ horas

**RECOMENDAÇÕES DE CURTO PRAZO (1-3 dias):**

1. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ dias

2. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ dias

**RECOMENDAÇÕES DE MÉDIO PRAZO (1-2 semanas):**

1. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ semanas

2. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ semanas

---

### 6.3 Assinatura e Data

**TESTADOR RESPONSÁVEL:**

Nome: ______________________________________________________
Função: ______________________________________________________
Email: ______________________________________________________

**APROVAÇÃO DO TESTE:**

[ ] Aprovado por: ______________________________________________________
[ ] Data de aprovação: 2026-__-__ __/__

**ASSINATURA:**
____________________________________________________

---

## ANEXOS - EVIDÊNCIAS TÉCNICAS

### A1. IDs de Rastreamento Capturados

- Intent ID: ________________________________________
- Correlation ID: ________________________________________
- Trace ID: ______________________________________________________
- Span ID: ______________________________________
- Plan ID: ________________________________________
- Decision ID: ________________________________________
- Ticket IDs (5 primeiros): _________________________________________________
- Worker IDs (ativos): _________________________________________________
- Telemetry IDs (últimos 3): _________________________________________________
- Result IDs (últimos 5): _________________________________________________
- Artifact IDs (gerados): _________________________________________________

### A2. Comandos Executados (para reprodutibilidade)

```bash
# 1. PREPARAÇÃO DO AMBIENTE

# Verificar todos os pods
kubectl get pods -A | grep -E "(neural-hive|code-forge|service-registry|execution-ticket|approval|kafka|mongodb|redis)"

# Verificar status do Worker Agent
kubectl get pods -n neural-hive -l app=worker-agents

# Verificar status do CodeForge
kubectl get pods -n neural-hive-execution -l app=code-forge

# Verificar status do Service Registry
kubectl get pods -n neural-hive -l app=service-registry

# Verificar status do Execution Ticket Service
kubectl get pods -n neural-hive -l app=execution-ticket-service

# Verificar status do Approval Service
kubectl get pods -n neural-hive -l app=approval-service

# Verificar status do Kafka
kubectl get pods -n kafka -l app=neural-hive-kafka

# Verificar status do MongoDB
kubectl get pods -n mongodb-cluster -l app=mongodb

# Verificar status do Redis
kubectl get pods -n redis-cluster -l app=redis

# 2. PORT-FORWARDS

# Port-forward CodeForge Service
kubectl port-forward -n neural-hive-execution svc/code-forge 8000:8000 &

# Port-forward Service Registry
kubectl port-forward -n neural-hive svc/service-registry 8080:8080 &

# Port-forward Execution Ticket Service
kubectl port-forward -n neural-hive svc/execution-ticket-service 8001:8000 &

# Port-forward Approval Service
kubectl port-forward -n neural-hive svc/approval-service 8082:8080 &

# 3. VERIFICAÇÃO DE CONEXÕES

# Verificar conexão MongoDB
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.adminCommand('ping')" --quiet

# Verificar conexão Redis
kubectl exec -n redis-cluster redis-66b84474ff-tv686 -- redis-cli PING

# Verificar conexão Kafka - Listar topics
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

# Verificar conexão CodeForge
curl -s http://localhost:8000/health | jq .

# Verificar conexão Service Registry
curl -s http://localhost:8080/health | jq .

# Verificar conexão Execution Ticket Service
curl -s http://localhost:8001/health | jq .

# Verificar conexão Approval Service
curl -s http://localhost:8082/health | jq .

# 4. TESTE DE WORKER AGENT

# Logs de Worker Agent - Ingestão
kubectl logs --tail=200 -n neural-hive worker-agents-________ | \
  grep -E "(KafkaTicketConsumer|ticket.*consumed|ingestion)" | \
  tail -30

# Logs de Worker Agent - Processamento
kubectl logs --tail=500 -n neural-hive worker-agents-________ | \
  grep -E "(ExecutionEngine|process_ticket|dependencies)" | \
  tail -30

# Logs de Worker Agent - Build
kubectl logs --tail=500 -n neural-hive worker-agents-________ | \
  grep -E "(BuildExecutor|CodeForge|trigger_pipeline|build_completed)" | \
  tail -30

# Logs de Worker Agent - Publicação
kubectl logs --tail=200 -n neural-hive worker-agents-________ | \
  grep -E "(KafkaResultProducer|publish_result|execution.results)" | \
  tail -20

# Logs de Worker Agent - DLQ
kubectl logs --tail=100 -n neural-hive worker-agents-________ | \
  grep -E "(DLQ|dead.*letter|alert)" | \
  tail -20

# 5. VERIFICAÇÃO NO KAFKA

# Verificar tickets de execução
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true \
  --property key.separator=" : "

# Verificar resultados de execução
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.results \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true \
  --property key.separator=" : "

# Verificar Dead Letter Queue
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets.dlq \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true

# 6. VERIFICAÇÃO NO MONGODB

# Verificar tickets de execução
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/neural_hive?authSource=admin" \
  --eval "db.execution_tickets.findOne({ticket_id: 'TICKET_ID_AQUI'}, {_id: 0})" --quiet

# Verificar artefatos CodeForge
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/code_forge?authSource=admin" \
  --eval "db.artifacts.findOne({ticket_id: 'TICKET_ID_AQUI'}, {_id: 0})" --quiet

# Verificar pipelines CodeForge
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/code_forge?authSource=admin" \
  --eval "db.pipelines.findOne({pipeline_id: 'PIPELINE_ID_AQUI'}, {_id: 0})" --quiet

# Verificar resultados de validação
kubectl exec -n mongodb-cluster mongodb-677c7746c4-rwwsb -- mongosh \
  "mongodb://root:local_dev_password@localhost:27017/code_forge?authSource=admin" \
  --eval "db.validation_results.find({ticket_id: 'TICKET_ID_AQUI'}).limit(5)" --quiet

# 7. VERIFICAÇÃO NO REDIS

# Verificar tickets processados
kubectl exec -n redis-cluster redis-66b84474ff-tv686 -- \
  redis-cli KEYS "ticket:processed:*" | head -10

# Verificar tickets em processamento
kubectl exec -n redis-cluster redis-66b84474ff-tv686 -- \
  redis-cli KEYS "ticket:processing:*" | head -10

# 8. API CALLS

# Trigger pipeline no CodeForge
curl -s -X POST http://localhost:8000/api/v1/pipelines \
  -H "Content-Type: application/json" \
  -d '{"artifact_id": "myapp-api", "parameters": {}}' | jq .

# Obter status do pipeline
curl -s http://localhost:8000/api/v1/pipelines/PIPELINE_ID_AQUI | jq .

# Obter ticket de execução
curl -s http://localhost:8001/api/v1/tickets/TICKET_ID_AQUI | jq .

# Obter aprovações
curl -s http://localhost:8082/api/v1/approvals/PLAN_ID_AQUI | jq .
```

### A3. Scripts de Coleta de Evidências

```
[INSERIR SCRIPTS CUSTOMIZADOS UTILIZADOS DURANTE O TESTE]
```

### A4. Screenshots/Capturas (referências)

```
[INSERIR REFERÊNCIAS PARA SCREENSHOTS OU CAPTURAS DE TELA]
```

---

## CHECKLIST FINAL DE TESTE

**PREPARAÇÃO DO AMBIENTE:**
[ ] Todos os pods verificados e running
[ ] Port-forward CodeForge estabelecido (8000:8000)
[ ] Port-forward Service Registry estabelecido (8080:8080)
[ ] Port-forward Execution Ticket Service estabelecido (8001:8000)
[ ] Port-forward Approval Service estabelecido (8082:8080)
[ ] Acesso ao MongoDB verificado
[ ] Acesso ao Redis verificado
[ ] Acesso ao Kafka verificado
[ ] Todos os topics Kafka existem
[ ] Conexões com serviços validadas
[ ] Documento preenchido e salvo antes do teste
[ ] Horário de início registrado

**EXECUÇÃO:**
[ ] Fluxo D1 executado completamente
[ ] Fluxo D2 executado completamente
[ ] Fluxo D3 executado completamente
[ ] Fluxo D4 executado completamente
[ ] Fluxo D5 executado completamente
[ ] Fluxo D6 executado completamente
[ ] Todos os dados capturados em tempo real
[ ] Evidências salvas durante o teste
[ ] Logs coletados para cada etapa
[ ] IDs de rastreamento registrados

**FINALIZAÇÃO:**
[ ] Análises completas realizadas
[ ] Matrizes preenchidas
[ ] Problemas identificados
[ ] Recomendações elaboradas
[ ] Documento revisado e finalizado
[ ] Horário de término registrado
[ ] Relatório assinado

---

## FIM DO DOCUMENTO DE TESTE

**Versão do documento:** 1.0
**Data de criação:** 2026-02-23
**Última atualização:** 2026-__-__ __/__
**Próximo teste agendado para:** 2026-__-__ __/__
