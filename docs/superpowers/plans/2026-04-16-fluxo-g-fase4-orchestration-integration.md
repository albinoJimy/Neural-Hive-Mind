# Fluxo G Fase 4: Orchestration Integration - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrar todos os serviços do Fluxo G no orchestrator-dynamic, criando pipeline end-to-end com Kafka e rotas de fallback.

**Architecture:** O orchestrator-dynamic (8003) estende seus workflows Temporal para orquestrar os serviços: requirements-engineering (8010), architect-agent (8008), knowledge-graph-rag (8016), documentation-generation (8014), approval-gateway (8017), code-forge (8005). Cada etapa publica eventos Kafka para rastreamento e suporta fallback para alternativas.

**Tech Stack:** Python 3.12+, Temporal SDK, aiokafka, FastAPI, Redis, MongoDB

---

## Pré-requisitos

- Fase 1, 2 e 3 completas (architect-agent estendido, requirements-engineering, documentation-generation, knowledge-graph-rag, approval-gateway)
- Serviço orchestrator-dynamic operacional (porta 8003)
- Kafka cluster com tópicos base criados
- Redis para cache de estados

---

## Task 1: Criar Tópicos Kafka do Fluxo G

**Files:**
- Create: `infrastructure/kafka/topics/fluxo-g-topics.yaml`
- Test: `tests/integration/kafka/test_fluxo_g_topics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/kafka/test_fluxo_g_topics.py
import pytest
from aiokafka import AIOKafkaAdminClient
from aiokafka.admin import NewTopic

@pytest.mark.asyncio
async def test_all_fluxo_g_topics_exist(kafka_bootstrap_servers):
    """Testa que todos os tópicos do Fluxo G foram criados."""
    admin_client = AIOKafkaAdminClient(bootstrap_servers=kafka_bootstrap_servers)

    expected_topics = {
        "fluxo-g.intent.received",
        "fluxo-g.requirements.generated",
        "fluxo-g.architecture.generated",
        "fluxo-g.rag.queries",
        "fluxo-g.rag.results",
        "fluxo-g.documentation.generated",
        "fluxo-g.approval.requested",
        "fluxo-g.approval.completed",
        "fluxo-g.code.generated",
        "fluxo-g.pipeline.completed",
        "fluxo-g.pipeline.failed",
    }

    existing_topics = await admin_client.list_topics()
    await admin_client.close()

    for topic in expected_topics:
        assert topic in existing_topics, f"Tópico {topic} não existe"


@pytest.mark.asyncio
async def test_topics_have_correct_config(kafka_bootstrap_servers):
    """Testa configuração dos tópicos (partições, replicação)."""
    admin_client = AIOKafkaAdminClient(bootstrap_servers=kafka_bootstrap_servers)

    topic_configs = {
        "fluxo-g.intent.received": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.requirements.generated": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.architecture.generated": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.rag.queries": {"num_partitions": 6, "replication_factor": 2},
        "fluxo-g.rag.results": {"num_partitions": 6, "replication_factor": 2},
        "fluxo-g.documentation.generated": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.approval.requested": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.approval.completed": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.code.generated": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.pipeline.completed": {"num_partitions": 3, "replication_factor": 2},
        "fluxo-g.pipeline.failed": {"num_partitions": 3, "replication_factor": 2},
    }

    existing_topics = await admin_client.list_topics()
    await admin_client.close()

    for topic_name, config in topic_configs.items():
        assert topic_name in existing_topics, f"Tópico {topic_name} não existe"


@pytest.mark.asyncio
async def test_dead_letter_topics_exist(kafka_bootstrap_servers):
    """Testa que DLTs foram criados para retry."""
    admin_client = AIOKafkaAdminClient(bootstrap_servers=kafka_bootstrap_servers)

    dlt_topics = {
        "fluxo-g.requirements.dlt",
        "fluxo-g.architecture.dlt",
        "fluxo-g.documentation.dlt",
        "fluxo-g.approval.dlt",
    }

    existing_topics = await admin_client.list_topics()
    await admin_client.close()

    for topic in dlt_topics:
        assert topic in existing_topics, f"DLT {topic} não existe"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/kafka/test_fluxo_g_topics.py -v`
Expected: FAIL - tópicos não existem ainda

- [ ] **Step 3: Create Kafka topics configuration**

```yaml
# infrastructure/kafka/topics/fluxo-g-topics.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-intent-received
  namespace: neural-hive-mind
  labels:
    strimzi.io/cluster: neural-hive-mind-kafka
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 86400000  # 24 horas
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-requirements-generated
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-architecture-generated
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-rag-queries
  namespace: neural-hive-mind
spec:
  partitions: 6  # Mais partições para alta taxa de queries
  replicas: 2
  config:
    retention.ms: 3600000  # 1 hora
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-rag-results
  namespace: neural-hive-mind
spec:
  partitions: 6
  replicas: 2
  config:
    retention.ms: 3600000  # 1 hora
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-documentation-generated
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-approval-requested
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 2592000000  # 30 dias (aprovações precisam de histórico)
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-approval-completed
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 2592000000  # 30 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-code-generated
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-pipeline-completed
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 2592000000  # 30 dias
    cleanup.policy: compact
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-pipeline-failed
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 2592000000  # 30 dias
    cleanup.policy: delete
---
# Dead Letter Topics para retry
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-requirements-dlt
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-architecture-dlt
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-documentation-dlt
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: fluxo-g-approval-dlt
  namespace: neural-hive-mind
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    cleanup.policy: delete
```

- [ ] **Step 4: Create script to apply topics**

```python
# infrastructure/kafka/scripts/create_fluxo_g_topics.py
import asyncio
from aiokafka import AIOKafkaAdminClient
from aiokafka.admin import NewTopic
import os

TOPICS = [
    # Main topics
    NewTopic(name="fluxo-g.intent.received", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.requirements.generated", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.architecture.generated", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.rag.queries", num_partitions=6, replication_factor=2),
    NewTopic(name="fluxo-g.rag.results", num_partitions=6, replication_factor=2),
    NewTopic(name="fluxo-g.documentation.generated", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.approval.requested", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.approval.completed", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.code.generated", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.pipeline.completed", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.pipeline.failed", num_partitions=3, replication_factor=2),
    # Dead Letter Topics
    NewTopic(name="fluxo-g.requirements.dlt", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.architecture.dlt", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.documentation.dlt", num_partitions=3, replication_factor=2),
    NewTopic(name="fluxo-g.approval.dlt", num_partitions=3, replication_factor=2),
]

async def create_topics():
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    admin_client = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)

    try:
        await admin_client.start()
        existing_topics = await admin_client.list_topics()

        # Filtra tópicos que já existem
        topics_to_create = [t for t in TOPICS if t.name not in existing_topics]

        if topics_to_create:
            result = await admin_client.create_topics(topics_to_create)
            for topic, future in result.items():
                try:
                    await future
                    print(f"✓ Tópico {topic} criado com sucesso")
                except Exception as e:
                    print(f"✗ Erro ao criar tópico {topic}: {e}")
        else:
            print("Todos os tópicos já existem")

    finally:
        await admin_client.close()

if __name__ == "__main__":
    asyncio.run(create_topics())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/integration/kafka/test_fluxo_g_topics.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add infrastructure/kafka/ tests/integration/kafka/
git commit -m "feat(orchestration): add Kafka topics for Fluxo G pipeline"
```

---

## Task 2: Criar Modelo de Pipeline no Orchestrator

**Files:**
- Create: `services/orchestrator-dynamic/src/models/fluxo_g_pipeline.py`
- Test: `services/orchestrator-dynamic/tests/models/test_fluxo_g_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/models/test_fluxo_g_pipeline.py
import pytest
from datetime import datetime, timedelta
from orchestrator.models.fluxo_g_pipeline import (
    FluxoGPipeline,
    PipelineStage,
    PipelineStatus,
    PipelineContext,
    StageResult,
)


@pytest.mark.asyncio
async def test_create_fluxo_g_pipeline():
    """Testa criação de pipeline do Fluxo G."""
    pipeline = FluxoGPipeline(
        intent_text="Criar um sistema de login",
        user_id="user123",
        project_name="sistema-login",
    )

    assert pipeline.id is not None
    assert pipeline.status == PipelineStatus.PENDING
    assert len(pipeline.stages) == 7
    assert pipeline.current_stage == PipelineStage.REQUIREMENTS


@pytest.mark.asyncio
async def test_pipeline_stage_progression():
    """Testa progressão entre estágios do pipeline."""
    pipeline = FluxoGPipeline(
        intent_text="Criar API de produtos",
        user_id="user456",
        project_name="api-produtos",
    )

    # Inicia pipeline
    await pipeline.start()

    assert pipeline.status == PipelineStatus.RUNNING
    assert pipeline.current_stage == PipelineStage.REQUIREMENTS

    # Completa requirements
    await pipeline.complete_stage(
        PipelineStage.REQUIREMENTS,
        result=StageResult(success=True, output={"requirements": ["req1", "req2"]})
    )

    assert pipeline.current_stage == PipelineStage.ARCHITECTURE
    assert pipeline.stages[PipelineStage.REQUIREMENTS]["status"] == "completed"


@pytest.mark.asyncio
async def test_pipeline_context_serialization():
    """Testa serialização do contexto do pipeline."""
    context = PipelineContext(
        user_id="user789",
        project_name="projeto-teste",
        intent_text="Intent de teste",
        metadata={"key": "value"},
    )

    serialized = context.model_dump_json()
    deserialized = PipelineContext.model_validate_json(serialized)

    assert deserialized.user_id == context.user_id
    assert deserialized.project_name == context.project_name
    assert deserialized.metadata == context.metadata


@pytest.mark.asyncio
async def test_pipeline_error_handling():
    """Testa tratamento de erros no pipeline."""
    pipeline = FluxoGPipeline(
        intent_text="Teste erro",
        user_id="user999",
        project_name="teste-erro",
    )

    await pipeline.start()

    # Simula erro no estágio de requirements
    with pytest.raises(PipelineStageError):
        await pipeline.fail_stage(
            PipelineStage.REQUIREMENTS,
            error="Erro ao gerar requisitos",
        )

    assert pipeline.status == PipelineStatus.FAILED
    assert pipeline.stages[PipelineStage.REQUIREMENTS]["status"] == "failed"


@pytest.mark.asyncio
async def test_pipeline_retry_logic():
    """Testa lógica de retry em estágios falhos."""
    pipeline = FluxoGPipeline(
        intent_text="Teste retry",
        user_id="user888",
        project_name="teste-retry",
    )

    await pipeline.start()

    # Falha no estágio
    await pipeline.fail_stage(
        PipelineStage.REQUIREMENTS,
        error="Erro temporário",
    )

    # Retry
    await pipeline.retry_stage(PipelineStage.REQUIREMENTS)

    assert pipeline.status == PipelineStatus.RUNNING
    assert pipeline.stages[PipelineStage.REQUIREMENTS]["status"] == "pending"
    assert pipeline.stages[PipelineStage.REQUIREMENTS]["retry_count"] == 1


@pytest.mark.asyncio
async def test_pipeline_timeout():
    """Testa timeout de estágio do pipeline."""
    pipeline = FluxoGPipeline(
        intent_text="Teste timeout",
        user_id="user777",
        project_name="teste-timeout",
        stage_timeout_seconds=1,
    )

    await pipeline.start()

    # Simula estágio que excede timeout
    import asyncio
    await asyncio.sleep(2)

    is_timeout = await pipeline.check_stage_timeout(PipelineStage.REQUIREMENTS)
    assert is_timeout is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/models/test_fluxo_g_pipeline.py -v`
Expected: FAIL - modelos não existem

- [ ] **Step 3: Implement models**

```python
# services/orchestrator-dynamic/src/models/fluxo_g_pipeline.py
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class PipelineStage(str, Enum):
    """Estágios do pipeline Fluxo G."""
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    RAG_QUERY = "rag_query"
    DOCUMENTATION = "documentation"
    APPROVAL = "approval"
    CODE_GENERATION = "code_generation"
    DEPLOYMENT = "deployment"


class PipelineStatus(str, Enum):
    """Status do pipeline."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


class StageResult(BaseModel):
    """Resultado de um estágio do pipeline."""
    success: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    artifacts: Optional[List[str]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PipelineStageError(Exception):
    """Erro em estágio do pipeline."""
    def __init__(self, stage: PipelineStage, error: str):
        self.stage = stage
        self.error = error
        super().__init__(f"Stage {stage.value} failed: {error}")


class PipelineContext(BaseModel):
    """Contexto compartilhado entre estágios do pipeline."""
    user_id: str
    project_name: str
    intent_text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    requirements: Optional[Dict[str, Any]] = None
    architecture: Optional[Dict[str, Any]] = None
    rag_results: Optional[Dict[str, Any]] = None
    documentation: Optional[Dict[str, Any]] = None
    approval_data: Optional[Dict[str, Any]] = None
    generated_code: Optional[Dict[str, Any]] = None


class FluxoGPipeline(BaseModel):
    """Pipeline completo do Fluxo G (Ideia → Software)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context: PipelineContext
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: Optional[PipelineStage] = None
    stages: Dict[PipelineStage, Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    stage_timeout_seconds: int = 300  # 5 minutos por estágio
    max_retries: int = 3

    class Config:
        use_enum_values = True

    def __init__(self, **data):
        super().__init__(**data)
        self._initialize_stages()

    def _initialize_stages(self):
        """Inicializa os estágios do pipeline."""
        stage_order = [
            PipelineStage.REQUIREMENTS,
            PipelineStage.ARCHITECTURE,
            PipelineStage.RAG_QUERY,
            PipelineStage.DOCUMENTATION,
            PipelineStage.APPROVAL,
            PipelineStage.CODE_GENERATION,
            PipelineStage.DEPLOYMENT,
        ]

        for stage in stage_order:
            if stage not in self.stages:
                self.stages[stage] = {
                    "status": "pending",
                    "retry_count": 0,
                    "result": None,
                    "started_at": None,
                    "completed_at": None,
                }

    async def start(self) -> None:
        """Inicia a execução do pipeline."""
        if self.status != PipelineStatus.PENDING:
            raise ValueError("Pipeline already started or completed")

        self.status = PipelineStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.current_stage = PipelineStage.REQUIREMENTS

    async def complete_stage(
        self,
        stage: PipelineStage,
        result: StageResult,
    ) -> None:
        """Marca um estágio como completo."""
        if self.stages[stage]["status"] == "completed":
            return

        self.stages[stage]["status"] = "completed"
        self.stages[stage]["result"] = result.model_dump()
        self.stages[stage]["completed_at"] = datetime.utcnow()

        # Avança para o próximo estágio
        stage_list = list(PipelineStage)
        current_index = stage_list.index(stage)
        if current_index + 1 < len(stage_list):
            next_stage = stage_list[current_index + 1]
            self.current_stage = next_stage

        # Atualiza o contexto
        self._update_context(stage, result)

    async def fail_stage(self, stage: PipelineStage, error: str) -> None:
        """Marca um estágio como falho."""
        self.stages[stage]["status"] = "failed"
        self.stages[stage]["error"] = error
        self.stages[stage]["completed_at"] = datetime.utcnow()

        # Verifica se deve retry ou falhar pipeline
        retry_count = self.stages[stage]["retry_count"]
        if retry_count < self.max_retries:
            self.stages[stage]["status"] = "retry_pending"
        else:
            self.status = PipelineStatus.FAILED
            self.completed_at = datetime.utcnow()

    async def retry_stage(self, stage: PipelineStage) -> None:
        """Reinicia um estágio falho."""
        self.stages[stage]["status"] = "pending"
        self.stages[stage]["retry_count"] += 1
        self.stages[stage]["error"] = None
        self.current_stage = stage
        self.status = PipelineStatus.RUNNING

    async def check_stage_timeout(self, stage: PipelineStage) -> bool:
        """Verifica se um estágio excedeu o timeout."""
        stage_data = self.stages[stage]
        if stage_data["status"] != "pending":
            return False

        started_at = stage_data.get("started_at")
        if not started_at:
            return False

        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        elapsed = (datetime.utcnow() - started_at).total_seconds()
        return elapsed > self.stage_timeout_seconds

    def _update_context(self, stage: PipelineStage, result: StageResult) -> None:
        """Atualiza o contexto com o resultado do estágio."""
        if not result.output:
            return

        if stage == PipelineStage.REQUIREMENTS:
            self.context.requirements = result.output
        elif stage == PipelineStage.ARCHITECTURE:
            self.context.architecture = result.output
        elif stage == PipelineStage.RAG_QUERY:
            self.context.rag_results = result.output
        elif stage == PipelineStage.DOCUMENTATION:
            self.context.documentation = result.output
        elif stage == PipelineStage.APPROVAL:
            self.context.approval_data = result.output
        elif stage == PipelineStage.CODE_GENERATION:
            self.context.generated_code = result.output

    async def mark_awaiting_approval(self) -> None:
        """Marca o pipeline como aguardando aprovação."""
        self.status = PipelineStatus.AWAITING_APPROVAL
        self.current_stage = PipelineStage.APPROVAL

    async def resume_after_approval(self, approved: bool) -> None:
        """Retoma o pipeline após aprovação."""
        if approved:
            self.status = PipelineStatus.RUNNING
            self.current_stage = PipelineStage.CODE_GENERATION
        else:
            self.status = PipelineStatus.CANCELLED
            self.completed_at = datetime.utcnow()

    async def complete(self) -> None:
        """Marca o pipeline como completo."""
        self.status = PipelineStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.current_stage = None

    def get_elapsed_time_seconds(self) -> float:
        """Retorna o tempo decorrido desde o início."""
        if not self.started_at:
            return 0.0

        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def get_progress_percentage(self) -> float:
        """Retorna o progresso do pipeline em percentagem."""
        total_stages = len(self.stages)
        completed_stages = sum(
            1 for s in self.stages.values() if s["status"] == "completed"
        )
        return (completed_stages / total_stages) * 100
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/models/test_fluxo_g_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/models/fluxo_g_pipeline.py \
        services/orchestrator-dynamic/tests/models/test_fluxo_g_pipeline.py
git commit -m "feat(orchestrator): add FluxoGPipeline model"
```

---

## Task 3: Criar Activities Temporal para Fluxo G

**Files:**
- Create: `services/orchestrator-dynamic/src/activities/fluxo_g_activities.py`
- Test: `services/orchestrator-dynamic/tests/activities/test_fluxo_g_activities.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/activities/test_fluxo_g_activities.py
import pytest
from unittest.mock import AsyncMock, patch
from orchestrator.activities.fluxo_g_activities import (
    GenerateRequirementsActivity,
    GenerateArchitectureActivity,
    QueryRAGActivity,
    GenerateDocumentationActivity,
    RequestApprovalActivity,
    GenerateCodeActivity,
)


@pytest.mark.asyncio
async def test_generate_requirements_activity():
    """Testa activity de geração de requisitos."""
    activity = GenerateRequirementsActivity()

    result = await activity.run(
        intent_text="Criar sistema de e-commerce",
        project_name="ecommerce-system",
        user_id="user123",
    )

    assert result["success"] is True
    assert "requirements" in result
    assert "user_stories" in result["requirements"]
    assert len(result["requirements"]["user_stories"]) > 0


@pytest.mark.asyncio
async def test_generate_architecture_activity():
    """Testa activity de geração de arquitetura."""
    activity = GenerateArchitectureActivity()

    requirements = {
        "user_stories": [
            {"role": "user", "action": "login", "benefit": "access account"}
        ]
    }

    result = await activity.run(
        requirements=requirements,
        project_name="login-system",
    )

    assert result["success"] is True
    assert "architecture" in result
    assert "components" in result["architecture"]


@pytest.mark.asyncio
async def test_query_rag_activity():
    """Testa activity de consulta RAG."""
    activity = QueryRAGActivity()

    result = await activity.run(
        query="arquitetura de microserviços",
        context={"domain": "software-architecture"},
        top_k=5,
        alpha=0.7,
    )

    assert result["success"] is True
    assert "results" in result
    assert isinstance(result["results"], list)


@pytest.mark.asyncio
async def test_query_rag_with_fallback():
    """Testa fallback quando RAG está indisponível."""
    activity = QueryRAGActivity()

    with patch.object(activity, "_query_rag_service", side_effect=Exception("RAG down")):
        result = await activity.run(
            query="microserviços",
            context={},
            top_k=3,
            alpha=0.5,
            enable_fallback=True,
        )

        # Deve usar fallback (templates internos)
        assert result["success"] is True
        assert result["fallback_used"] is True


@pytest.mark.asyncio
async def test_generate_documentation_activity():
    """Testa activity de geração de documentação."""
    activity = GenerateDocumentationActivity()

    architecture = {
        "components": [{"name": "API Gateway", "type": "service"}]
    }

    result = await activity.run(
        architecture=architecture,
        project_name="api-gateway",
        doc_types=["readme", "api_docs"],
    )

    assert result["success"] is True
    assert "documentation" in result
    assert "readme" in result["documentation"]


@pytest.mark.asyncio
async def test_request_approval_activity():
    """Testa activity de solicitação de aprovação."""
    activity = RequestApprovalActivity()

    result = await activity.run(
        artifact_id="artifact-123",
        artifact_type="architecture",
        content={"components": []},
        approvers=["architect@company.com"],
        user_id="user123",
    )

    assert result["success"] is True
    assert "approval_id" in result
    assert "token" in result


@pytest.mark.asyncio
async def test_generate_code_activity():
    """Testa activity de geração de código."""
    activity = GenerateCodeActivity()

    result = await activity.run(
        approved_architecture={
            "components": [{"name": "UserService", "type": "service"}]
        },
        approved_documentation={
            "readme": "# UserService\nAPI de usuários"
        },
        project_name="user-service",
        tech_stack={"language": "python", "framework": "fastapi"},
    )

    assert result["success"] is True
    assert "generated_code" in result
    assert "files" in result["generated_code"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/activities/test_fluxo_g_activities.py -v`
Expected: FAIL - activities não existem

- [ ] **Step 3: Implement activities**

```python
# services/orchestrator-dynamic/src/activities/fluxo_g_activities.py
import httpx
from typing import Dict, Any, List, Optional
from datetime import timedelta
import logging
import os

logger = logging.getLogger(__name__)


class FluxoGActivityBase:
    """Base class para activities do Fluxo G."""

    def __init__(self):
        self.timeout = timedelta(seconds=30)

    def _get_service_url(self, service_name: str) -> str:
        """Retorna a URL do serviço."""
        service_urls = {
            "requirements-engineering": os.getenv(
                "REQUIREMENTS_SERVICE_URL", "http://requirements-engineering:8010"
            ),
            "architect-agent": os.getenv(
                "ARCHITECT_SERVICE_URL", "http://architect-agent:8008"
            ),
            "knowledge-graph-rag": os.getenv(
                "RAG_SERVICE_URL", "http://knowledge-graph-rag:8016"
            ),
            "documentation-generation": os.getenv(
                "DOCS_SERVICE_URL", "http://documentation-generation:8014"
            ),
            "approval-gateway": os.getenv(
                "APPROVAL_SERVICE_URL", "http://approval-gateway:8017"
            ),
            "code-forge": os.getenv(
                "CODE_FORGE_URL", "http://code-forge:8005"
            ),
        }
        return service_urls.get(service_name, "")


class GenerateRequirementsActivity(FluxoGActivityBase):
    """Activity para geração de requisitos."""

    async def run(
        self,
        intent_text: str,
        project_name: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Executa a geração de requisitos."""
        try:
            service_url = self._get_service_url("requirements-engineering")
            endpoint = f"{service_url}/api/v1/requirements/generate"

            payload = {
                "intent": intent_text,
                "project_name": project_name,
                "user_id": user_id,
                "options": {
                    "include_user_stories": True,
                    "include_acceptance_criteria": True,
                    "include_data_models": True,
                },
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "requirements": data,
                "requirements_id": data.get("id"),
            }

        except Exception as e:
            logger.error(f"Error generating requirements: {e}")
            return {
                "success": False,
                "error": str(e),
            }


class GenerateArchitectureActivity(FluxoGActivityBase):
    """Activity para geração de arquitetura."""

    async def run(
        self,
        requirements: Dict[str, Any],
        project_name: str,
        tech_stack: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Executa a geração de arquitetura."""
        try:
            service_url = self._get_service_url("architect-agent")
            endpoint = f"{service_url}/api/v1/architecture/plan"

            payload = {
                "project_name": project_name,
                "requirements": requirements,
                "tech_stack": tech_stack or {
                    "language": "python",
                    "framework": "fastapi",
                },
            }

            async with httpx.AsyncClient(timeout=timedelta(seconds=60)) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "architecture": data,
                "architecture_id": data.get("id"),
            }

        except Exception as e:
            logger.error(f"Error generating architecture: {e}")
            return {
                "success": False,
                "error": str(e),
            }


class QueryRAGActivity(FluxoGActivityBase):
    """Activity para consulta ao Knowledge Graph RAG."""

    def __init__(self):
        super().__init__()
        self.fallback_templates = self._load_fallback_templates()

    def _load_fallback_templates(self) -> Dict[str, List[Dict]]:
        """Carrega templates de fallback."""
        return {
            "architecture": [
                {
                    "id": "tpl-microservices-001",
                    "name": "Microservices Pattern",
                    "description": "Arquitetura de microserviços padrão",
                    "components": ["API Gateway", "Service Discovery", "Config Server"],
                },
                {
                    "id": "tpl-monolith-001",
                    "name": "Modular Monolith",
                    "description": "Monólito modular para começar",
                    "components": ["Web Layer", "Business Layer", "Data Layer"],
                },
            ],
        }

    async def run(
        self,
        query: str,
        context: Dict[str, Any],
        top_k: int = 5,
        alpha: float = 0.7,
        enable_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Executa consulta RAG com fallback."""
        try:
            service_url = self._get_service_url("knowledge-graph-rag")
            endpoint = f"{service_url}/api/v1/query"

            payload = {
                "query": query,
                "context": context,
                "top_k": top_k,
                "alpha": alpha,
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "results": data.get("results", []),
                "fallback_used": False,
            }

        except Exception as e:
            logger.warning(f"RAG service unavailable: {e}")

            if enable_fallback:
                return self._execute_fallback(query, context)
            else:
                return {
                    "success": False,
                    "error": str(e),
                    "fallback_used": False,
                }

    def _execute_fallback(
        self,
        query: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Executa fallback usando templates internos."""
        domain = context.get("domain", "architecture")
        templates = self.fallback_templates.get(domain, [])

        # Busca simples por keywords
        query_lower = query.lower()
        results = [
            t for t in templates
            if any(kw in query_lower for kw in t["name"].lower().split())
        ]

        logger.info(f"Using fallback: {len(results)} templates found")

        return {
            "success": True,
            "results": results[:3],
            "fallback_used": True,
        }


class GenerateDocumentationActivity(FluxoGActivityBase):
    """Activity para geração de documentação."""

    async def run(
        self,
        architecture: Dict[str, Any],
        project_name: str,
        doc_types: List[str] = None,
    ) -> Dict[str, Any]:
        """Executa a geração de documentação."""
        doc_types = doc_types or ["readme", "api_docs"]

        try:
            service_url = self._get_service_url("documentation-generation")
            endpoint = f"{service_url}/api/v1/documentation/generate"

            payload = {
                "project_name": project_name,
                "architecture": architecture,
                "doc_types": doc_types,
            }

            async with httpx.AsyncClient(timeout=timedelta(seconds=45)) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "documentation": data,
                "documentation_id": data.get("id"),
            }

        except Exception as e:
            logger.error(f"Error generating documentation: {e}")
            return {
                "success": False,
                "error": str(e),
            }


class RequestApprovalActivity(FluxoGActivityBase):
    """Activity para solicitação de aprovação."""

    async def run(
        self,
        artifact_id: str,
        artifact_type: str,
        content: Dict[str, Any],
        approvers: List[str],
        user_id: str,
    ) -> Dict[str, Any]:
        """Solicita aprovação de artefato."""
        try:
            service_url = self._get_service_url("approval-gateway")
            endpoint = f"{service_url}/api/v1/approvals/request"

            payload = {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "content": content,
                "approvers": approvers,
                "requested_by": user_id,
                "approval_type": "fluxo_g_stage",
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "approval_id": data.get("approval_id"),
                "token": data.get("approval_token"),
                "status": data.get("status"),
            }

        except Exception as e:
            logger.error(f"Error requesting approval: {e}")
            return {
                "success": False,
                "error": str(e),
            }


class GenerateCodeActivity(FluxoGActivityBase):
    """Activity para geração de código."""

    async def run(
        self,
        approved_architecture: Dict[str, Any],
        approved_documentation: Dict[str, Any],
        project_name: str,
        tech_stack: Dict[str, str],
    ) -> Dict[str, Any]:
        """Gera código baseado em artefatos aprovados."""
        try:
            service_url = self._get_service_url("code-forge")
            endpoint = f"{service_url}/api/v1/code/generate"

            payload = {
                "project_name": project_name,
                "architecture": approved_architecture,
                "documentation": approved_documentation,
                "tech_stack": tech_stack,
                "options": {
                    "include_tests": True,
                    "include_docker": True,
                    "include_kubernetes": True,
                },
            }

            async with httpx.AsyncClient(timeout=timedelta(seconds=120)) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "generated_code": data,
                "code_id": data.get("id"),
            }

        except Exception as e:
            logger.error(f"Error generating code: {e}")
            return {
                "success": False,
                "error": str(e),
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/activities/test_fluxo_g_activities.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/activities/fluxo_g_activities.py \
        services/orchestrator-dynamic/tests/activities/test_fluxo_g_activities.py
git commit -m "feat(orchestrator): add FluxoG Temporal activities"
```

---

## Task 4: Criar Workflow Temporal do Fluxo G

**Files:**
- Create: `services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py`
- Test: `services/orchestrator-dynamic/tests/workflows/test_fluxo_g_workflow.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/workflows/test_fluxo_g_workflow.py
import pytest
from datetime import timedelta
from temporalio import workflow
from orchestrator.workflows.fluxo_g_workflow import FluxoGWorkflow


@pytest.mark.asyncio
async def test_fluxo_g_workflow_definition():
    """Testa definição do workflow."""
    assert hasattr(FluxoGWorkflow, "run")
    assert callable(FluxoGWorkflow.run)


@pytest.mark.asyncio
async def test_workflow_query_methods():
    """Testa métodos de query do workflow."""
    assert hasattr(FluxoGWorkflow, "current_stage")
    assert hasattr(FluxoGWorkflow, "progress")
    assert hasattr(FluxoGWorkflow, "status")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/workflows/test_fluxo_g_workflow.py -v`
Expected: FAIL - workflow não existe

- [ ] **Step 3: Implement workflow**

```python
# services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.defn:
    from orchestrator.activities.fluxo_g_activities import (
        GenerateRequirementsActivity,
        GenerateArchitectureActivity,
        QueryRAGActivity,
        GenerateDocumentationActivity,
        RequestApprovalActivity,
        GenerateCodeActivity,
    )


@workflow.defn
class FluxoGWorkflow:
    """Workflow principal do Fluxo G: Ideia → Software."""

    def __init__(self) -> None:
        self._current_stage = "pending"
        self._progress = 0.0
        self._status = "pending"

    @workflow.run
    async def run(
        self,
        intent_text: str,
        project_name: str,
        user_id: str,
        tech_stack: Optional[dict] = None,
        require_approval: bool = True,
    ) -> dict:
        """Executa o pipeline completo do Fluxo G."""

        self._status = "running"
        tech_stack = tech_stack or {}

        # STAGE 1: Requirements
        self._current_stage = "requirements"
        self._progress = 14.0  # 1/7

        requirements_result = await workflow.execute_activity(
            GenerateRequirementsActivity.run,
            args={
                "intent_text": intent_text,
                "project_name": project_name,
                "user_id": user_id,
            },
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
            ),
        )

        if not requirements_result["success"]:
            raise ApplicationError(
                f"Requirements generation failed: {requirements_result.get('error')}"
            )

        requirements = requirements_result["requirements"]

        # STAGE 2: Architecture
        self._current_stage = "architecture"
        self._progress = 28.0  # 2/7

        architecture_result = await workflow.execute_activity(
            GenerateArchitectureActivity.run,
            args={
                "requirements": requirements,
                "project_name": project_name,
                "tech_stack": tech_stack,
            },
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        if not architecture_result["success"]:
            raise ApplicationError(
                f"Architecture generation failed: {architecture_result.get('error')}"
            )

        architecture = architecture_result["architecture"]

        # STAGE 3: RAG Query (opcional, usa fallback se falhar)
        self._current_stage = "rag_query"
        self._progress = 42.0  # 3/7

        rag_result = await workflow.execute_activity(
            QueryRAGActivity.run,
            args={
                "query": f"{project_name} architecture best practices",
                "context": {"domain": "architecture"},
                "top_k": 5,
                "alpha": 0.7,
                "enable_fallback": True,
            },
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=1),  # Usa fallback rápido
        )

        rag_context = rag_result.get("results", [])

        # STAGE 4: Documentation
        self._current_stage = "documentation"
        self._progress = 57.0  # 4/7

        documentation_result = await workflow.execute_activity(
            GenerateDocumentationActivity.run,
            args={
                "architecture": architecture,
                "project_name": project_name,
                "doc_types": ["readme", "api_docs", "diagrams"],
            },
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        if not documentation_result["success"]:
            raise ApplicationError(
                f"Documentation generation failed: {documentation_result.get('error')}"
            )

        documentation = documentation_result["documentation"]

        # STAGE 5: Approval (opcional)
        if require_approval:
            self._current_stage = "approval"
            self._progress = 71.0  # 5/7
            self._status = "awaiting_approval"

            approval_result = await workflow.execute_activity(
                RequestApprovalActivity.run,
                args={
                    "artifact_id": architecture_result.get("architecture_id"),
                    "artifact_type": "architecture",
                    "content": {
                        "architecture": architecture,
                        "documentation": documentation,
                    },
                    "approvers": workflow.memo_value("approvers", []),
                    "user_id": user_id,
                },
                start_to_close_timeout=timedelta(seconds=30),
            )

            if not approval_result["success"]:
                raise ApplicationError(
                    f"Approval request failed: {approval_result.get('error')}"
                )

            # Aguarda sinal de aprovação
            await workflow.wait_condition(
                lambda: workflow.memo_value("approval_completed", False)
            )

            if not workflow.memo_value("approval_approved", False):
                self._status = "rejected"
                return {
                    "success": False,
                    "reason": "Approval rejected",
                    "pipeline_id": workflow.info().workflow_id,
                }

        self._status = "running"

        # STAGE 6: Code Generation
        self._current_stage = "code_generation"
        self._progress = 85.0  # 6/7

        code_result = await workflow.execute_activity(
            GenerateCodeActivity.run,
            args={
                "approved_architecture": architecture,
                "approved_documentation": documentation,
                "project_name": project_name,
                "tech_stack": tech_stack,
            },
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        if not code_result["success"]:
            raise ApplicationError(
                f"Code generation failed: {code_result.get('error')}"
            )

        # STAGE 7: Complete
        self._current_stage = "completed"
        self._progress = 100.0
        self._status = "completed"

        return {
            "success": True,
            "pipeline_id": workflow.info().workflow_id,
            "requirements": requirements,
            "architecture": architecture,
            "documentation": documentation,
            "generated_code": code_result["generated_code"],
        }

    @workflow.query
    def current_stage(self) -> str:
        """Retorna o estágio atual do workflow."""
        return self._current_stage

    @workflow.query
    def progress(self) -> float:
        """Retorna o progresso do workflow (0-100)."""
        return self._progress

    @workflow.query
    def status(self) -> str:
        """Retorna o status do workflow."""
        return self._status

    @workflow.signal
    async def approve(self, approved: bool, feedback: str = "") -> None:
        """Sinaliza aprovação/rejeição."""
        workflow.memo_update("approval_completed", True)
        workflow.memo_update("approval_approved", approved)
        workflow.memo_update("approval_feedback", feedback)


class ApplicationError(Exception):
    """Erro na aplicação."""
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/workflows/test_fluxo_g_workflow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py \
        services/orchestrator-dynamic/tests/workflows/test_fluxo_g_workflow.py
git commit -m "feat(orchestrator): add FluxoG Temporal workflow"
```

---

## Task 5: Criar Kafka Producer para Eventos do Pipeline

**Files:**
- Create: `services/orchestrator-dynamic/src/producers/fluxo_g_producer.py`
- Test: `services/orchestrator-dynamic/tests/producers/test_fluxo_g_producer.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/producers/test_fluxo_g_producer.py
import pytest
from unittest.mock import AsyncMock, patch
from orchestrator.producers.fluxo_g_producer import (
    FluxoGEventProducer,
    PipelineEventType,
)


@pytest.mark.asyncio
async def test_producer_publishes_intent_received():
    """Testa publicação de evento intent.received."""
    producer = FluxoGEventProducer()

    await producer.publish_intent_received(
        pipeline_id="pipeline-123",
        intent_text="Criar API de produtos",
        user_id="user456",
        project_name="api-produtos",
    )

    assert producer.last_published_topic == "fluxo-g.intent.received"


@pytest.mark.asyncio
async def test_producer_publishes_requirements_generated():
    """Testa publicação de evento requirements.generated."""
    producer = FluxoGEventProducer()

    await producer.publish_requirements_generated(
        pipeline_id="pipeline-123",
        requirements={"user_stories": []},
        requirements_id="req-456",
    )

    assert producer.last_published_topic == "fluxo-g.requirements.generated"


@pytest.mark.asyncio
async def test_producer_publishes_architecture_generated():
    """Testa publicação de evento architecture.generated."""
    producer = FluxoGEventProducer()

    await producer.publish_architecture_generated(
        pipeline_id="pipeline-123",
        architecture={"components": []},
        architecture_id="arch-789",
    )

    assert producer.last_published_topic == "fluxo-g.architecture.generated"


@pytest.mark.asyncio
async def test_producer_publishes_pipeline_completed():
    """Testa publicação de evento pipeline.completed."""
    producer = FluxoGEventProducer()

    await producer.publish_pipeline_completed(
        pipeline_id="pipeline-123",
        duration_seconds=300,
        output={"generated_code": {}},
    )

    assert producer.last_published_topic == "fluxo-g.pipeline.completed"


@pytest.mark.asyncio
async def test_producer_publishes_pipeline_failed():
    """Testa publicação de evento pipeline.failed."""
    producer = FluxoGEventProducer()

    await producer.publish_pipeline_failed(
        pipeline_id="pipeline-123",
        failed_stage="requirements",
        error="Service unavailable",
        duration_seconds=30,
    )

    assert producer.last_published_topic == "fluxo-g.pipeline.failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/producers/test_fluxo_g_producer.py -v`
Expected: FAIL - producer não existe

- [ ] **Step 3: Implement producer**

```python
# services/orchestrator-dynamic/src/producers/fluxo_g_producer.py
import json
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import logging
import os

logger = logging.getLogger(__name__)


class PipelineEventType(str, Enum):
    """Tipos de eventos do pipeline."""
    INTENT_RECEIVED = "intent.received"
    REQUIREMENTS_GENERATED = "requirements.generated"
    ARCHITECTURE_GENERATED = "architecture.generated"
    RAG_QUERIED = "rag.queried"
    DOCUMENTATION_GENERATED = "documentation.generated"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_COMPLETED = "approval.completed"
    CODE_GENERATED = "code.generated"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    STAGE_FAILED = "stage.failed"


class FluxoGEventProducer:
    """Producer de eventos Kafka do Fluxo G."""

    TOPIC_MAP = {
        PipelineEventType.INTENT_RECEIVED: "fluxo-g.intent.received",
        PipelineEventType.REQUIREMENTS_GENERATED: "fluxo-g.requirements.generated",
        PipelineEventType.ARCHITECTURE_GENERATED: "fluxo-g.architecture.generated",
        PipelineEventType.RAG_QUERIED: "fluxo-g.rag.results",
        PipelineEventType.DOCUMENTATION_GENERATED: "fluxo-g.documentation.generated",
        PipelineEventType.APPROVAL_REQUESTED: "fluxo-g.approval.requested",
        PipelineEventType.APPROVAL_COMPLETED: "fluxo-g.approval.completed",
        PipelineEventType.CODE_GENERATED: "fluxo-g.code.generated",
        PipelineEventType.PIPELINE_COMPLETED: "fluxo-g.pipeline.completed",
        PipelineEventType.PIPELINE_FAILED: "fluxo-g.pipeline.failed",
        PipelineEventType.STAGE_FAILED: "fluxo-g.pipeline.failed",
    }

    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None
        self._bootstrap_servers = os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self._last_published_topic = None

    @property
    def last_published_topic(self) -> Optional[str]:
        """Para testes: retorna último tópico publicado."""
        return self._last_published_topic

    async def start(self):
        """Inicia o producer Kafka."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                compression_type="snappy",
                linger_ms=10,
                batch_size=32768,
            )
            await self._producer.start()
            logger.info("FluxoG Kafka producer started")

    async def stop(self):
        """Para o producer Kafka."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("FluxoG Kafka producer stopped")

    async def publish(
        self,
        event_type: PipelineEventType,
        data: Dict[str, Any],
        key: Optional[str] = None,
    ) -> bool:
        """Publica um evento no Kafka."""
        if not self._producer:
            await self.start()

        topic = self.TOPIC_MAP.get(event_type)
        if not topic:
            logger.error(f"Unknown event type: {event_type}")
            return False

        event = {
            "event_type": event_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }

        try:
            await self._producer.send_and_wait(topic, value=event, key=key)
            self._last_published_topic = topic
            logger.debug(f"Published {event_type} to {topic}")
            return True

        except KafkaError as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            return False

    async def publish_intent_received(
        self,
        pipeline_id: str,
        intent_text: str,
        user_id: str,
        project_name: str,
    ) -> bool:
        """Publica evento de intenção recebida."""
        return await self.publish(
            PipelineEventType.INTENT_RECEIVED,
            {
                "pipeline_id": pipeline_id,
                "intent_text": intent_text,
                "user_id": user_id,
                "project_name": project_name,
            },
            key=pipeline_id,
        )

    async def publish_requirements_generated(
        self,
        pipeline_id: str,
        requirements: Dict[str, Any],
        requirements_id: str,
    ) -> bool:
        """Publica evento de requisitos gerados."""
        return await self.publish(
            PipelineEventType.REQUIREMENTS_GENERATED,
            {
                "pipeline_id": pipeline_id,
                "requirements_id": requirements_id,
                "requirements_summary": {
                    "user_stories_count": len(requirements.get("user_stories", [])),
                    "acceptance_criteria_count": len(
                        requirements.get("acceptance_criteria", [])
                    ),
                },
            },
            key=pipeline_id,
        )

    async def publish_architecture_generated(
        self,
        pipeline_id: str,
        architecture: Dict[str, Any],
        architecture_id: str,
    ) -> bool:
        """Publica evento de arquitetura gerada."""
        return await self.publish(
            PipelineEventType.ARCHITECTURE_GENERATED,
            {
                "pipeline_id": pipeline_id,
                "architecture_id": architecture_id,
                "architecture_summary": {
                    "components_count": len(architecture.get("components", [])),
                    "pattern": architecture.get("pattern", "unknown"),
                },
            },
            key=pipeline_id,
        )

    async def publish_rag_queried(
        self,
        pipeline_id: str,
        query: str,
        results_count: int,
        fallback_used: bool = False,
    ) -> bool:
        """Publica evento de consulta RAG."""
        return await self.publish(
            PipelineEventType.RAG_QUERIED,
            {
                "pipeline_id": pipeline_id,
                "query": query,
                "results_count": results_count,
                "fallback_used": fallback_used,
            },
            key=pipeline_id,
        )

    async def publish_documentation_generated(
        self,
        pipeline_id: str,
        documentation: Dict[str, Any],
        documentation_id: str,
    ) -> bool:
        """Publica evento de documentação gerada."""
        return await self.publish(
            PipelineEventType.DOCUMENTATION_GENERATED,
            {
                "pipeline_id": pipeline_id,
                "documentation_id": documentation_id,
                "doc_types": list(documentation.keys()),
            },
            key=pipeline_id,
        )

    async def publish_approval_requested(
        self,
        pipeline_id: str,
        approval_id: str,
        artifact_type: str,
        approvers: list[str],
    ) -> bool:
        """Publica evento de aprovação solicitada."""
        return await self.publish(
            PipelineEventType.APPROVAL_REQUESTED,
            {
                "pipeline_id": pipeline_id,
                "approval_id": approval_id,
                "artifact_type": artifact_type,
                "approvers_count": len(approvers),
            },
            key=pipeline_id,
        )

    async def publish_approval_completed(
        self,
        pipeline_id: str,
        approval_id: str,
        approved: bool,
        feedback: str = "",
    ) -> bool:
        """Publica evento de aprovação completada."""
        return await self.publish(
            PipelineEventType.APPROVAL_COMPLETED,
            {
                "pipeline_id": pipeline_id,
                "approval_id": approval_id,
                "approved": approved,
                "has_feedback": bool(feedback),
            },
            key=pipeline_id,
        )

    async def publish_code_generated(
        self,
        pipeline_id: str,
        code_id: str,
        files_count: int,
        lines_of_code: int,
    ) -> bool:
        """Publica evento de código gerado."""
        return await self.publish(
            PipelineEventType.CODE_GENERATED,
            {
                "pipeline_id": pipeline_id,
                "code_id": code_id,
                "files_count": files_count,
                "lines_of_code": lines_of_code,
            },
            key=pipeline_id,
        )

    async def publish_pipeline_completed(
        self,
        pipeline_id: str,
        duration_seconds: float,
        output: Dict[str, Any],
    ) -> bool:
        """Publica evento de pipeline completado."""
        return await self.publish(
            PipelineEventType.PIPELINE_COMPLETED,
            {
                "pipeline_id": pipeline_id,
                "duration_seconds": duration_seconds,
                "output_summary": {
                    "has_code": bool(output.get("generated_code")),
                    "has_docs": bool(output.get("documentation")),
                },
            },
            key=pipeline_id,
        )

    async def publish_pipeline_failed(
        self,
        pipeline_id: str,
        failed_stage: str,
        error: str,
        duration_seconds: float,
    ) -> bool:
        """Publica evento de pipeline falhou."""
        return await self.publish(
            PipelineEventType.PIPELINE_FAILED,
            {
                "pipeline_id": pipeline_id,
                "failed_stage": failed_stage,
                "error_message": error,
                "duration_seconds": duration_seconds,
            },
            key=pipeline_id,
        )

    async def publish_stage_failed(
        self,
        pipeline_id: str,
        stage: str,
        error: str,
        retryable: bool = True,
    ) -> bool:
        """Publica evento de estágio falhou."""
        return await self.publish(
            PipelineEventType.STAGE_FAILED,
            {
                "pipeline_id": pipeline_id,
                "stage": stage,
                "error_message": error,
                "retryable": retryable,
            },
            key=pipeline_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/producers/test_fluxo_g_producer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/producers/fluxo_g_producer.py \
        services/orchestrator-dynamic/tests/producers/test_fluxo_g_producer.py
git commit -m "feat(orchestrator): add Kafka event producer for Fluxo G"
```

---

## Task 6: Criar REST API para Iniciar Pipelines

**Files:**
- Create: `services/orchestrator-dynamic/src/api/routers/fluxo_g.py`
- Test: `services/orchestrator-dynamic/tests/api/test_fluxo_g_api.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/api/test_fluxo_g_api.py
import pytest
from httpx import AsyncClient
from main import app


@pytest.mark.asyncio
async def test_start_pipeline_success():
    """Testa início de pipeline com sucesso."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/fluxo-g/pipelines",
            json={
                "intent_text": "Criar um sistema de gerenciamento de tarefas",
                "project_name": "task-manager",
                "user_id": "user123",
                "tech_stack": {
                    "language": "python",
                    "framework": "fastapi",
                },
                "require_approval": True,
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert "pipeline_id" in data
    assert "status" in data
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_get_pipeline_status():
    """Testa consulta de status de pipeline."""
    # Primeiro cria um pipeline
    async with AsyncClient(app=app, base_url="http://test") as client:
        start_response = await client.post(
            "/api/v1/fluxo-g/pipelines",
            json={
                "intent_text": "API de testes",
                "project_name": "test-api",
                "user_id": "user456",
            },
        )

        pipeline_id = start_response.json()["pipeline_id"]

        # Consulta status
        status_response = await client.get(f"/api/v1/fluxo-g/pipelines/{pipeline_id}")

    assert status_response.status_code == 200
    data = status_response.json()
    assert "pipeline_id" in data
    assert "current_stage" in data
    assert "progress" in data


@pytest.mark.asyncio
async def test_list_pipelines():
    """Testa listagem de pipelines."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/fluxo-g/pipelines")

    assert response.status_code == 200
    data = response.json()
    assert "pipelines" in data
    assert isinstance(data["pipelines"], list)


@pytest.mark.asyncio
async def test_approve_pipeline():
    """Testa sinal de aprovação de pipeline."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/fluxo-g/pipelines/pipeline-123/approve",
            json={
                "approved": True,
                "feedback": "LGTM! ship it.",
            },
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cancel_pipeline():
    """Testa cancelamento de pipeline."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/fluxo-g/pipelines/pipeline-456/cancel"
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_intent_text():
    """Testa validação de intent_text vazio."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/fluxo-g/pipelines",
            json={
                "intent_text": "",
                "project_name": "test",
                "user_id": "user123",
            },
        )

    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/api/test_fluxo_g_api.py -v`
Expected: FAIL - router não existe

- [ ] **Step 3: Implement router**

```python
# services/orchestrator-dynamic/src/api/routers/fluxo_g.py
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field, validator

from orchestrator.clients.temporal_client import TemporalClient
from orchestrator.workflows.fluxo_g_workflow import FluxoGWorkflow
from orchestrator.producers.fluxo_g_producer import FluxoGEventProducer


router = APIRouter(prefix="/fluxo-g", tags=["Fluxo G"])

temporal_client = TemporalClient()
event_producer = FluxoGEventProducer()


# ==================== Request/Response Models ====================


class StartPipelineRequest(BaseModel):
    """Request para iniciar um pipeline Fluxo G."""

    intent_text: str = Field(..., min_length=10, max_length=5000)
    project_name: str = Field(..., min_length=2, max_length=100)
    user_id: str = Field(..., min_length=1)
    tech_stack: Optional[dict] = Field(
        default=None,
        example={
            "language": "python",
            "framework": "fastapi",
            "database": "postgresql",
        },
    )
    require_approval: bool = Field(default=True)
    approvers: Optional[List[str]] = Field(default=None)
    metadata: Optional[dict] = Field(default_factory=dict)

    @validator("project_name")
    def validate_project_name(cls, v):
        """Valida nome do projeto (snake_case ou kebab-case)."""
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError(
                "project_name deve conter apenas caracteres alfanuméricos, _ ou -"
            )
        return v


class ApprovalRequest(BaseModel):
    """Request para aprovação de pipeline."""

    approved: bool = Field(..., description="True se aprovado, False se rejeitado")
    feedback: str = Field(default="", max_length=2000)
    approver_id: str = Field(..., min_length=1)


class PipelineResponse(BaseModel):
    """Response de status de pipeline."""

    pipeline_id: str
    status: str
    current_stage: str
    progress: float
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


class PipelineListResponse(BaseModel):
    """Response de listagem de pipelines."""

    pipelines: List[PipelineResponse]
    total: int
    page: int
    page_size: int


# ==================== Endpoints ====================


@router.post(
    "/pipelines",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Iniciar novo pipeline Fluxo G",
)
async def start_pipeline(
    request: StartPipelineRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Inicia um novo pipeline do Fluxo G.

    O pipeline executa as seguintes etapas:
    1. Requirements Engineering
    2. Architectural Planning
    3. Knowledge Graph RAG (com fallback)
    4. Documentation Generation
    5. Approval (opcional)
    6. Code Generation
    7. Deployment preparation
    """

    # Publica evento de intenção recebida
    pipeline_id = f"fluxo-g-{datetime.utcnow().timestamp()}"

    await event_producer.publish_intent_received(
        pipeline_id=pipeline_id,
        intent_text=request.intent_text,
        user_id=request.user_id,
        project_name=request.project_name,
    )

    # Inicia workflow Temporal
    try:
        workflow_id = await temporal_client.start_workflow(
            FluxoGWorkflow.run,
            args={
                "intent_text": request.intent_text,
                "project_name": request.project_name,
                "user_id": request.user_id,
                "tech_stack": request.tech_stack,
                "require_approval": request.require_approval,
            },
            id=pipeline_id,
            task_queue="fluxo-g-task-queue",
            memo={
                "approvers": request.approvers or [],
                "approval_completed": False,
                "approval_approved": False,
                "approval_feedback": "",
            },
        )

        return {
            "pipeline_id": workflow_id,
            "status": "running",
            "message": "Pipeline iniciado com sucesso",
            "current_stage": "requirements",
            "progress": 0.0,
        }

    except Exception as e:
        # Publica evento de falha
        await event_producer.publish_pipeline_failed(
            pipeline_id=pipeline_id,
            failed_stage="initialization",
            error=str(e),
            duration_seconds=0,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao iniciar pipeline: {str(e)}",
        )


@router.get(
    "/pipelines/{pipeline_id}",
    response_model=PipelineResponse,
    summary="Obter status de pipeline",
)
async def get_pipeline_status(pipeline_id: str) -> PipelineResponse:
    """
    Retorna o status atual de um pipeline.

    Inclui estágio atual, progresso, e timestamps.
    """
    try:
        # Consulta workflow Temporal
        workflow_handle = temporal_client.get_workflow_handle(pipeline_id)

        current_stage = await workflow_handle.query(FluxoGWorkflow.current_stage)
        progress = await workflow_handle.query(FluxoGWorkflow.progress)
        workflow_status = await workflow_handle.query(FluxoGWorkflow.status)

        # Descrição do workflow
        description = await workflow_handle.describe()

        return PipelineResponse(
            pipeline_id=pipeline_id,
            status=workflow_status,
            current_stage=current_stage,
            progress=progress,
            created_at=description.creation_time,
            started_at=None,  # Temporal não expõe started time diretamente
            completed_at=None,
            duration_seconds=None,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline não encontrado: {str(e)}",
        )


@router.get(
    "/pipelines",
    response_model=PipelineListResponse,
    summary="Listar pipelines",
)
async def list_pipelines(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
) -> PipelineListResponse:
    """
    Lista pipelines do Fluxo G.

    Suporta paginação e filtro por status.
    """
    # TODO: Implementar listagem com Redis/MongoDB store
    return PipelineListResponse(
        pipelines=[],
        total=0,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/pipelines/{pipeline_id}/approve",
    response_model=dict,
    summary="Aprovar/rejeitar pipeline",
)
async def approve_pipeline(
    pipeline_id: str,
    request: ApprovalRequest,
) -> dict:
    """
    Envia sinal de aprovação/rejeição para um pipeline aguardando aprovação.
    """
    try:
        workflow_handle = temporal_client.get_workflow_handle(pipeline_id)

        # Envia sinal
        await workflow_handle.signal(
            FluxoGWorkflow.approve,
            approved=request.approved,
            feedback=request.feedback,
        )

        # Publica evento
        await event_producer.publish_approval_completed(
            pipeline_id=pipeline_id,
            approval_id="",  # Obtido do memo do workflow
            approved=request.approved,
            feedback=request.feedback,
        )

        return {
            "message": "Sinal de aprovação enviado com sucesso",
            "approved": request.approved,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao enviar aprovação: {str(e)}",
        )


@router.post(
    "/pipelines/{pipeline_id}/cancel",
    response_model=dict,
    summary="Cancelar pipeline",
)
async def cancel_pipeline(pipeline_id: str) -> dict:
    """
    Cancela um pipeline em execução.
    """
    try:
        workflow_handle = temporal_client.get_workflow_handle(pipeline_id)
        await workflow_handle.cancel()

        return {
            "message": "Pipeline cancelado com sucesso",
            "pipeline_id": pipeline_id,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao cancelar pipeline: {str(e)}",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/api/test_fluxo_g_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/api/routers/fluxo_g.py \
        services/orchestrator-dynamic/tests/api/test_fluxo_g_api.py
git commit -m "feat(orchestrator): add REST API for Fluxo G pipelines"
```

---

## Task 7: Criar Service de Persistência de Pipeline

**Files:**
- Create: `services/orchestrator-dynamic/src/services/pipeline_store.py`
- Test: `services/orchestrator-dynamic/tests/services/test_pipeline_store.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/services/test_pipeline_store.py
import pytest
from datetime import datetime, timedelta
from orchestrator.services.pipeline_store import (
    PipelineStore,
    PipelineRecord,
)


@pytest.mark.asyncio
async def test_save_pipeline_record():
    """Testa salvar registro de pipeline."""
    store = PipelineStore()

    record = PipelineRecord(
        pipeline_id="pipeline-123",
        user_id="user456",
        project_name="test-project",
        intent_text="Intent de teste",
        status="running",
        current_stage="requirements",
    )

    await store.save(record)

    retrieved = await store.get("pipeline-123")
    assert retrieved is not None
    assert retrieved.pipeline_id == "pipeline-123"
    assert retrieved.status == "running"


@pytest.mark.asyncio
async def test_update_pipeline_status():
    """Testa atualizar status de pipeline."""
    store = PipelineStore()

    # Cria registro inicial
    record = PipelineRecord(
        pipeline_id="pipeline-789",
        user_id="user789",
        project_name="project-b",
        intent_text="Intent B",
        status="running",
        current_stage="architecture",
    )
    await store.save(record)

    # Atualiza status
    await store.update_status(
        "pipeline-789",
        status="completed",
        current_stage="completed",
        progress=100.0,
    )

    retrieved = await store.get("pipeline-789")
    assert retrieved.status == "completed"
    assert retrieved.current_stage == "completed"


@pytest.mark.asyncio
async def test_list_pipelines_by_user():
    """Testa listar pipelines por usuário."""
    store = PipelineStore()

    # Cria pipelines para dois usuários
    await store.save(
        PipelineRecord(
            pipeline_id="pipe-1",
            user_id="user-a",
            project_name="proj-a",
            intent_text="Intent A",
            status="completed",
            current_stage="completed",
        )
    )

    await store.save(
        PipelineRecord(
            pipeline_id="pipe-2",
            user_id="user-a",
            project_name="proj-b",
            intent_text="Intent B",
            status="running",
            current_stage="requirements",
        )
    )

    await store.save(
        PipelineRecord(
            pipeline_id="pipe-3",
            user_id="user-b",
            project_name="proj-c",
            intent_text="Intent C",
            status="pending",
            current_stage="pending",
        )
    )

    # Lista pipelines do user-a
    user_a_pipelines = await store.list_by_user("user-a")

    assert len(user_a_pipelines) == 2
    assert all(p.user_id == "user-a" for p in user_a_pipelines)


@pytest.mark.asyncio
async def test_get_active_pipelines():
    """Testa buscar pipelines ativos."""
    store = PipelineStore()

    await store.save(
        PipelineRecord(
            pipeline_id="active-1",
            user_id="user-x",
            project_name="proj-x",
            intent_text="X",
            status="running",
            current_stage="requirements",
        )
    )

    await store.save(
        PipelineRecord(
            pipeline_id="completed-1",
            user_id="user-y",
            project_name="proj-y",
            intent_text="Y",
            status="completed",
            current_stage="completed",
        )
    )

    active = await store.list_active()

    assert len(active) == 1
    assert active[0].pipeline_id == "active-1"


@pytest.mark.asyncio
async def test_delete_old_records():
    """Testa deletar registros antigos."""
    store = PipelineStore()

    # Cria registro antigo
    old_record = PipelineRecord(
        pipeline_id="old-pipe",
        user_id="user-z",
        project_name="proj-z",
        intent_text="Z",
        status="completed",
        current_stage="completed",
        created_at=datetime.utcnow() - timedelta(days=40),
    )
    await store.save(old_record)

    # Cria registro recente
    recent_record = PipelineRecord(
        pipeline_id="recent-pipe",
        user_id="user-z",
        project_name="proj-w",
        intent_text="W",
        status="completed",
        current_stage="completed",
        created_at=datetime.utcnow() - timedelta(days=1),
    )
    await store.save(recent_record)

    # Deleta registros com mais de 30 dias
    deleted = await store.delete_older_than(days=30)

    assert deleted == 1

    old_check = await store.get("old-pipe")
    assert old_check is None

    recent_check = await store.get("recent-pipe")
    assert recent_check is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/services/test_pipeline_store.py -v`
Expected: FAIL - service não existe

- [ ] **Step 3: Implement service**

```python
# services/orchestrator-dynamic/src/services/pipeline_store.py
from typing import List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
import os
import logging

logger = logging.getLogger(__name__)


class PipelineRecord(BaseModel):
    """Registro de pipeline do Fluxo G."""

    pipeline_id: str
    user_id: str
    project_name: str
    intent_text: str
    status: str
    current_stage: str
    progress: float = 0.0
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tech_stack: Optional[dict] = None
    requirements_id: Optional[str] = None
    architecture_id: Optional[str] = None
    documentation_id: Optional[str] = None
    code_id: Optional[str] = None
    metadata: dict = {}

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PipelineStore:
    """Serviço de persistência de pipelines."""

    def __init__(self):
        self._mongodb_url = os.getenv(
            "MONGODB_URL", "mongodb://localhost:27017"
        )
        self._database_name = os.getenv(
            "MONGODB_DATABASE", "neural-hive-mind"
        )
        self._collection_name = "fluxo_g_pipelines"
        self._client: Optional[AsyncIOMotorClient] = None
        self._collection = None

    async def _get_collection(self):
        """Retorna a coleção MongoDB."""
        if self._collection is None:
            self._client = AsyncIOMotorClient(self._mongodb_url)
            database = self._client[self._database_name]
            self._collection = database[self._collection_name]

            # Cria índices
            await self._collection.create_index("pipeline_id", unique=True)
            await self._collection.create_index("user_id")
            await self._collection.create_index("status")
            await self._collection.create_index("created_at")

        return self._collection

    async def save(self, record: PipelineRecord) -> str:
        """Salva ou atualiza um registro de pipeline."""
        collection = await self._get_collection()

        doc = record.model_dump()
        if doc.get("created_at") is None:
            doc["created_at"] = datetime.utcnow()

        await collection.update_one(
            {"pipeline_id": record.pipeline_id},
            {"$set": doc},
            upsert=True,
        )

        logger.debug(f"Saved pipeline record: {record.pipeline_id}")
        return record.pipeline_id

    async def get(self, pipeline_id: str) -> Optional[PipelineRecord]:
        """Retorna um registro de pipeline."""
        collection = await self._get_collection()

        doc = await collection.find_one({"pipeline_id": pipeline_id})
        if not doc:
            return None

        doc.pop("_id", None)
        return PipelineRecord(**doc)

    async def update_status(
        self,
        pipeline_id: str,
        status: str,
        current_stage: Optional[str] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Atualiza o status de um pipeline."""
        collection = await self._get_collection()

        update_doc = {"status": status}
        if current_stage is not None:
            update_doc["current_stage"] = current_stage
        if progress is not None:
            update_doc["progress"] = progress
        if error is not None:
            update_doc["error"] = error

        if status == "completed":
            update_doc["completed_at"] = datetime.utcnow()

        result = await collection.update_one(
            {"pipeline_id": pipeline_id},
            {"$set": update_doc},
        )

        return result.modified_count > 0

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 100,
    ) -> List[PipelineRecord]:
        """Lista pipelines de um usuário."""
        collection = await self._get_collection()

        cursor = collection.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)

        records = []
        for doc in docs:
            doc.pop("_id", None)
            records.append(PipelineRecord(**doc))

        return records

    async def list_active(
        self,
    ) -> List[PipelineRecord]:
        """Lista pipelines ativos (running, awaiting_approval)."""
        collection = await self._get_collection()

        cursor = collection.find({
            "status": {"$in": ["running", "awaiting_approval"]}
        }).sort("created_at", -1)

        docs = await cursor.to_list(length=1000)

        records = []
        for doc in docs:
            doc.pop("_id", None)
            records.append(PipelineRecord(**doc))

        return records

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[str] = None,
    ) -> tuple[List[PipelineRecord], int]:
        """Lista todos os pipelines com paginação."""
        collection = await self._get_collection()

        query = {}
        if status_filter:
            query["status"] = status_filter

        total = await collection.count_documents(query)

        skip = (page - 1) * page_size
        cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(page_size)

        docs = await cursor.to_list(length=page_size)

        records = []
        for doc in docs:
            doc.pop("_id", None)
            records.append(PipelineRecord(**doc))

        return records, total

    async def delete_older_than(self, days: int = 30) -> int:
        """Deleta registros mais antigos que N dias."""
        collection = await self._get_collection()

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = await collection.delete_many({
            "created_at": {"$lt": cutoff_date},
            "status": {"$in": ["completed", "failed", "cancelled"]},
        })

        logger.info(f"Deleted {result.deleted_count} pipeline records older than {days} days")
        return result.deleted_count

    async def close(self):
        """Fecha a conexão MongoDB."""
        if self._client:
            self._client.close()
            self._client = None
            self._collection = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/services/test_pipeline_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/services/pipeline_store.py \
        services/orchestrator-dynamic/tests/services/test_pipeline_store.py
git commit -m "feat(orchestrator): add pipeline persistence store"
```

---

## Task 8: Criar Middleware de Injeção de Eventos

**Files:**
- Create: `services/orchestrator-dynamic/src/middleware/pipeline_events.py`
- Test: `services/orchestrator-dynamic/tests/middleware/test_pipeline_events.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/middleware/test_pipeline_events.py
import pytest
from unittest.mock import AsyncMock, patch
from orchestrator.middleware.pipeline_events import (
    PipelineEventInjector,
    PipelineEventContext,
)


@pytest.mark.asyncio
async def test_event_injector_intercepts_workflow_start():
    """Testa interceptor captura início de workflow."""
    injector = PipelineEventInjector()

    context = PipelineEventContext(
        pipeline_id="pipeline-123",
        event_type="workflow_started",
        data={"stage": "requirements"},
    )

    await injector.on_workflow_event(context)

    assert injector.last_event["event_type"] == "workflow_started"
    assert injector.last_event["pipeline_id"] == "pipeline-123"


@pytest.mark.asyncio
async def test_event_injector_publishes_to_kafka():
    """Testa interceptor publica eventos Kafka."""
    injector = PipelineEventInjector()

    with patch.object(injector._producer, "publish", new_callable=AsyncMock) as mock_publish:
        context = PipelineEventContext(
            pipeline_id="pipeline-456",
            event_type="stage_completed",
            data={"stage": "requirements", "success": True},
        )

        await injector.on_workflow_event(context)

        mock_publish.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/middleware/test_pipeline_events.py -v`
Expected: FAIL - middleware não existe

- [ ] **Step 3: Implement middleware**

```python
# services/orchestrator-dynamic/src/middleware/pipeline_events.py
from typing import Dict, Any, Optional
from pydantic import BaseModel
import logging

from orchestrator.producers.fluxo_g_producer import (
    FluxoGEventProducer,
    PipelineEventType,
)

logger = logging.getLogger(__name__)


class PipelineEventContext(BaseModel):
    """Contexto de evento de pipeline."""
    pipeline_id: str
    event_type: str
    data: Dict[str, Any] = {}
    timestamp: Optional[float] = None


class PipelineEventInjector:
    """
    Middleware que intercepta eventos do workflow e publica no Kafka.

    Integra o workflow Temporal com o sistema de eventos Kafka,
    permitindo rastreamento e observabilidade.
    """

    def __init__(self):
        self._producer = FluxoGEventProducer()
        self._last_event = None

    @property
    def last_event(self) -> Optional[dict]:
        """Para testes: retorna último evento processado."""
        return self._last_event

    async def on_workflow_event(self, context: PipelineEventContext) -> None:
        """
        Processa um evento do workflow e publica no Kafka.

        Mapeia eventos internos do workflow para eventos Kafka padronizados.
        """
        self._last_event = {
            "event_type": context.event_type,
            "pipeline_id": context.pipeline_id,
            "data": context.data,
        }

        # Mapeamento de eventos
        event_mapping = {
            "workflow_started": self._on_started,
            "stage_started": self._on_stage_started,
            "stage_completed": self._on_stage_completed,
            "stage_failed": self._on_stage_failed,
            "workflow_completed": self._on_completed,
            "workflow_failed": self._on_failed,
            "approval_requested": self._on_approval_requested,
            "approval_completed": self._on_approval_completed,
        }

        handler = event_mapping.get(context.event_type)
        if handler:
            await handler(context)
        else:
            logger.warning(f"Unknown event type: {context.event_type}")

    async def _on_started(self, context: PipelineEventContext) -> None:
        """Lida com evento de workflow iniciado."""
        await self._producer.publish_intent_received(
            pipeline_id=context.pipeline_id,
            intent_text=context.data.get("intent_text", ""),
            user_id=context.data.get("user_id", ""),
            project_name=context.data.get("project_name", ""),
        )

    async def _on_stage_started(self, context: PipelineEventContext) -> None:
        """Lida com evento de estágio iniciado."""
        logger.info(
            f"Stage {context.data.get('stage')} started for pipeline {context.pipeline_id}"
        )

    async def _on_stage_completed(self, context: PipelineEventContext) -> None:
        """Lida com evento de estágio completado."""
        stage = context.data.get("stage")

        if stage == "requirements":
            await self._producer.publish_requirements_generated(
                pipeline_id=context.pipeline_id,
                requirements=context.data.get("requirements", {}),
                requirements_id=context.data.get("requirements_id", ""),
            )
        elif stage == "architecture":
            await self._producer.publish_architecture_generated(
                pipeline_id=context.pipeline_id,
                architecture=context.data.get("architecture", {}),
                architecture_id=context.data.get("architecture_id", ""),
            )
        elif stage == "documentation":
            await self._producer.publish_documentation_generated(
                pipeline_id=context.pipeline_id,
                documentation=context.data.get("documentation", {}),
                documentation_id=context.data.get("documentation_id", ""),
            )
        elif stage == "code_generation":
            code_data = context.data.get("generated_code", {})
            await self._producer.publish_code_generated(
                pipeline_id=context.pipeline_id,
                code_id=context.data.get("code_id", ""),
                files_count=code_data.get("files_count", 0),
                lines_of_code=code_data.get("lines_of_code", 0),
            )

    async def _on_stage_failed(self, context: PipelineEventContext) -> None:
        """Lida com evento de estágio falhou."""
        await self._producer.publish_stage_failed(
            pipeline_id=context.pipeline_id,
            stage=context.data.get("stage", ""),
            error=context.data.get("error", ""),
            retryable=context.data.get("retryable", True),
        )

    async def _on_completed(self, context: PipelineEventContext) -> None:
        """Lida com evento de workflow completado."""
        await self._producer.publish_pipeline_completed(
            pipeline_id=context.pipeline_id,
            duration_seconds=context.data.get("duration_seconds", 0),
            output=context.data.get("output", {}),
        )

    async def _on_failed(self, context: PipelineEventContext) -> None:
        """Lida com evento de workflow falhou."""
        await self._producer.publish_pipeline_failed(
            pipeline_id=context.pipeline_id,
            failed_stage=context.data.get("failed_stage", ""),
            error=context.data.get("error", ""),
            duration_seconds=context.data.get("duration_seconds", 0),
        )

    async def _on_approval_requested(self, context: PipelineEventContext) -> None:
        """Lida com evento de aprovação solicitada."""
        await self._producer.publish_approval_requested(
            pipeline_id=context.pipeline_id,
            approval_id=context.data.get("approval_id", ""),
            artifact_type=context.data.get("artifact_type", ""),
            approvers=context.data.get("approvers", []),
        )

    async def _on_approval_completed(self, context: PipelineEventContext) -> None:
        """Lida com evento de aprovação completada."""
        await self._producer.publish_approval_completed(
            pipeline_id=context.pipeline_id,
            approval_id=context.data.get("approval_id", ""),
            approved=context.data.get("approved", False),
            feedback=context.data.get("feedback", ""),
        )

    async def close(self):
        """Fecha recursos do middleware."""
        await self._producer.stop()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/middleware/test_pipeline_events.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/middleware/pipeline_events.py \
        services/orchestrator-dynamic/tests/middleware/test_pipeline_events.py
git commit -m "feat(orchestrator): add pipeline event injector middleware"
```

---

## Task 9: Criar Configurações e Feature Flags

**Files:**
- Create: `services/orchestrator-dynamic/src/config/fluxo_g_settings.py`
- Test: `services/orchestrator-dynamic/tests/config/test_fluxo_g_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/config/test_fluxo_g_settings.py
import pytest
import os
from orchestrator.config.fluxo_g_settings import (
    FluxoGSettings,
    get_fluxo_g_settings,
)


@pytest.mark.asyncio
async def test_default_settings():
    """Testa configurações padrão."""
    settings = FluxoGSettings()

    assert settings.enable_requirements is True
    assert settings.enable_architecture is True
    assert settings.enable_rag is True
    assert settings.enable_documentation is True
    assert settings.enable_approval is True
    assert settings.enable_code_generation is True


@pytest.mark.asyncio
async def test_settings_from_env():
    """Testa configurações de variáveis de ambiente."""
    os.environ["FLUXO_G_ENABLE_APPROVAL"] = "false"
    os.environ["FLUXO_G_RAG_ALPHA"] = "0.9"
    os.environ["FLUXO_G_STAGE_TIMEOUT"] = "600"

    settings = get_fluxo_g_settings()

    assert settings.enable_approval is False
    assert settings.rag_alpha == 0.9
    assert settings.stage_timeout_seconds == 600

    # Cleanup
    del os.environ["FLUXO_G_ENABLE_APPROVAL"]
    del os.environ["FLUXO_G_RAG_ALPHA"]
    del os.environ["FLUXO_G_STAGE_TIMEOUT"]


@pytest.mark.asyncio
async def test_disabled_stage_skips_execution():
    """Testa que estágio desabilitado pula execução."""
    settings = FluxoGSettings(
        enable_documentation=False,
    )

    assert settings.is_stage_enabled("documentation") is False
    assert settings.is_stage_enabled("requirements") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/config/test_fluxo_g_settings.py -v`
Expected: FAIL - configurações não existem

- [ ] **Step 3: Implement settings**

```python
# services/orchestrator-dynamic/src/config/fluxo_g_settings.py
from pydantic import BaseSettings, Field
from typing import List, Optional
import os


class FluxoGSettings(BaseSettings):
    """Configurações do Fluxo G."""

    # Feature flags por estágio
    enable_requirements: bool = Field(default=True, env="FLUXO_G_ENABLE_REQUIREMENTS")
    enable_architecture: bool = Field(default=True, env="FLUXO_G_ENABLE_ARCHITECTURE")
    enable_rag: bool = Field(default=True, env="FLUXO_G_ENABLE_RAG")
    enable_documentation: bool = Field(default=True, env="FLUXO_G_ENABLE_DOCUMENTATION")
    enable_approval: bool = Field(default=True, env="FLUXO_G_ENABLE_APPROVAL")
    enable_code_generation: bool = Field(default=True, env="FLUXO_G_ENABLE_CODE_GENERATION")

    # Configurações de RAG
    rag_alpha: float = Field(default=0.7, env="FLUXO_G_RAG_ALPHA")
    rag_top_k: int = Field(default=5, env="FLUXO_G_RAG_TOP_K")
    rag_enable_fallback: bool = Field(default=True, env="FLUXO_G_RAG_ENABLE_FALLBACK")

    # Configurações de timeout
    stage_timeout_seconds: int = Field(default=300, env="FLUXO_G_STAGE_TIMEOUT")
    pipeline_timeout_seconds: int = Field(default=3600, env="FLUXO_G_PIPELINE_TIMEOUT")

    # Configurações de retry
    max_stage_retries: int = Field(default=3, env="FLUXO_G_MAX_RETRIES")

    # Configurações de aprovação
    default_approvers: List[str] = Field(default_factory=list, env="FLUXO_G_DEFAULT_APPROVERS")
    approval_timeout_seconds: int = Field(default=86400, env="FLUXO_G_APPROVAL_TIMEOUT")  # 24h

    # Configurações de código
    default_tech_stack: dict = Field(
        default_factory=lambda: {
            "language": "python",
            "framework": "fastapi",
            "database": "postgresql",
        }
    )

    # Observabilidade
    enable_kafka_events: bool = Field(default=True, env="FLUXO_G_ENABLE_KAFKA_EVENTS")
    enable_metrics: bool = Field(default=True, env="FLUXO_G_ENABLE_METRICS")

    class Config:
        env_file = ".env"
        case_sensitive = False

    def is_stage_enabled(self, stage: str) -> bool:
        """Verifica se um estágio está habilitado."""
        stage_map = {
            "requirements": self.enable_requirements,
            "architecture": self.enable_architecture,
            "rag_query": self.enable_rag,
            "documentation": self.enable_documentation,
            "approval": self.enable_approval,
            "code_generation": self.enable_code_generation,
        }
        return stage_map.get(stage, True)

    def get_enabled_stages(self) -> List[str]:
        """Retorna lista de estágios habilitados."""
        all_stages = [
            "requirements",
            "architecture",
            "rag_query",
            "documentation",
            "approval",
            "code_generation",
        ]
        return [s for s in all_stages if self.is_stage_enabled(s)]


_global_settings: Optional[FluxoGSettings] = None


def get_fluxo_g_settings() -> FluxoGSettings:
    """Retorna instância singleton de configurações."""
    global _global_settings
    if _global_settings is None:
        _global_settings = FluxoGSettings()
    return _global_settings


def reset_fluxo_g_settings():
    """Reseta instância de configurações (para testes)."""
    global _global_settings
    _global_settings = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/config/test_fluxo_g_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/config/fluxo_g_settings.py \
        services/orchestrator-dynamic/tests/config/test_fluxo_g_settings.py
git commit -m "feat(orchestrator): add FluxoG settings and feature flags"
```

---

## Task 10: Criar Worker Temporal para Fluxo G

**Files:**
- Create: `services/orchestrator-dynamic/src/workers/fluxo_g_worker.py`
- Test: `services/orchestrator-dynamic/tests/workers/test_fluxo_g_worker.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/workers/test_fluxo_g_worker.py
import pytest
from orchestrator.workers.fluxo_g_worker import (
    create_fluxo_g_worker,
    FluxoGWorkerConfig,
)


@pytest.mark.asyncio
async def test_worker_creation():
    """Testa criação do worker Fluxo G."""
    config = FluxoGWorkerConfig(
        task_queue="fluxo-g-task-queue",
        temporal_host="localhost",
        temporal_port=7233,
    )

    worker = create_fluxo_g_worker(config)

    assert worker is not None
    assert worker.task_queue == "fluxo-g-task-queue"


def test_worker_config_defaults():
    """Testa configurações padrão do worker."""
    config = FluxoGWorkerConfig()

    assert config.task_queue == "fluxo-g-task-queue"
    assert config.max_cached_workflows == 100
    assert config.max_concurrent_activities == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest services/orchestrator-dynamic/tests/workers/test_fluxo_g_worker.py -v`
Expected: FAIL - worker não existe

- [ ] **Step 3: Implement worker**

```python
# services/orchestrator-dynamic/src/workers/fluxo_g_worker.py
from typing import Optional
from pydantic import BaseSettings, Field
import os

from temporalio.worker import Worker
from temporalio.client import Client
from temporalio.worker import WorkerConfig

from orchestrator.workflows.fluxo_g_workflow import FluxoGWorkflow
from orchestrator.activities.fluxo_g_activities import (
    GenerateRequirementsActivity,
    GenerateArchitectureActivity,
    QueryRAGActivity,
    GenerateDocumentationActivity,
    RequestApprovalActivity,
    GenerateCodeActivity,
)


class FluxoGWorkerConfig(BaseSettings):
    """Configurações do worker Fluxo G."""

    task_queue: str = Field(default="fluxo-g-task-queue", env="TEMPORAL_TASK_QUEUE")
    temporal_host: str = Field(default="localhost", env="TEMPORAL_HOST")
    temporal_port: int = Field(default=7233, env="TEMPORAL_PORT")
    temporal_namespace: str = Field(default="default", env="TEMPORAL_NAMESPACE")
    max_cached_workflows: int = Field(default=100, env="WORKER_MAX_CACHED_WORKFLOWS")
    max_concurrent_activities: int = Field(default=50, env="WORKER_MAX_CONCURRENT_ACTIVITIES")
    max_concurrent_workflow_tasks: int = Field(default=20, env="WORKER_MAX_CONCURRENT_TASKS")

    class Config:
        env_file = ".env"


async def create_fluxo_g_worker(
    config: Optional[FluxoGWorkerConfig] = None,
    client: Optional[Client] = None,
) -> Worker:
    """
    Cria e configura um worker Temporal para o Fluxo G.

    Args:
        config: Configurações do worker
        client: Cliente Temporal existente (opcional)

    Returns:
        Worker configurado e pronto para iniciar
    """
    if config is None:
        config = FluxoGWorkerConfig()

    if client is None:
        client = await Client.connect(
            f"{config.temporal_host}:{config.temporal_port}",
            namespace=config.temporal_namespace,
        )

    # Cria atividades
    activities = {
        "generate-requirements": GenerateRequirementsActivity(),
        "generate-architecture": GenerateArchitectureActivity(),
        "query-rag": QueryRAGActivity(),
        "generate-documentation": GenerateDocumentationActivity(),
        "request-approval": RequestApprovalActivity(),
        "generate-code": GenerateCodeActivity(),
    }

    # Configura worker
    worker = Worker(
        client=client,
        task_queue=config.task_queue,
        workflows=[FluxoGWorkflow],
        activities=activities,
        max_cached_workflows=config.max_cached_workflows,
        max_concurrent_activities=config.max_concurrent_activities,
        max_concurrent_workflow_tasks=config.max_concurrent_workflow_tasks,
    )

    return worker


async def run_fluxo_g_worker(
    config: Optional[FluxoGWorkerConfig] = None,
) -> None:
    """
    Executa o worker Fluxo G de forma bloqueante.

    Use este método para iniciar o worker em um processo dedicado.
    """
    import asyncio
    import signal

    worker = await create_fluxo_g_worker(config)

    # Configura graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    print("Fluxo G Worker started. Press Ctrl+C to stop.")

    # Executa worker até shutdown
    await worker.run()

    print("Fluxo G Worker stopped.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_fluxo_g_worker())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest services/orchestrator-dynamic/tests/workers/test_fluxo_g_worker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator-dynamic/src/workers/fluxo_g_worker.py \
        services/orchestrator-dynamic/tests/workers/test_fluxo_g_worker.py
git commit -m "feat(orchestrator): add Temporal worker for Fluxo G"
```

---

## Task 11: Criar Manifestos Kubernetes

**Files:**
- Create: `services/orchestrator-dynamic/deployments/fluxo-g/`
- Test: N/A

- [ ] **Step 1: Create deployment manifest**

```yaml
# services/orchestrator-dynamic/deployments/fluxo-g/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator-dynamic-fluxog
  namespace: neural-hive-mind
  labels:
    app: orchestrator-dynamic
    component: fluxo-g
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orchestrator-dynamic
      component: fluxo-g
  template:
    metadata:
      labels:
        app: orchestrator-dynamic
        component: fluxo-g
    spec:
      containers:
      - name: orchestrator
        image: neural-hive-mind/orchestrator-dynamic:latest
        ports:
        - containerPort: 8003
          name: http
        - containerPort: 8013
          name: metrics
        env:
        - name: TEMPORAL_HOST
          value: "temporal-frontend.temporal"
        - name: TEMPORAL_PORT
          value: "7233"
        - name: TEMPORAL_TASK_QUEUE
          value: "fluxo-g-task-queue"
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka.neural-hive-mind:9092"
        - name: MONGODB_URL
          valueFrom:
            secretKeyRef:
              name: mongodb-secret
              key: connection-string
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: url
        # Feature flags
        - name: FLUXO_G_ENABLE_REQUIREMENTS
          value: "true"
        - name: FLUXO_G_ENABLE_ARCHITECTURE
          value: "true"
        - name: FLUXO_G_ENABLE_RAG
          value: "true"
        - name: FLUXO_G_ENABLE_DOCUMENTATION
          value: "true"
        - name: FLUXO_G_ENABLE_APPROVAL
          value: "true"
        - name: FLUXO_G_ENABLE_CODE_GENERATION
          value: "true"
        - name: FLUXO_G_ENABLE_KAFKA_EVENTS
          value: "true"
        # Service URLs
        - name: REQUIREMNTS_SERVICE_URL
          value: "http://requirements-engineering:8010"
        - name: ARCHITECT_SERVICE_URL
          value: "http://architect-agent:8008"
        - name: RAG_SERVICE_URL
          value: "http://knowledge-graph-rag:8016"
        - name: DOCS_SERVICE_URL
          value: "http://documentation-generation:8014"
        - name: APPROVAL_SERVICE_URL
          value: "http://approval-gateway:8017"
        - name: CODE_FORGE_URL
          value: "http://code-forge:8005"
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 2Gi
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8003
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8003
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: orchestrator-dynamic-fluxog
  namespace: neural-hive-mind
  labels:
    app: orchestrator-dynamic
    component: fluxo-g
spec:
  type: ClusterIP
  ports:
  - port: 8003
    targetPort: 8003
    name: http
  - port: 8013
    targetPort: 8013
    name: metrics
  selector:
    app: orchestrator-dynamic
    component: fluxo-g
---
# Worker dedicado para Fluxo G
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator-fluxog-worker
  namespace: neural-hive-mind
  labels:
    app: orchestrator-worker
    component: fluxo-g
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orchestrator-worker
      component: fluxo-g
  template:
    metadata:
      labels:
        app: orchestrator-worker
        component: fluxo-g
    spec:
      containers:
      - name: worker
        image: neural-hive-mind/orchestrator-dynamic:latest
        command: ["python", "-m", "orchestrator.workers.fluxo_g_worker"]
        env:
        - name: TEMPORAL_HOST
          value: "temporal-frontend.temporal"
        - name: TEMPORAL_PORT
          value: "7233"
        - name: TEMPORAL_TASK_QUEUE
          value: "fluxo-g-task-queue"
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka.neural-hive-mind:9092"
        - name: MONGODB_URL
          valueFrom:
            secretKeyRef:
              name: mongodb-secret
              key: connection-string
        # Feature flags
        - name: FLUXO_G_ENABLE_REQUIREMENTS
          value: "true"
        - name: FLUXO_G_ENABLE_ARCHITECTURE
          value: "true"
        - name: FLUXO_G_ENABLE_RAG
          value: "true"
        - name: FLUXO_G_ENABLE_DOCUMENTATION
          value: "true"
        - name: FLUXO_G_ENABLE_APPROVAL
          value: "true"
        - name: FLUXO_G_ENABLE_CODE_GENERATION
          value: "true"
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 1Gi
```

- [ ] **Step 2: Create ConfigMap**

```yaml
# services/orchestrator-dynamic/deployments/fluxo-g/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orchestrator-fluxog-config
  namespace: neural-hive-mind
data:
  # Feature flags
  FLUXO_G_ENABLE_REQUIREMENTS: "true"
  FLUXO_G_ENABLE_ARCHITECTURE: "true"
  FLUXO_G_ENABLE_RAG: "true"
  FLUXO_G_ENABLE_DOCUMENTATION: "true"
  FLUXO_G_ENABLE_APPROVAL: "true"
  FLUXO_G_ENABLE_CODE_GENERATION: "true"

  # RAG settings
  FLUXO_G_RAG_ALPHA: "0.7"
  FLUXO_G_RAG_TOP_K: "5"
  FLUXO_G_RAG_ENABLE_FALLBACK: "true"

  # Timeouts
  FLUXO_G_STAGE_TIMEOUT: "300"
  FLUXO_G_PIPELINE_TIMEOUT: "3600"
  FLUXO_G_MAX_RETRIES: "3"

  # Tech stack padrão
  DEFAULT_LANGUAGE: "python"
  DEFAULT_FRAMEWORK: "fastapi"
  DEFAULT_DATABASE: "postgresql"

  # Observabilidade
  FLUXO_G_ENABLE_KAFKA_EVENTS: "true"
  FLUXO_G_ENABLE_METRICS: "true"
```

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator-dynamic/deployments/fluxo-g/
git commit -m "feat(orchestrator): add Kubernetes manifests for Fluxo G"
```

---

## Task 12: Criar Testes de Integração End-to-End

**Files:**
- Create: `services/orchestrator-dynamic/tests/integration/test_fluxo_g_e2e.py`
- Test: `services/orchestrator-dynamic/tests/integration/test_fluxo_g_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
# services/orchestrator-dynamic/tests/integration/test_fluxo_g_e2e.py
import pytest
import asyncio
from datetime import datetime
from httpx import AsyncClient

from orchestrator.clients.temporal_client import TemporalClient
from orchestrator.workflows.fluxo_g_workflow import FluxoGWorkflow


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fluxo_g_e2e_simple_pipeline(temporal_client: TemporalClient):
    """
    Teste E2E do Fluxo G sem aprovação.

    Executa: Requirements → Architecture → RAG → Documentation → Code
    """
    # Inicia workflow
    workflow_id = f"test-e2e-{datetime.utcnow().timestamp()}"

    result = await temporal_client.execute_workflow(
        FluxoGWorkflow.run,
        args={
            "intent_text": "Criar uma API simples de usuários com CRUD",
            "project_name": "user-api",
            "user_id": "test-user",
            "tech_stack": {
                "language": "python",
                "framework": "fastapi",
            },
            "require_approval": False,
        },
        id=workflow_id,
        task_queue="fluxo-g-task-queue",
    )

    # Verifica resultado
    assert result["success"] is True
    assert "requirements" in result
    assert "architecture" in result
    assert "documentation" in result
    assert "generated_code" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fluxo_g_e2e_with_approval(temporal_client: TemporalClient):
    """
    Teste E2E do Fluxo G com aprovação.

    Executa pipeline completo e testa sinal de aprovação.
    """
    workflow_id = f"test-e2e-approval-{datetime.utcnow().timestamp()}"

    # Inicia workflow com aprovação
    handle = await temporal_client.start_workflow(
        FluxoGWorkflow.run,
        args={
            "intent_text": "Criar serviço de autenticação",
            "project_name": "auth-service",
            "user_id": "test-user",
            "require_approval": True,
        },
        id=workflow_id,
        task_queue="fluxo-g-task-queue",
        memo={
            "approvers": ["architect@test.com"],
            "approval_completed": False,
            "approval_approved": False,
        },
    )

    # Aguarda até estar aguardando aprovação
    await asyncio.sleep(2)

    # Envia aprovação
    await handle.signal(FluxoGWorkflow.approve, approved=True, feedback="LGTM")

    # Aguarda conclusão
    result = await handle.result()

    assert result["success"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fluxo_g_e2e_rejection(temporal_client: TemporalClient):
    """
    Teste E2E do Fluxo G com rejeição.

    Verifica que pipeline é cancelado quando rejeitado.
    """
    workflow_id = f"test-e2e-reject-{datetime.utcnow().timestamp()}"

    handle = await temporal_client.start_workflow(
        FluxoGWorkflow.run,
        args={
            "intent_text": "Criar microserviço",
            "project_name": "microservice-test",
            "user_id": "test-user",
            "require_approval": True,
        },
        id=workflow_id,
        task_queue="fluxo-g-task-queue",
    )

    # Aguarda até estar aguardando aprovação
    await asyncio.sleep(2)

    # Envia rejeição
    await handle.signal(
        FluxoGWorkflow.approve,
        approved=False,
        feedback="Precisa de mais detalhes"
    )

    # Aguarda conclusão
    result = await handle.result()

    assert result["success"] is False
    assert result["reason"] == "Approval rejected"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fluxo_g_e2e_kafka_events(
    temporal_client: TemporalClient,
    kafka_consumer,
):
    """
    Teste E2E verificando eventos Kafka.
    """
    workflow_id = f"test-e2e-kafka-{datetime.utcnow().timestamp()}"

    # Inicia workflow
    handle = await temporal_client.start_workflow(
        FluxoGWorkflow.run,
        args={
            "intent_text": "API de produtos",
            "project_name": "product-api",
            "user_id": "test-user",
            "require_approval": False,
        },
        id=workflow_id,
        task_queue="fluxo-g-task-queue",
    )

    # Consome eventos Kafka
    events = []
    async for event in kafka_consumer("fluxo-g"):
        events.append(event)
        if len(events) >= 3:  # Intent, Requirements, Architecture
            break

    # Verifica eventos
    event_types = [e.get("event_type") for e in events]
    assert "intent.received" in event_types
    assert "requirements.generated" in event_types
    assert "architecture.generated" in event_types

    # Cancela workflow
    await handle.cancel()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fluxo_g_e2e_fallback_on_rag_failure(temporal_client: TemporalClient):
    """
    Teste E2E verificando fallback quando RAG falha.
    """
    # Simula falha do RAG (setando URL inválida)
    # Pipeline deve continuar com fallback templates

    workflow_id = f"test-e2e-fallback-{datetime.utcnow().timestamp()}"

    result = await temporal_client.execute_workflow(
        FluxoGWorkflow.run,
        args={
            "intent_text": "Sistema de pedidos",
            "project_name": "order-system",
            "user_id": "test-user",
            "require_approval": False,
        },
        id=workflow_id,
        task_queue="fluxo-g-task-queue",
    )

    # Pipeline deve completar mesmo com RAG em fallback
    assert result["success"] is True
```

- [ ] **Step 2: Create fixtures para testes**

```python
# services/orchestrator-dynamic/tests/conftest.py
import pytest
import asyncio
from temporalio.client import Client
from httpx import AsyncClient


@pytest.fixture
async def temporal_client():
    """Cliente Temporal para testes."""
    client = await Client.connect(
        "localhost:7233",
        namespace="default",
    )
    yield client
    await client.close()


@pytest.fixture
async def kafka_consumer():
    """Consumer Kafka para testes."""
    from aiokafka import AIOKafkaConsumer
    import json

    async def _consumer(topic_prefix: str):
        consumer = AIOKafkaConsumer(
            bootstrap_servers="localhost:9092",
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )

        # Subscribe em todos os tópicos do Fluxo G
        topics = [f"{topic_prefix}.{t}" for t in [
            "intent.received",
            "requirements.generated",
            "architecture.generated",
            "rag.results",
            "documentation.generated",
            "approval.completed",
            "code.generated",
            "pipeline.completed",
        ]]
        await consumer.subscribe(topics)

        async for message in consumer:
            yield message.value

        await consumer.stop()

    return _consumer


@pytest.fixture
def app():
    """Aplicação FastAPI para testes HTTP."""
    from main import app
    return app
```

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator-dynamic/tests/integration/test_fluxo_g_e2e.py \
        services/orchestrator-dynamic/tests/conftlex.py
git commit -m "test(orchestrator): add E2E integration tests for Fluxo G"
```

---

## Task 13: Criar Documentação de Deploy

**Files:**
- Create: `services/orchestrator-dynamic/docs/FLUXO_G_DEPLOY.md`
- Test: N/A

- [ ] **Step 1: Create documentation**

```markdown
# Fluxo G - Deployment Guide

**Versão:** 1.0
**Data:** 2026-04-16

---

## Visão Geral

Este guia descreve como fazer deploy da integração do Fluxo G no orchestrator-dynamic.

## Pré-requisitos

- Kubernetes cluster (v1.28+)
- Temporal Server (v1.22+)
- Kafka Cluster (v3.5+)
- MongoDB (v6.0+)
- Redis (v7.0+)
- Helm 3.x

---

## Passo 1: Criar Tópicos Kafka

```bash
# Aplica manifestos Kafka
kubectl apply -f infrastructure/kafka/topics/fluxo-g-topics.yaml

# Verifica tópicos criados
kubectl exec -it kafka-0 -n neural-hive-mind -- \
  kafka-topics --bootstrap-server localhost:9092 --list | grep fluxo-g
```

Tópicos esperados:
- `fluxo-g.intent.received`
- `fluxo-g.requirements.generated`
- `fluxo-g.architecture.generated`
- `fluxo-g.rag.queries`
- `fluxo-g.rag.results`
- `fluxo-g.documentation.generated`
- `fluxo-g.approval.requested`
- `fluxo-g.approval.completed`
- `fluxo-g.code.generated`
- `fluxo-g.pipeline.completed`
- `fluxo-g.pipeline.failed`
- DLTs para retry

---

## Passo 2: Criar ConfigMaps e Secrets

```bash
# ConfigMap
kubectl apply -f services/orchestrator-dynamic/deployments/fluxo-g/configmap.yaml

# Secrets (se ainda não existirem)
kubectl create secret generic mongodb-secret \
  --from-literal=connection-string='mongodb://user:pass@mongodb:27017/neural-hive-mind' \
  -n neural-hive-mind

kubectl create secret generic redis-secret \
  --from-literal=url='redis://:password@redis:6379/0' \
  -n neural-hive-mind
```

---

## Passo 3: Deploy do Orchestrator com Fluxo G

```bash
# Deployment da API e Worker
kubectl apply -f services/orchestrator-dynamic/deployments/fluxo-g/deployment.yaml

# Verifica status
kubectl rollout status deployment/orchestrator-dynamic-fluxog -n neural-hive-mind
kubectl rollout status deployment/orchestrator-fluxog-worker -n neural-hive-mind
```

---

## Passo 4: Verificar Deploy

```bash
# Verifica pods
kubectl get pods -n neural-hive-mind -l component=fluxo-g

# Verifica logs
kubectl logs -f deployment/orchestrator-dynamic-fluxog -n neural-hive-mind
kubectl logs -f deployment/orchestrator-fluxog-worker -n neural-hive-mind

# Verifica health
kubectl exec -it deployment/orchestrator-dynamic-fluxog -n neural-hive-mind -- \
  curl http://localhost:8003/health/ready
```

---

## Passo 5: Testar Integração

```bash
# Port-forward para teste local
kubectl port-forward -n neural-hive-mind svc/orchestrator-dynamic-fluxog 8003:8003

# Iniciar pipeline
curl -X POST http://localhost:8003/api/v1/fluxo-g/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "intent_text": "Criar uma API REST de produtos com autenticação JWT",
    "project_name": "product-api",
    "user_id": "user123",
    "tech_stack": {
      "language": "python",
      "framework": "fastapi",
      "database": "postgresql"
    },
    "require_approval": true
  }'

# Resposta esperada:
# {
#   "pipeline_id": "fluxo-g-1234567890",
#   "status": "running",
#   "message": "Pipeline iniciado com sucesso",
#   "current_stage": "requirements",
#   "progress": 0.0
# }
```

---

## Feature Flags

Configure behavior via environment variables:

| Variável | Default | Descrição |
|----------|---------|-----------|
| `FLUXO_G_ENABLE_REQUIREMENTS` | `true` | Habilita estágio de requirements |
| `FLUXO_G_ENABLE_ARCHITECTURE` | `true` | Habilita estágio de arquitetura |
| `FLUXO_G_ENABLE_RAG` | `true` | Habilita estágio RAG |
| `FLUXO_G_ENABLE_DOCUMENTATION` | `true` | Habilita estágio de documentação |
| `FLUXO_G_ENABLE_APPROVAL` | `true` | Habilita estágio de aprovação |
| `FLUXO_G_ENABLE_CODE_GENERATION` | `true` | Habilita estágio de geração de código |
| `FLUXO_G_RAG_ALPHA` | `0.7` | Balanceamento RAG (0=graph, 1=vector) |
| `FLUXO_G_RAG_TOP_K` | `5` | Número de resultados RAG |
| `FLUXO_G_STAGE_TIMEOUT` | `300` | Timeout por estágio (segundos) |
| `FLUXO_G_MAX_RETRIES` | `3` | Máximo de retries por estágio |

---

## Monitoramento

### Métricas Prometheus

```
# Taxa de pipelines iniciados
rate(fluxo_g_pipelines_started_total[5m])

# Taxa de pipelines completados
rate(fluxo_g_pipelines_completed_total[5m])

# Taxa de pipelines falhos
rate(fluxo_g_pipelines_failed_total[5m])

# Duração média do pipeline
histogram_quantile(0.95, fluxo_g_pipeline_duration_seconds)

# Status dos pipelines
count by (status) (fluxo_g_pipeline_status)
```

### Alerts Grafana

```yaml
# Alerta: alta taxa de falhas
- alert: FluxoGHighFailureRate
  expr: rate(fluxo_g_pipelines_failed_total[5m]) > 0.1
  for: 5m
  annotations:
    summary: "Alta taxa de falhas no Fluxo G"
```

---

## Troubleshooting

### Pipeline não inicia

1. Verificar se worker está rodando:
   ```bash
   kubectl logs -f deployment/orchestrator-fluxog-worker -n neural-hive-mind
   ```

2. Verificar task queue no Temporal UI:
   ```
   http://temporal-ui:8088/namespaces/default/task-queues/fluxo-g-task-queue
   ```

### Timeout em estágio

Ajustar `FLUXO_G_STAGE_TIMEOUT` na ConfigMap.

### RAG sempre usa fallback

Verificar conectividade com knowledge-graph-rag:
```bash
kubectl exec -it deployment/orchestrator-fluxog-worker -n neural-hive-mind -- \
  curl http://knowledge-graph-rag:8016/health
```

---

## Rollback

```bash
# Rollback deployment
kubectl rollout undo deployment/orchestrator-dynamic-fluxog -n neural-hive-mind
kubectl rollout undo deployment/orchestrator-fluxog-worker -n neural-hive-mind
```

---

## Escalabilidade

### Horizontal Scaling

```bash
# Escala workers (mais throughput de activities)
kubectl scale deployment/orchestrator-fluxog-worker --replicas=4 -n neural-hive-mind

# Escala API (mais throughput de requisições)
kubectl scale deployment/orchestrator-dynamic-fluxog --replicas=5 -n neural-hive-mind
```

### Vertical Scaling

Ajustar `resources.requests` e `resources.limits` no deployment.

---

## Segurança

1. **RBAC**: Criar ServiceAccount dedicado
2. **Network Policies**: Restringir acesso entre serviços
3. **Secrets**: Usar Kubernetes Secrets ou External Secrets Operator
4. **TLS**: Habilitar TLS em todos os endpoints

---

*Documentação atualizada em 2026-04-16*
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator-dynamic/docs/FLUXO_G_DEPLOY.md
git commit -m "docs(orchestrator): add Fluxo G deployment guide"
```

---

## Task 14: Atualizar Router Principal

**Files:**
- Modify: `services/orchestrator-dynamic/src/api/main.py`

- [ ] **Step 1: Adicionar router do Fluxo G**

```python
# services/orchestrator-dynamic/src/api/main.py

from fastapi import FastAPI
from contextlib import asynccontextmanager

from orchestrator.api.routers import health, workflows
from orchestrator.api.routers.fluxo_g import router as fluxo_g_router  # NOVO


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    from orchestrator.producers.fluxo_g_producer import FluxoGEventProducer

    producer = FluxoGEventProducer()
    await producer.start()

    yield

    # Shutdown
    await producer.stop()


app = FastAPI(
    title="Orchestrator Dynamic API",
    version="2.0.0",
    description="Orquestrador de workflows Neural-Hive-Mind com suporte ao Fluxo G",
    lifespan=lifespan,
)

# Routers
app.include_router(health.router, tags=["Health"])
app.include_router(workflows.router, prefix="/api/v1", tags=["Workflows"])
app.include_router(fluxo_g_router, prefix="/api/v1")  # NOVO


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "orchestrator-dynamic",
        "version": "2.0.0",
        "features": [
            "temporal_workflows",
            "fluxo_g_pipeline",
        ],
    }
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator-dynamic/src/api/main.py
git commit -m "feat(orchestrator): integrate Fluxo G router into main API"
```

---

## Task 15: Criar Diagrama de Arquitetura

**Files:**
- Create: `docs/diagrams/fluxo-g-architecture.mmd`

- [ ] **Step 1: Create Mermaid diagram**

```mermaid
{% raw %}
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#f3f9ff',
    'primaryTextColor': '#0d47a1',
    'primaryBorderColor': '#2196f3',
    'lineColor': '#42a5f5',
    'secondaryColor': '#f5f5f5',
    'tertiaryColor': '#fff'
  }
}}%%
graph TB
    subgraph "Camada de API"
        A[REST API<br/>FastAPI :8003]
    end

    subgraph "Camada de Orquestração"
        B[Temporal Workflow<br/>FluxoGWorkflow]
        W[Temporal Workers<br/>2+ pods]
    end

    subgraph "Serviços do Fluxo G"
        R[Requirements Engineering<br/>:8010]
        AR[Architect Agent<br/>:8008]
        K[Knowledge Graph RAG<br/>:8016]
        D[Documentation Generation<br/>:8014]
        AP[Approval Gateway<br/>:8017]
        C[Code Forge<br/>:8005]
    end

    subgraph "Event Streaming"
        KAF[(Kafka Cluster<br/>15 tópicos)]
    end

    subgraph "Persistência"
        M[(MongoDB<br/>pipeline state)]
        RED[(Redis<br/>cache)]
        NEO[(Neo4j<br/>knowledge graph)]
        QDR[(Qdrant<br/>vectors)]
    end

    A -->|HTTP| B
    B -.->|Activities| W
    W -->|HTTP/gRPC| R
    W -->|HTTP/gRPC| AR
    W -->|HTTP/gRPC| K
    W -->|HTTP/gRPC| D
    W -->|HTTP/gRPC| AP
    W -->|HTTP/gRPC| C

    R -->|read/write| M
    AR -->|read/write| M
    D -->|read/write| M
    AP -->|read/write| M

    K -->|query| NEO
    K -->|search| QDR

    W -->|publish| KAF
    W -->|read/write| RED

    style A fill:#e3f2fd
    style B fill:#fff3e0
    style W fill:#fff3e0
    style KAF fill:#f3e5f5
    style M fill:#e8f5e9
    style RED fill:#e8f5e9
    style NEO fill:#e8f5e9
    style QDR fill:#e8f5e9
{% endraw %}
```

- [ ] **Step 2: Commit**

```bash
git add docs/diagrams/fluxo-g-architecture.mmd
git commit -m "docs(architecture): add Fluxo G architecture diagram"
```

---

## Resumo do Plano

**15 tarefas** completando a **Fase 4: Orchestration Integration** do Fluxo G.

### Componentes Criados

1. **Kafka Topics**: 15 tópicos para eventos do pipeline
2. **Pipeline Model**: `FluxoGPipeline` com 7 estágios
3. **Temporal Activities**: 6 activities para integração com serviços
4. **Temporal Workflow**: `FluxoGWorkflow` orquestrando pipeline completo
5. **Kafka Producer**: `FluxoGEventProducer` para publicar eventos
6. **REST API**: Endpoints para iniciar/consultar/aprovar pipelines
7. **Pipeline Store**: Persistência em MongoDB
8. **Event Middleware**: Injeção automática de eventos
9. **Settings**: Feature flags e configurações
10. **Worker**: Worker Temporal dedicado
11. **Kubernetes**: Deployments para API e Worker
12. **E2E Tests**: Testes de integração completos
13. **Docs**: Guia de deployment
14. **Router Integration**: API principal atualizada
15. **Architecture Diagram**: Documentação visual

### Próximos Passos

**Fase 5: Testing & Hardening**
- Testes de carga
- Security hardening
- Performance tuning
- Final documentation

---

*Plano criado em 2026-04-16*
*Para uso com superpowers:subagent-driven-development*
