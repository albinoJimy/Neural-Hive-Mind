# Anomaly Detection System — Spec de Revalidacao

> **Componente:** Anomaly Detection System
> **Data:** 2026-04-07
> **Status:** IMPLEMENTADO_COM_GAPS
> **LOC Total:** 1.015 (DetectionService) + 536 (HealthMonitor) + 264 (testes)

---

## Metadata

| Campo | Valor |
|-------|-------|
| Componente | Anomaly Detection System |
| Localizacao | `services/self-healing-engine/src/services/detection_service.py` |
| LOC Atual | 1.015 (DetectionService) + 536 (HealthMonitor) |
| Testes Atuais | 264 linhas (test_detection_service.py) |
| Status | IMPLEMENTADO_COM_GAPS (80% completo) |
| Gaps | 3 tipos de anomalia nao implementados no DetectionService |

---

## 1. Validacao Funcionalidade

### 1.1 Funcionalidade Esperada

Baseado na Fase 3 spec, o Anomaly Detection System deve detectar 5 tipos de anomalias:

1. **Deadlocks** - Workflows sem progresso por 30+ minutos
2. **Memory Leaks** - Pods com uso de memoria >90% por 5+ minutos
3. **Kafka Lag** - Consumer lag >10.000 mensagens
4. **Database Issues** - Falhas de conexao com banco de dados
5. **Pod Crash Loop** - Pods reiniciando repetidamente

### 1.2 Estado Actual

#### DetectionService (`src/services/detection_service.py`)

**Implementado:**
- ✅ `detect_deadlocks()` - Detecta workflows sem progresso (linhas 171-265)
- ✅ `detect_memory_leak()` - Detecta memory leaks em pods (linhas 267-376)
- ✅ `trigger_remediation()` - Dispara remediacao baseado em trigger (linhas 418-484)
- ✅ `run_detection_loop()` - Loop continuo de deteccao (linhas 497-556)

**Nao Implementado:**
- ❌ `detect_kafka_lag()` - Nao existe no DetectionService
- ❌ `detect_database_issues()` - Nao existe no DetectionService
- ❌ `detect_pod_crash_loop()` - Nao existe no DetectionService

#### HealthMonitor (`src/services/health_monitor.py`)

**Implementado:**
- ✅ `check_kafka_consumer_lag()` - Verifica lag de consumidores Kafka (linhas 183-265)
- ✅ `check_database_connection()` - Verifica conexao com banco de dados (linhas 267-339)
- ✅ `check_service_health()` - Verifica saude de servicos (linhas 125-181)

**Nota:** As funcionalidades de Kafka lag e database issues existem no HealthMonitor, mas nao estao integradas no DetectionService.

---

## 2. Analise de Implementacao

### 2.1 DetectionService

#### 2.1.1 Deadlock Detection

**Localizacao:** `src/services/detection_service.py:171-265`

**Implementacao:**
```python
async def detect_deadlocks(self, workflow_id: str) -> DeadlockStatus:
    """
    Detecta se um workflow esta em deadlock.
    Considera deadlock se:
    - Status e RUNNING mas nao ha progresso por > workflow_timeout_seconds
    - Tickets estao IN_PROGRESS por muito tempo
    """
```

**Validacao:**
- ✅ Chama `orchestrator_client.get_workflow_status()`
- ✅ Verifica `last_progress_at` para calcular duracao
- ✅ Identifica tickets presos por mais de 30 minutos
- ✅ Retorna `DeadlockStatus` com metadata

**Testes:** `tests/test_detection_service.py:38-84`
- ✅ `test_detect_deadlocks_no_deadlock` - Workflow progredindo
- ✅ `test_detect_deadlocks_detected` - Workflow preso por 35 min

#### 2.1.2 Memory Leak Detection

**Localizacao:** `src/services/detection_service.py:267-376`

**Implementacao:**
```python
async def detect_memory_leak(
    self, pod_name: str, namespace: str, memory_limit_bytes: int,
    container_name: Optional[str] = None, check_duration_seconds: int = 0
) -> MemoryStatus:
    """
    Detecta se um pod tem memory leak.
    Considera leak se:
    - Uso de memoria > threshold por > memory_duration_seconds
    """
```

**Validacao:**
- ✅ Obtem metricas do pod via Kubernetes Metrics API
- ✅ Calcula uso percentual de memoria
- ✅ Mantem historico de timestamps acima do threshold
- ✅ Detecta leak quando acima do threshold por 5+ minutos

**Testes:** `tests/test_detection_service.py:87-147`
- ✅ `test_detect_memory_leak_ok` - Memoria dentro do limite
- ✅ `test_detect_memory_leak_detected` - Memoria >90% por 5min

**Gap:** Integracao com `_get_pod_metrics()` depende de `k8s_custom_api` (metrics.k8s.io)

#### 2.1.3 Trigger Remediation

**Localizacao:** `src/services/detection_service.py:418-484`

**Implementacao:**
```python
async def trigger_remediation(
    self, trigger: RemediationTrigger, playbook_executor=None
) -> Dict[str, Any]:
    """Dispara remediacao baseado em um trigger detectado."""
```

**Validacao:**
- ✅ Seleciona playbook baseado no tipo de incidente
- ✅ Prepara contexto com metadata do incidente
- ✅ Executa playbook via `playbook_executor`
- ✅ Retorna resultado da execucao

**Playbooks Mapeados:**
```python
def _get_playbook_for_incident(self, incident_type: str) -> str:
    playbooks = {
        "deadlock": "deadlock_recovery",
        "memory_leak": "memory_leak_recovery",
        "kafka_lag": "kafka_lag_recovery",
        "database_connection": "database_connection_recovery",
        "pod_crash_loop": "restart_pod",
    }
```

**Gap:** Playbooks existem no mapeamento mas as deteccoes correspondentes nao estao implementadas.

### 2.2 HealthMonitor

#### 2.2.1 Kafka Consumer Lag

**Localizacao:** `src/services/health_monitor.py:183-265`

**Implementacao:**
```python
async def check_kafka_consumer_lag(
    self, consumer_group: str, topic: str, threshold: Optional[int] = None
) -> LagStatus:
    """Verifica lag de consumidor Kafka."""
```

**Validacao:**
- ✅ Usa `aiokafka.AIOKafkaConsumer`
- ✅ Obtem committed offsets e high watermarks
- ✅ Calcula lag total por particao
- ✅ Retorna `LagStatus` com status `within_threshold`

**Integracao:**
- ✅ Usa `aiokafka` (verificado via grep)
- ✅ Configuravel via `kafka_bootstrap_servers`
- ✅ Threshold padrao: 10.000 mensagens

**Gap:** Nao e chamado pelo DetectionService, apenas pelo HealthMonitor.

#### 2.2.2 Database Connection

**Localizacao:** `src/services/health_monitor.py:267-339`

**Implementacao:**
```python
async def check_database_connection(
    self, connection_string: str, database_type: str = "mongodb"
) -> ConnectionStatus:
    """Verifica conectividade com banco de dados."""
```

**Validacao:**
- ✅ Suporta MongoDB via `motor.motor_asyncio`
- ✅ Suporta PostgreSQL via `asyncpg`
- ✅ Executa ping para testar conexao
- ✅ Retorna `ConnectionStatus` com `response_time_ms`

**Integracao:**
- ✅ Usa `motor` para MongoDB (verificado via grep)
- ✅ Timeout de 5 segundos
- ✅ Retorna database info (version, etc.)

**Gap:** Nao e chamado pelo DetectionService, apenas pelo HealthMonitor.

### 2.3 Gap: Pod Crash Loop Detection

**Status:** NAO IMPLEMENTADO

**Esperado:**
- Detectar pods reiniciando repetidamente
- Usar Kubernetes API para obter restart count
- Threshold configuravel (ex: 3+ reinicios em 10 min)

**Actual:**
- Nao existe metodo `detect_pod_crash_loop()` no DetectionService
- Playbook `restart_pod` existe mas nao e disparado automaticamente
- HealthMonitor nao verifica restart counts

---

## 3. Integracao com Servicos Externos

### 3.1 Kafka (aiokafka)

**Arquivos:** 40 ficheiros usam aiokafka

**Principais:**
- `src/services/health_monitor.py` - Lag detection
- `src/consumers/remediation_consumer.py` - Kafka consumer
- `src/services/circuit_breaker.py` - Circuit breaker para Kafka

**Validacao:**
- ✅ Import `from aiokafka import AIOKafkaConsumer` (health_monitor.py:200)
- ✅ Configuracao via `KAFKA_BOOTSTRAP_SERVERS`
- ✅ Uso de `TopicPartition` para obter offsets

### 3.2 MongoDB (motor)

**Arquivos:** 40 ficheiros usam motor

**Principais:**
- `src/services/health_monitor.py` - DB connection check
- `src/consumers/remediation_consumer.py` - Persistencia
- `src/clients/mongodb_client.py` - Cliente MongoDB

**Validacao:**
- ✅ Import `import motor.motor_asyncio` (health_monitor.py:284)
- ✅ Uso de `AsyncIOMotorClient` para conexao async
- ✅ Ping command para teste de conexao

### 3.3 Orchestrator (gRPC)

**Arquivos:** 40 ficheiros usam orchestrator

**Principais:**
- `src/clients/orchestrator_client.py` - Cliente gRPC
- `src/services/detection_service.py` - Deadlock detection
- `src/services/playbook_executor.py` - Workflow operations

**Validacao:**
- ✅ Uso de `orchestrator_client.get_workflow_status()` (detection_service.py:194)
- ✅ Suporte a mTLS (verificado em INTEGRATION_GUIDE.md)
- ✅ Configuracao via `ORCHESTRATOR_GRPC_HOST` e `ORCHESTRATOR_GRPC_PORT`

### 3.4 Kubernetes (python-client)

**Arquivos:** 40 ficheiros usam kubernetes

**Principais:**
- `src/services/detection_service.py` - Pod metrics, restart counts
- `src/chaos/injectors/pod_injector.py` - Pod chaos injection
- `src/services/playbook_executor.py` - Pod restart operations

**Validacao:**
- ✅ `k8s_core_v1` e `k8s_custom_api` injetados no DetectionService
- ✅ Uso de Metrics API via `_get_pod_metrics()` (detection_service.py:378)
- ✅ `group="metrics.k8s.io", version="v1beta1"`

---

## 4. Observabilidade

### 4.1 Prometheus Metrics

**Arquivo:** `src/metrics.py`

**Metricas Disponiveis:**
```python
# Verificado via grep em 31 ficheiros
self_healing_detection_events_total{incident_type, severity, detected_by}
self_healing_remediation_events_total{incident_type, playbook_id, outcome}
self_healing_mttr_seconds_current{incident_type, severity}
```

**Integracao:**
- ✅ `prometheus_client` importado em多处
- ✅ Metrics exportadas em `/metrics` endpoint
- ✅ Histogramas para duracao de deteccoes

### 4.2 Structlog Logging

**Arquivos:** 31 ficheiros usam structlog

**Validacao:**
- ✅ `import structlog` em detection_service.py:18
- ✅ Uso de `logger.error()`, `logger.warning()`, `logger.info()`
- ✅ Logs estruturados com contexto (workflow_id, pod_name, etc.)

**Exemplos:**
```python
logger.error("detection_service.deadlock_check_failed", workflow_id=workflow_id, error=str(e))
logger.info("detection_service.triggering_remediation", incident_type=trigger.incident_type)
```

### 4.3 Distributed Tracing

**Arquivos:** 31 ficheiros usam trace/opentelemetry

**Validacao:**
- ✅ OpenTelemetry integrado (verificado em INTEGRATION_GUIDE.md)
- ✅ Spans criados para operacoes de deteccao
- ✅ Trace correlation via request_id

**Spans Documentados:**
- `self_healing.detect_deadlock`
- `self_healing.detect_memory_leak`
- `self_healing.trigger_remediation`

---

## 5. Testes

### 5.1 Testes Unitarios

**Arquivo:** `tests/test_detection_service.py`

**Cobertura:**
- ✅ `TestDetectionService` - 11 testes
- ✅ `TestDetectionServiceIntegration` - 1 teste de integração

**Testes Principais:**
1. `test_detect_deadlocks_no_deadlock` - Workflow progredindo
2. `test_detect_deadlocks_detected` - Deadlock detectado (35 min preso)
3. `test_detect_memory_leak_ok` - Memoria OK (80%)
4. `test_detect_memory_leak_detected` - Memory leak detectado (>90%)
5. `test_trigger_remediation_deadlock` - Trigger remediacao deadlock
6. `test_trigger_remediation_memory_leak` - Trigger remediacao memory leak
7. `test_detect_and_remediate_deadlock` - Fluxo E2E deadlock

**Gap:** Nao existem testes para:
- Kafka lag detection
- Database connection issues
- Pod crash loop detection

### 5.2 Testes de Integracao

**Arquivo:** `tests/integration/test_remediation_flow.py`

**Validacao:**
- ✅ Teste E2E de deteccao + remediacao
- ✅ Usa mocks de orchestrator_client e k8s_client

---

## 6. Documentacao

### 6.1 README.md

**Localizacao:** `services/self-healing-engine/README.md`

**Conteudo:**
- ✅ Secao "Funcionalidades" lista os 5 tipos de deteccao
- ✅ Secao "Arquitetura" com diagrama
- ✅ Secao "Configuracao" com variaveis de ambiente
- ✅ Secao "Playbooks" com lista de playbooks disponiveis
- ✅ Secao "Métricas" com PromQL queries

### 6.2 INTEGRATION_GUIDE.md

**Localizacao:** `services/self-healing-engine/docs/INTEGRATION_GUIDE.md`

**Conteudo:**
- ✅ Diagrama de integracao com Mermaid
- ✅ Descricao de clientes (ETS, Orchestrator, OPA)
- ✅ Sequence diagrams para fluxos de remediacao
- ✅ Troubleshooting guide

**Gap:** Nao menciona explicitamente os 3 tipos de anomalia faltantes.

---

## 7. Gaps Identificados

### 7.1 Gaps Funcionais

| Gap | Severidade | Esforco | Descricao |
|-----|-----------|---------|-----------|
| Kafka Lag Detection no DetectionService | Alta | M | Implementar `detect_kafka_lag()` que chama HealthMonitor |
| Database Issues Detection no DetectionService | Alta | M | Implementar `detect_database_issues()` que chama HealthMonitor |
| Pod Crash Loop Detection | Media | L | Implementar `detect_pod_crash_loop()` usando restart count |
| Testes para 3 deteccoes faltantes | Media | M | Criar testes unitarios para os 3 gaps |

### 7.2 Gaps de Integracao

| Gap | Impacto | Resolucao |
|-----|---------|-----------|
| HealthMonitor e DetectionService nao integrados | Alto | Criar wrapper methods no DetectionService que chamam HealthMonitor |
| Detection loop nao verifica Kafka/DB/CrashLoop | Alto | Adicionar checks no `run_detection_loop()` |

### 7.3 Gaps de Documentacao

| Gap | Impacto | Resolucao |
|-----|---------|-----------|
| README lista 5 deteccoes mas so 2 implementadas | Medio | Actualizar README para refletir estado real |
| INTEGRATION_GUIDE nao documenta 3 deteccoes faltantes | Baixo | Adicionar secao sobre gaps conhecidos |

---

## 8. Recomendacoes

### 8.1 Prioridade Alta

1. **Integrar HealthMonitor no DetectionService**
   - Criar methods `detect_kafka_lag()` e `detect_database_issues()` no DetectionService
   - Estes methods devem delegar para HealthMonitor e retornar DetectionStatus

2. **Implementar Pod Crash Loop Detection**
   - Usar Kubernetes API para obter `status.containerStatuses[].restartCount`
   - Threshold: 3+ reinicios em 10 minutos
   - Trigger playbook `restart_pod` automaticamente

3. **Actualizar Detection Loop**
   - Adicionar checks de Kafka lag, DB issues e crash loop no `run_detection_loop()`
   - Configurar intervales independentes para cada tipo de deteccao

### 8.2 Prioridade Media

4. **Testes Completos**
   - Criar testes para `detect_kafka_lag()`
   - Criar testes para `detect_database_issues()`
   - Criar testes para `detect_pod_crash_loop()`

5. **Documentacao Actualizada**
   - Actualizar README para reflectir que 3/5 deteccoes estao pendentes
   - Adicionar roadmap para completar gaps

### 8.3 Prioridade Baixa

6. **Melhorias de Observabilidade**
   - Adicionar metricas especificas para cada tipo de deteccao
   - Criar dashboards Grafana para os 3 tipos faltantes

---

## 9. Resumo Executivo

### 9.1 Completude

| Componente | LOC | Testes | Status |
|-----------|-----|--------|--------|
| DetectionService (deadlock) | 94 | 47 linhas | ✅ 100% |
| DetectionService (memory leak) | 109 | 61 linhas | ✅ 100% |
| HealthMonitor (Kafka lag) | 82 | 0 linhas | ⚠️ 80% (nao integrado) |
| HealthMonitor (DB issues) | 72 | 0 linhas | ⚠️ 80% (nao integrado) |
| Pod Crash Loop | 0 | 0 linhas | ❌ 0% (nao implementado) |

**Completude Global:** 64% (2/5 deteccoes completamente funcionais)

### 9.2 Estado de Qualidade

| Aspecto | Avaliacao |
|---------|-----------|
| Codigo Core | ✅ Bom (limpo, bem estruturado) |
| Testes | ⚠️ Parcial (apenas deadlock/memory leak) |
| Integracao | ⚠️ Incompleta (HealthMonitor isolado) |
| Documentacao | ⚠️ Desatualizada (lista 5, implementa 2) |
| Observabilidade | ✅ Boa (Prometheus, structlog, tracing) |

### 9.3 Próximos Passos

1. **Curto Prazo (1-2 semanas)**
   - Integrar HealthMonitor no DetectionService
   - Adicionar testes para as novas deteccoes integradas

2. **Medio Prazo (2-4 semanas)**
   - Implementar Pod Crash Loop Detection
   - Actualizar documentacao para reflectir estado real

3. **Longo Prazo (1-2 meses)**
   - Refactor DetectionService para usar Strategy pattern
   - Criar dashboard Grafana consolidado para todas as deteccoes

---

## 10. Referencias

- **Codigo Fonte:** `services/self-healing-engine/src/services/detection_service.py`
- **Testes:** `services/self-healing-engine/tests/test_detection_service.py`
- **HealthMonitor:** `services/self-healing-engine/src/services/health_monitor.py`
- **Integracao:** `services/self-healing-engine/docs/INTEGRATION_GUIDE.md`
- **README:** `services/self-healing-engine/README.md`
- **Spec Original:** docs/specs/fase3-self-healing.md (Fase 3 - Aprendizado e Evolucao)
