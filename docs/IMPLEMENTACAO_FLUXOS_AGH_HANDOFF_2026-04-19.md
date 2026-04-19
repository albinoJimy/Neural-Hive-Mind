# Handoff: Implementação Fluxos A, G, H - Neural-Hive-Mind

**Data:** 2026-04-19
**Versão:** 1.0
**Status:** Ready for Implementation

---

## Resumo Executivo

Este documento contém specs completas e tickets decompostos para implementação dos três fluxos principais do Neural-Hive-Mind. Baseado em validação profunda do código por agentes especializados.

### Status Atual Consolidado

| Fluxo | Completude | Bloqueadores Críticos | Estimativa para 100% |
|-------|------------|----------------------|---------------------|
| **Fluxo A** (Intenções) | ~70% | Gateway "gordo", Correlation ID | 5 semanas |
| **Fluxo G** (Requirements→KG) | ~75% | test-generation sem Kafka | 5-8 semanas |
| **Fluxo H** (Legacy Migration) | ~80% | CDC reconnection, OOM, Race conditions | 8 semanas |

**Total Estimado:** 18-21 semanas de desenvolvimento para 100% de completude dos 3 fluxos.

---

# PARTE 1: FLUXO A - INTENTION FLOW

## Current State Validation

### Componentes Implementados

| Serviço | Status | LOC | Testes | Issues |
|---------|--------|-----|--------|--------|
| gateway-intencoes (8000) | ✅ Completo | ~2,500 | 191 | NLU embedded |
| semantic-translation-engine (8001) | ✅ Completo | ~1,800 | 143 | - |
| consensus-engine (8002) | ✅ Completo | ~1,200 | 68 | - |
| orchestrator-dynamic (8003) | ⚠️ 90% | ~2,100 | 50+ | Fluxo C incompleto |
| worker-agents (8005) | ✅ Completo | ~3,500 | 100+ | - |

**Total de testes automatizados:** ~550 testes

## Gaps Identificados

### Gap A-001: Gateway "Gordo" (Priority: HIGH)
NLU Pipeline está embutido no Gateway, violando SRP. Dificulta evolução independente do NLU.

**Evidência:**
```python
# services/gateway-intencoes/src/pipelines/nlu_pipeline.py
# 500+ linhas de NLU embedded no Gateway
```

### Gap A-002: Fluxo C Integration Incomplete (Priority: HIGH)
FlowCConsumer não está plenamente integrado no lifespan do Orchestrator.

### Gap A-003: Correlation ID Propagation (Priority: CRITICAL)
Correlation ID não é propagado consistentemente entre serviços. Dificulta debugging distribuído.

### Gap A-004: DLQ Reprocessing Rate Limiting (Priority: MEDIUM)
DLQ reprocessor pode sobrecarregar serviços durante reprocessamento massivo.

### Gap A-005: Adaptive NLU Thresholds (Priority: LOW)
Thresholds não são configuráveis por domínio em runtime.

## Tickets Fluxo A

### [REFACTOR-A-001]: Extract NLU Pipeline to Separate Service

**Tipo:** Refatoração
**Priority:** High
**Effort:** XL (3+ semanas)
**Dependencies:** Nenhum

**Descrição:** Extrair NLU Pipeline do Gateway para microserviço próprio (nlu-service).

**Arquivos:**
- NOVO: `services/nlu-service/` (serviço completo)
- MODIFICAR: `services/gateway-intencoes/src/main.py`
- MODIFICAR: `services/gateway-intencoes/src/pipelines/nlu_pipeline.py` (remover)

**Acceptance Criteria:**
- [ ] NLU service independente criado com FastAPI
- [ ] Gateway consome NLU via gRPC
- [ ] Cache Redis mantido no NLU service
- [ ] spaCy models com lazy loading
- [ ] Health checks específicos para NLU service
- [ ] 100% dos testes do Gateway passando após extração
- [ ] Documentação de API do NLU service gerada

---

### [FEAT-A-002]: Complete Orchestrator Fluxo C Integration

**Tipo:** Feature
**Priority:** High
**Effort:** M (1 semana)
**Dependencies:** Nenhum

**Descrição:** Completar integração do FlowCConsumer no Orchestrator Dynamic.

**Arquivos:**
- `services/orchestrator-dynamic/src/main.py` (lifespan)
- `services/orchestrator-dynamic/src/integration/flow_c_consumer.py`
- `services/orchestrator-dynamic/src/workflows/orchestration_workflow.py`

**Acceptance Criteria:**
- [ ] FlowCConsumer inicia corretamente no lifespan
- [ ] Approval responses roteados para Temporal workflows
- [ ] Correlation ID propagado do Fluxo C para D
- [ ] DLQ handler implementado para falhas
- [ ] 10+ testes de integração escritos

---

### [BUG-A-003]: Implement Consistent Correlation ID Propagation

**Tipo:** Bug
**Priority:** CRITICAL
**Effort:** S (2-3 dias)
**Dependencies:** Nenhum

**Descrição:** Implementar middleware W3C Trace Context em todos os serviços do Fluxo A.

**Arquivos:**
- `services/gateway-intencoes/src/main.py`
- `services/semantic-translation-engine/src/main.py`
- `services/consensus-engine/src/main.py`
- `services/orchestrator-dynamic/src/main.py`
- `services/worker-agents/src/main.py`

**Acceptance Criteria:**
- [ ] W3C Trace Context headers propagados em todos os requests Kafka
- [ ] traceparent e tracestate validados
- [ ] Métricas de trace correlation implementadas
- [ ] 20+ testes unitários para middleware
- [ ] Documentação de tracing distribuído criada

---

### [FEAT-A-004]: Implement DLQ Rate Limiter

**Tipo:** Feature
**Priority:** Medium
**Effort:** S (2-3 dias)
**Dependencies:** Nenhum

**Descrição:** Implementar token bucket rate limiter no DLQ reprocessor.

**Arquivos:**
- `services/semantic-translation-engine/src/services/dlq_reprocessor.py`
- `services/semantic-translation-engine/src/observability/metrics.py`

**Acceptance Criteria:**
- [ ] Token bucket rate limiter implementado
- [ ] Configuração ajustável via environment variables
- [ ] Métricas de rate limit emitidas
- [ ] 15+ testes unitários implementados

---

### [FEAT-A-005]: Externalize Adaptive NLU Thresholds

**Tipo:** Feature
**Priority:** Low
**Effort:** XS (1 dia)
**Dependencies:** [REFACTOR-A-001]

**Descrição:** Mover thresholds adaptativos do NLU para MongoDB/Redis.

**Arquivos:**
- `services/gateway-intencoes/src/pipelines/nlu_pipeline.py`
- `services/gateway-intencoes/src/config/settings.py`
- NOVO: `services/gateway-intencoes/src/config/adaptive_thresholds.py`

**Acceptance Criteria:**
- [ ] Thresholds carregados do MongoDB/Redis
- [ ] Cache TTL configurável
- [ ] Fallback para thresholds hardcoded
- [ ] 10+ testes unitários para configuração dinâmica
- [ ] Admin endpoint para atualizar thresholds runtime

---

## Priorização Sprint - Fluxo A

**Sprint 1 (3 semanas):**
1. [REFACTOR-A-001]: Extract NLU Pipeline
2. [BUG-A-003]: Correlation ID Propagation

**Sprint 2 (1 semana):**
3. [FEAT-A-002]: Complete Fluxo C Integration

**Sprint 3 (1 semana):**
4. [FEAT-A-004]: DLQ Rate Limiter
5. [FEAT-A-005]: Externalize Adaptive Thresholds

---

# PARTE 2: FLUXO G - REQUIREMENTS TO KNOWLEDGE GRAPH

## Current State Validation

### Services Analysis

| Serviço | Kafka | Status | Issues |
|---------|-------|--------|--------|
| requirements-engineering (8010) | ✅ | FULL | - |
| documentation-generation (8012/8014) | ✅ | FULL | - |
| **test-generation (8013)** | ❌ | **ISOLADO** | **CRÍTICO** |
| knowledge-graph-rag (8016) | N/A | HTTP-only | Design |
| approval-gateway (8017) | N/A | HTTP-only | Design |
| orchestrator-dynamic (8003) | ✅ | Workflow | Stub responses |

**Testes implementados:** ~50 testes

## Gaps Identificados

### Gap G-001: Test-Generation Kafka Integration (CRITICAL)
test-generation tem config Kafka mas **nenhum consumer/producer implementado**. Serviço está completamente isolado do pipeline.

**Evidência:**
```python
# services/test-generation/src/main.py (lines 1-91)
# ❌ NO Kafka initialization
# ❌ NO consumers/ directory
# ❌ NO producers/ directory
```

**Impacto:** Bloqueia automação do Fluxo G - testes não são triggers automaticamente.

### Gap G-002: Orchestrator Activities Return Stubs
Activities do Fluxo G retornam stubs quando http_client não está injetado.

**Evidência:**
```python
# services/orchestrator-dynamic/src/activities/fluxo_g_integration.py:52-61
if not _http_client:
    return {"requirements_set_id": f"REQ-SET-{plan_id}", "status": "stub"}
```

### Gap G-003: HTTP vs Kafka Pattern
Activities usam HTTP POST em vez de consumir eventos Kafka. Viola arquitetura event-driven.

## Tickets Fluxo G

### [FEAT-G-001]: Implement Test-Generation Kafka Consumer

**Tipo:** Feature
**Priority:** CRITICAL
**Effort:** L (2-3 semanas)
**Dependencies:** Nenhum

**Descrição:** Implementar integração Kafka completa para test-generation.

**Arquivos a CRIAR:**
- `services/test-generation/src/consumers/__init__.py`
- `services/test-generation/src/consumers/requirements_consumer.py`
- `services/test-generation/src/producers/__init__.py`
- `services/test-generation/src/producers/tests_producer.py`

**Arquivos a MODIFICAR:**
- `services/test-generation/src/main.py`
- `services/test-generation/src/config/settings.py`

**Implementation:**

```python
# services/test-generation/src/consumers/requirements_consumer.py
class RequirementsConsumer:
    """Consumes requirements.generated events from Kafka."""

    async def _handle_requirements_generated(self, data: dict):
        """Process requirements and trigger test generation."""
        requirements_set_id = data.get("requirements_set_id")
        requirements = data.get("requirements", [])

        # Call TestGenerator.generate_tests()
        # Publish tests.generated event
```

```python
# services/test-generation/src/producers/tests_producer.py
class TestsProducer:
    """Publishes tests.generated events to Kafka."""

    async def publish_tests_generated(
        self,
        test_suite_id: str,
        requirements_set_id: str,
        tests_count: int,
        test_types: List[str]
    )
```

**Acceptance Criteria:**
- [ ] Consumer subscribes to `requirements.generated` topic
- [ ] Consumer triggers `TestGenerator.generate_tests()` on message
- [ ] Producer publishes `tests.generated` event
- [ ] Integration tests com testcontainers Kafka
- [ ] Health check retorna `kafka_connected: true`
- [ ] E2E test: requirement → Kafka → test-generation → Kafka → tests

---

### [FEAT-G-002]: Add Test-Generation MongoDB Persistence

**Tipo:** Feature
**Priority:** HIGH
**Effort:** M (1 semana)
**Dependencies:** [FEAT-G-001]

**Descrição:** Persistir test suites gerados no MongoDB.

**Arquivos:**
- NOVO: `services/test-generation/src/repositories/test_suites_repository.py`
- MODIFICAR: `services/test-generation/src/db/mongodb.py`
- MODIFICAR: `services/test-generation/src/services/test_generator.py`

**MongoDB Schema:**
```python
{
  "_id": ObjectId,
  "test_suite_id": "TS-abc123",
  "plan_id": "plan-123",
  "requirements_set_id": "REQ-SET-456",
  "name": "Test Suite for Authentication",
  "test_cases": [...],
  "framework": "pytest",
  "language": "python",
  "total_tests": 5,
  "coverage_estimate": 0.8,
  "created_at": datetime,
  "updated_at": datetime
}
```

**Acceptance Criteria:**
- [ ] Test suites persistidos em `test_suites` collection
- [ ] Repository methods testados
- [ ] API endpoints `/tests/suites/{id}` e `/tests/suites`
- [ ] Integration tests com MongoDB testcontainers

---

### [REFACTOR-G-003]: Convert Orchestrator Activities to Kafka-First

**Tipo:** Refatoração
**Priority:** MEDIUM
**Effort:** XL (3+ semanas)
**Dependencies:** [FEAT-G-001]

**Descrição:** Refatorar activities do Fluxo G para consumir eventos Kafka em vez de HTTP calls.

**Arquivos:**
- `services/orchestrator-dynamic/src/activities/fluxo_g_integration.py`
- `services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py`
- NOVO: `services/orchestrator-dynamic/src/consumers/fluxo_g_events.py`

**Current Pattern (HTTP):**
```python
response = await _http_client.post(
    "http://requirements-engineering:8010/api/v1/requirements/from-plan",
    json={...},
    timeout=30.0
)
```

**Target Pattern (Kafka):**
```python
await _kafka_producer.publish_generate_requirements_event(
    plan_id=plan_id,
    cognitive_plan=cognitive_plan
)

result = await _kafka_consumer.wait_for_requirements(
    plan_id=plan_id,
    timeout=30.0
)
```

**Acceptance Criteria:**
- [ ] Activities publicam eventos Kafka
- [ ] Correlation ID pattern implementado
- [ ] Saga pattern para transações distribuídas
- [ ] Integration tests E2E com Kafka
- [ ] Fallback para HTTP se Kafka unavailable

---

### [FEAT-G-004]: Add Test-Generation Integration Tests

**Tipo:** Teste
**Priority:** HIGH
**Effort:** M (1 semana)
**Dependencies:** [FEAT-G-001]

**Descrição:** Adicionar testes de integração completos para test-generation Kafka flow.

**Arquivos:**
- NOVO: `services/test-generation/tests/integration/test_kafka_flow.py`
- NOVO: `services/test-generation/tests/integration/test_e2e_test_generation.py`
- MODIFICAR: `services/test-generation/tests/conftest.py`

**Acceptance Criteria:**
- [ ] 5+ integration tests adicionados
- [ ] Tests usam testcontainers para Kafka e MongoDB
- [ ] LLM calls mocked (sem OpenAI API key)
- [ ] CI/CD pipeline executa integration tests
- [ ] Coverage >80% para Kafka flow

---

## Priorização Sprint - Fluxo G

**Sprint 1 (3-4 semanas):**
1. [FEAT-G-001]: Test-Generation Kafka Integration (CRÍTICO)

**Sprint 2 (2 semanas):**
2. [FEAT-G-002]: MongoDB Persistence
3. [FEAT-G-004]: Integration Tests

**Sprint 3 (3+ semanas):**
4. [REFACTOR-G-003]: Convert to Kafka-First (Technical Debt)

---

# PARTE 3: FLUXO H - LEGACY MIGRATION

## Current State Validation

### Services Status

| Serviço | Status | LOC | Testes | Issues Críticos |
|---------|--------|-----|--------|-----------------|
| doc-ingestion (8018) | 95% | ~1,500 | 17 | Entity persistence stub |
| data-migration (8019) | 85% | ~2,700 | 17 | CDC, OOM, Race conditions |
| cutover-orchestrator | 90% | ~1,200 | 2 | - |

**Testes implementados:** ~36 testes

## Gaps Críticos Identificados

### Gap H-001: CDC Pipeline Reconnection Logic (CRITICAL)

**Problema:** CDC consumer NÃO tem lógica de reconexão. Para permanentemente em erro Kafka.

**Evidência:**
```python
# services/data-migration/src/services/cdc_pipeline.py:307-356
async for msg in self._consumer:
    try:
        # Process event
    except Exception as e:
        stats["errors"] += 1
        # ❌ NO RECONNECTION LOGIC
```

**Arquivo:** `services/data-migration/src/services/cdc_pipeline.py` (898 linhas)

---

### Gap H-002: Rollback Manager OOM Risk (CRITICAL)

**Problema:** Carrega tabela inteira em memória antes de upload S3.

**Evidência:**
```python
# services/data-migration/src/services/rollback_manager.py:284-296
all_data = []
while offset < total_count:
    batch = await postgres.fetch_batch(...)
    all_data.extend(batch)  # ❌ EVERYTHING IN MEMORY
```

**Arquivo:** `services/data-migration/src/services/rollback_manager.py` (741 linhas)

---

### Gap H-003: S3 Snapshot Race Conditions (CRITICAL)

**Problema:** Sem locking em writes S3. Jobs concorrentes podem corromper snapshots.

**Evidência:**
```python
# services/data-migration/src/services/rollback_manager.py:319-338
s3_client.put_object(
    bucket_name=self._bucket,
    key=key,
    data=BytesIO(compressed_data),
    # ❌ NO VERSIONING OR LOCKING
)
```

---

### Gap H-004: Entity Persistence Missing (CRITICAL)

**Problema:** Entidades extraídas não são persistidas (stub message).

**Evidência:**
```python
# services/doc-ingestion/src/api/routers/parsing.py:357
return {"message": "Entity persistence not implemented yet"}  # STUB
```

## Tickets Fluxo H

### [BUG-H-001]: Implement CDC Pipeline Reconnection Logic

**Tipo:** Bug
**Priority:** CRITICAL
**Effort:** L (2 semanas)
**Dependencies:** Nenhum

**Descrição:** Implementar lógica de reconexão com exponential backoff.

**Arquivos:**
- `services/data-migration/src/services/cdc_pipeline.py` (lines 307-356, 657-682)
- NOVO: `services/data-migration/src/services/reconnection_manager.py`

**Implementation:**

```python
class ReconnectionManager:
    """Gerencia reconexão Kafka com exponential backoff."""

    async def consume_with_reconnection(self, consumer, handler):
        """Consome com reconexão automática."""
        retry_count = 0
        max_retries = self._config.max_retries

        while retry_count < max_retries:
            try:
                async for msg in consumer:
                    await handler(msg)
                    retry_count = 0  # Reset on success
            except (KafkaError, ConnectionError) as e:
                retry_count += 1
                delay = min(
                    self._config.initial_delay * (2 ** retry_count),
                    self._config.max_delay
                )
                logger.warning("kafka_connection_lost",
                            retry=retry_count,
                            delay=delay)
                await asyncio.sleep(delay)
```

**Configuração:**
```python
kafka_reconnect_max_attempts: int = 50
kafka_reconnect_initial_delay_ms: int = 1000
kafka_reconnect_max_delay_ms: int = 300000
kafka_reconnect_backoff_multiplier: float = 2.0
```

**Acceptance Criteria:**
- [ ] CDC reconecta automaticamente após broker restart
- [ ] Consumer resume do último offset committed
- [ ] Reconnection attempts logged com backoff
- [ ] Health check retorna false quando Kafka down
- [ ] Unit tests para cenários de reconexão
- [ ] Integration test com Kafka failure simulado
- [ ] Sem data loss durante reconexão

---

### [BUG-H-002]: Fix Rollback Manager OOM Risk

**Tipo:** Bug
**Priority:** CRITICAL
**Effort:** L (2 semanas)
**Dependencies:** Nenhum

**Descrição:** Implementar streaming S3 upload em chunks.

**Arquivos:**
- `services/data-migration/src/services/rollback_manager.py` (lines 244-339, 442-503)

**Implementation:**

```python
async def _create_s3_snapshot_streaming(self, ...):
    """Stream data diretamente para S3 em chunks."""
    chunk_size = 10000
    chunk_number = 0

    async for batch in postgres.fetch_batches_streaming(
        table_name=table_mapping.source_table,
        batch_size=chunk_size,
    ):
        # Upload chunk como arquivo separado
        chunk_key = f"snapshots/{snapshot_id}/{table_name}_chunk{chunk_number:04d}.json.gz"
        await self._upload_chunk_to_s3(batch, chunk_key)
        chunk_number += 1

        # Criar/update manifest
        await self._update_manifest(snapshot_id, table_name, chunk_key)
```

**Configuração:**
```python
snapshot_chunk_size: int = 10000  # Rows per chunk
snapshot_max_memory_mb: int = 512
```

**Acceptance Criteria:**
- [ ] Snapshot de tabelas com 10M+ rows sem OOM
- [ ] Memory usage < limite configurado
- [ ] Chunks uploaded concorrentemente
- [ ] Manifest file criado com metadata
- [ ] Rollback restaura de chunks corretamente
- [ ] Integration test com 1M rows

---

### [BUG-H-003]: Implement S3 Snapshot Concurrency Control

**Tipo:** Bug
**Priority:** CRITICAL
**Effort:** M (1 semana)
**Dependencies:** Nenhum

**Descrição:** Implementar optimistic locking com S3 versioning.

**Arquivos:**
- `services/data-migration/src/services/rollback_manager.py` (lines 319-338, 456-477)

**Implementation:**

```python
async def _upload_snapshot_with_locking(
    self,
    snapshot_id: str,
    data: bytes,
    expected_version: Optional[str] = None
) -> str:
    """Upload com conditional write."""
    key = f"snapshots/{snapshot_id}.json.gz"

    # Check existing
    try:
        existing = await s3_client.head_object(Bucket=self._bucket, Key=key)
        existing_version = existing.get("VersionId")

        if expected_version and existing_version != expected_version:
            raise ConcurrentModificationError(
                f"Snapshot {snapshot_id} foi modificado por outro processo"
            )
    except S3ClientError (404):
        pass

    # Upload com versioning
    response = s3_client.put_object(
        Bucket=self._bucket,
        Key=key,
        Body=data,
        ContentEncoding="gzip",
    )

    return response.get("VersionId")
```

**Acceptance Criteria:**
- [ ] Writes concorrentes detectados e rejeitados
- [ ] Optimistic locking previne corrupção
- [ ] Version IDs rastreados em metadata
- [ ] Error message claro em concurrent modification
- [ ] Unit tests com asyncio.gather
- [ ] Integration test com jobs concorrentes

---

### [FEAT-H-004]: Implement Entity Persistence

**Tipo:** Feature
**Priority:** CRITICAL
**Effort:** M (1 semana)
**Dependencies:** Nenhum

**Descrição:** Implementar persistência de entidades extraídas no MongoDB.

**Arquivos:**
- NOVO: `services/doc-ingestion/src/repositories/entity_repository.py`
- MODIFICAR: `services/doc-ingestion/src/api/routers/parsing.py` (line 357)
- MODIFICAR: `services/doc-ingestion/src/models/entities.py`

**Implementation:**

```python
# services/doc-ingestion/src/repositories/entity_repository.py
class EntityRepository:
    """Repository para entidades extraídas."""

    async def save_entities(
        self,
        document_id: str,
        entities: List[ExtractedEntity]
    ) -> int:
        """Persiste entidades no MongoDB."""
        client = await get_mongodb_client()
        collection = client.db.get_collection("entities")

        entities_to_insert = [
            {
                **entity.model_dump(),
                "document_id": document_id,
                "extracted_at": datetime.now(timezone.utc),
            }
            for entity in entities
        ]

        result = await collection.insert_many(entities_to_insert)
        return len(result.inserted_ids)

    async def get_entities_by_document(self, document_id: str) -> List[ExtractedEntity]:
        """Recupera entidades de um documento."""
        # Implementation
```

**Acceptance Criteria:**
- [ ] Entidades persistidas em `entities` collection
- [ ] Indexes criados (document_id, type, text search)
- [ ] Duplicates previnidos
- [ ] Search endpoint: GET /entities/search
- [ ] Unit + Integration tests

---

### [FEAT-H-005]: Add Pause/Resume Endpoints

**Tipo:** Feature
**Priority:** HIGH
**Effort:** S (2-3 dias)
**Dependencies:** Nenhum

**Descrição:** Expor endpoints de pause/resume para migrations.

**Arquivos:**
- `services/data-migration/src/api/routers/migrations.py`

**Implementation:**

```python
@router.post("/{job_id}/pause")
async def pause_migration(job_id: str):
    """Pausa uma migration em execução."""
    orchestrator = get_migration_orchestrator(job_id)
    job = await get_migration_job(job_id)

    success = await orchestrator.pause_migration(job)
    if not success:
        raise HTTPException(400, f"Cannot pause job in state {job.status}")

    job.status = "paused"
    job.paused_at = datetime.now(timezone.utc)
    await update_migration_job(job_id, job)

    return {"job_id": job_id, "status": "paused"}

@router.post("/{job_id}/resume")
async def resume_migration(job_id: str):
    """Retoma uma migration pausada."""
    # Similar implementation
```

**Acceptance Criteria:**
- [ ] POST /migrations/{id}/pause funciona
- [ ] POST /migrations/{id}/resume funciona
- [ ] 404 se job não existe
- [ ] 400 se state não permite pause/resume
- [ ] Job status atualizado no MongoDB

---

### [FEAT-H-006]: Add Document Download Endpoint

**Tipo:** Feature
**Priority:** HIGH
**Effort:** S (2-3 dias)
**Dependencies:** Nenhum

**Descrição:** Permitir download de documentos originais.

**Arquivos:**
- `services/doc-ingestion/src/api/routers/documents.py`
- `services/doc-ingestion/src/clients/s3_client.py`

**Acceptance Criteria:**
- [ ] GET /documents/{id}/download retorna arquivo
- [ ] Content-Type correto
- [ ] Content-Disposition header para browser download
- [ ] 404 se documento não existe

---

### [REFACTOR-H-007]: Implement Prometheus Metrics

**Tipo:** Refatoração
**Priority:** MEDIUM
**Effort:** M (1 semana)
**Dependencies:** Nenhum

**Descrição:** Completar implementação de métricas Prometheus.

**Arquivos:**
- NOVO: `services/data-migration/src/services/metrics.py`
- MODIFICAR: `services/data-migration/src/main.py`

**Métricas:**
```python
from prometheus_client import Counter, Histogram, Gauge

cdc_events_processed = Counter(
    "cdc_events_processed_total",
    "Total CDC events processed",
    ["job_id", "operation_type"]
)

cdc_consumer_lag = Gauge(
    "cdc_consumer_lag_ms",
    "CDC consumer lag in milliseconds",
    ["job_id"]
)

migration_progress = Gauge(
    "migration_progress_percentage",
    "Migration progress percentage",
    ["job_id"]
)
```

**Acceptance Criteria:**
- [ ] /metrics endpoint expõe Prometheus metrics
- [ ] CDC lag tracked per job
- [ ] Migration progress tracked
- [ ] Métricas documentadas

---

### [TEST-H-008]: Add E2E Tests

**Tipo:** Teste
**Priority:** MEDIUM
**Effort:** M (1 semana)
**Dependencies:** [BUG-H-001]

**Descrição:** Adicionar testes E2E para workflow completo de migration.

**Arquivos:**
- NOVO: `services/data-migration/tests/e2e/test_full_migration.py`
- NOVO: `services/data-migration/tests/e2e/test_cdc_reconnection.py`

**Acceptance Criteria:**
- [ ] Full migration E2E test passa
- [ ] CDC reconnection E2E test passa
- [ ] Tests executam com docker-compose
- [ ] Execução <10 minutos

---

## Priorização Sprint - Fluxo H

**Sprint 1 (2 semanas):**
1. [FEAT-H-004]: Entity Persistence
2. [FEAT-H-005]: Pause/Resume Endpoints

**Sprint 2 (2 semanas):**
3. [BUG-H-001]: CDC Reconnection (CRÍTICO)
4. [FEAT-H-006]: Document Download

**Sprint 3 (3 semanas):**
5. [BUG-H-002]: OOM Fix (CRÍTICO)
6. [BUG-H-003]: Concurrency Control (CRÍTICO)

**Sprint 4 (2 semanas):**
7. [REFACTOR-H-007]: Prometheus Metrics
8. [TEST-H-008]: E2E Tests

---

# PARTE 4: HANDOFF PARA CLAUDE CODE

## Como Usar Este Documento

### Para Cada Fluxo:

1. **Leia a seção "Current State Validation"** para entender o que já existe
2. **Revise os "Gaps Identificados"** para entender os problemas
3. **Siga os "Tickets" na ordem de priorização**

### Formato dos Tickets

Cada ticket contém:
- **Tipo**: Bug/Feature/Refactor/Teste
- **Priority**: CRITICAL/HIGH/MEDIUM/LOW
- **Effort**: XS(1d), S(2-3d), M(1w), L(2w), XL(3+w)
- **Dependencies**: Tickets que devem ser completados antes
- **Arquivos**: Arquivos específicos a criar/modificar
- **Acceptance Criteria**: Checklist de conclusão

### Estratégia de Implementação Sugerida

**Opção A: Paralelo (2 engenheiros)**
- Engenheiro 1: Fluxo A + Fluxo G
- Engenheiro 2: Fluxo H

**Opção B: Sequencial (1 engenheiro)**
- Sprint 1-2: Fluxo H (bugs críticos primeiro)
- Sprint 3-4: Fluxo G (test-generation Kafka)
- Sprint 5-6: Fluxo A (refatoração NLU)

### Comandos Úteis

```bash
# Verificar status atual dos serviços
docker-compose ps

# Rodar testes de um serviço específico
pytest services/test-generation/tests/

# Verificar logs de um serviço
docker-compose logs -f test-generation

# Verificar coverage
pytest --cov=services/test-generation/src
```

---

# PARTE 5: RESUMO DE TICKETS

## Todos os Tickets (Priorizados)

| ID | Fluxo | Título | Priority | Effort | Dependencies |
|----|-------|--------|----------|--------|--------------|
| BUG-A-003 | A | Correlation ID Propagation | CRITICAL | S | - |
| REFACTOR-A-001 | A | Extract NLU Pipeline | HIGH | XL | - |
| FEAT-A-002 | A | Complete Fluxo C Integration | HIGH | M | - |
| FEAT-A-004 | A | DLQ Rate Limiter | MEDIUM | S | - |
| FEAT-A-005 | A | Externalize NLU Thresholds | LOW | XS | REFACTOR-A-001 |
| FEAT-G-001 | G | Test-Generation Kafka | CRITICAL | L | - |
| FEAT-G-002 | G | Test-Generation MongoDB | HIGH | M | FEAT-G-001 |
| FEAT-G-004 | G | Test-Generation Tests | HIGH | M | FEAT-G-001 |
| REFACTOR-G-003 | G | Kafka-First Activities | MEDIUM | XL | FEAT-G-001 |
| BUG-H-001 | H | CDC Reconnection | CRITICAL | L | - |
| BUG-H-002 | H | OOM Fix | CRITICAL | L | - |
| BUG-H-003 | H | S3 Concurrency | CRITICAL | M | - |
| FEAT-H-004 | H | Entity Persistence | CRITICAL | M | - |
| FEAT-H-005 | H | Pause/Resume | HIGH | S | - |
| FEAT-H-006 | H | Document Download | HIGH | S | - |
| REFACTOR-H-007 | H | Prometheus Metrics | MEDIUM | M | - |
| TEST-H-008 | H | E2E Tests | MEDIUM | M | BUG-H-001 |

## Resumo de Esforço

| Fluxo | Críticos | Alta | Média | Baixa | Total Estimado |
|-------|----------|------|-------|-------|----------------|
| A | 1 | 1 | 1 | 1 | 5 semanas |
| G | 1 | 2 | 1 | - | 5-8 semanas |
| H | 4 | 2 | 2 | - | 8 semanas |
| **TOTAL** | **6** | **5** | **4** | **1** | **18-21 semanas** |

---

# APÊNDICE: ARQUIVOS CRÍTICOS

## Fluxo A

1. `services/gateway-intencoes/src/pipelines/nlu_pipeline.py` (500+ linhas)
2. `services/orchestrator-dynamic/src/integration/flow_c_consumer.py`
3. `services/semantic-translation-engine/src/services/dlq_reprocessor.py`

## Fluxo G

1. `services/test-generation/src/main.py` (91 linhas - NEEDS KAFKA)
2. `services/orchestrator-dynamic/src/activities/fluxo_g_integration.py` (260 linhas)
3. `services/test-generation/src/services/test_generator.py`

## Fluxo H

1. `services/data-migration/src/services/cdc_pipeline.py` (898 linhas)
2. `services/data-migration/src/services/rollback_manager.py` (741 linhas)
3. `services/data-migration/src/services/migration_orchestrator.py` (1054 linhas)
4. `services/doc-ingestion/src/api/routers/parsing.py` (line 357)

---

**Fim do Handoff Document**

Para começar a implementação, execute `/execute-tasks` e referencie este documento.
