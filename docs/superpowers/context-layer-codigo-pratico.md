# Context Layer - Exemplos de Código Práticos

> **Data:** 2026-04-23
> **Propósito:** Exemplos concretos para implementação do Context Layer
> **Status:** Code Samples

---

## 1. Exemplo 1: Adicionar workflow_type ao CognitivePlan

### Localização
`services/semantic-translation-engine/src/models/cognitive_plan.py`

### Código Anterior
```python
class CognitivePlan(BaseModel):
    plan_id: str
    intent_id: str
    correlation_id: str | None
    trace_id: str | None
    tasks: list[TaskNode]
    risk_score: float
    requires_approval: bool
    is_destructive: bool
```

### Código Modificado (Non-Breaking)
```python
from enum import Enum
from typing import Optional

class WorkflowType(str, Enum):
    """Tipo de workflow a executar"""
    ORCHESTRATION = "orchestration"  # Fluxo C - modificar existente
    GENERATION = "generation"        # Fluxo G - criar novo

class CognitivePlan(BaseModel):
    # --- CAMPOS EXISTENTES ---
    plan_id: str
    intent_id: str
    correlation_id: str | None
    trace_id: str | None
    tasks: list[TaskNode]
    risk_score: float
    requires_approval: bool
    is_destructive: bool

    # --- NOVOS CAMPOS (NON-BREAKING COM DEFAULTS) ---
    workflow_type: WorkflowType = Field(
        default=WorkflowType.ORCHESTRATION,
        description="Tipo de workflow a executar (orchestration ou generation)"
    )
    context_id: Optional[str] = Field(
        None,
        description="ID do contexto rico associado a este plano"
    )
    workflow_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiança na classificação do tipo de workflow"
    )
    workflow_reasoning: Optional[str] = Field(
        None,
        description="Justificativa para o tipo de workflow escolhido"
    )
```

### Testes de Compatibilidade
```python
import pytest
from src.models.cognitive_plan import CognitivePlan, WorkflowType

def test_cognitive_plan_backward_compatibility():
    """Testa que planos antigos sem novos campos funcionam"""
    old_plan_data = {
        "plan_id": "plan-123",
        "intent_id": "intent-456",
        "correlation_id": "corr-789",
        "trace_id": "trace-012",
        "tasks": [],
        "risk_score": 0.7,
        "requires_approval": False,
        "is_destructive": False,
    }

    # ✅ Deve funcionar sem novos campos (defaults aplicados)
    plan = CognitivePlan(**old_plan_data)

    assert plan.workflow_type == WorkflowType.ORCHESTRATION
    assert plan.context_id is None
    assert plan.workflow_confidence == 0.5
    assert plan.workflow_reasoning is None

def test_cognitive_plan_with_new_fields():
    """Testa planos com novos campos preenchidos"""
    new_plan_data = {
        "plan_id": "plan-123",
        "intent_id": "intent-456",
        "correlation_id": "corr-789",
        "trace_id": "trace-012",
        "tasks": [],
        "risk_score": 0.7,
        "requires_approval": False,
        "is_destructive": False,
        # NOVOS CAMPOS
        "workflow_type": WorkflowType.GENERATION,
        "context_id": "ctx-abc",
        "workflow_confidence": 0.85,
        "workflow_reasoning": "Intent contains 'criar novo sistema' keyword",
    }

    plan = CognitivePlan(**new_plan_data)

    assert plan.workflow_type == WorkflowType.GENERATION
    assert plan.context_id == "ctx-abc"
    assert plan.workflow_confidence == 0.85
    assert "criar novo sistema" in plan.workflow_reasoning

def test_cognitive_plan_avro_serialization():
    """Testa serialização Avro com novos campos"""
    from src.models.cognitive_plan import CognitivePlan

    plan_data = {
        "plan_id": "plan-123",
        "intent_id": "intent-456",
        "tasks": [],
        "risk_score": 0.7,
        "requires_approval": False,
        "is_destructive": False,
        "workflow_type": WorkflowType.GENERATION,
    }

    plan = CognitivePlan(**plan_data)

    # ✅ Deve serializar para Avro com novos campos
    avro_dict = plan.to_avro_dict()

    assert avro_dict["workflowType"] == "GENERATION"
    assert avro_dict["workflowConfidence"] == 0.5  # Default
    assert avro_dict["contextId"] is None  # Default
```

---

## 2. Exemplo 2: Decision Consumer com Roteamento

### Localização
`services/orchestrator-dynamic/src/consumers/decision_consumer.py`

### Código Anterior (Hardcoded)
```python
async def process_decision(self, decision: ConsolidatedDecision):
    # ... validações ...

    # ❌ HARDCODED: Sempre usa OrchestrationWorkflow
    await self.temporal_client.start_workflow(
        OrchestrationWorkflow.run,  # ← HARDCODED
        {
            "cognitive_plan": decision.cognitive_plan,
            "consolidated_decision": decision.dict(),
        },
        id=decision.decision_id,
        task_queue=self.config.temporal_task_queue,
    )
```

### Código Modificado (Roteamento Inteligente)
```python
import structlog
from src.models.cognitive_plan import CognitivePlan, WorkflowType
from src.workflows.orchestration_workflow import OrchestrationWorkflow
from src.workflows.fluxo_g_workflow import FluxoGWorkflow

logger = structlog.get_logger(__name__)

class DecisionConsumer:
    def __init__(self, settings, temporal_client, context_manager_client=None):
        self.settings = settings
        self.temporal = temporal_client
        self.context_client = context_manager_client  # ✅ Opcional

    async def process_decision(self, decision: ConsolidatedDecision):
        """Processa decisão com roteamento inteligente baseado em workflow_type"""

        try:
            # ✅ Passo 1: Extrair CognitivePlan
            cognitive_plan = CognitivePlan(**decision.cognitive_plan)
            workflow_type = cognitive_plan.workflow_type

            logger.info(
                "Processing decision",
                decision_id=decision.decision_id,
                workflow_type=workflow_type,
                context_id=cognitive_plan.context_id,
            )

            # ✅ Passo 2: Roteamento inteligente
            if workflow_type == WorkflowType.GENERATION:
                workflow_cls = FluxoGWorkflow
                routing_reasoning = cognitive_plan.workflow_reasoning or "Generation workflow"
                logger.info(
                    "Routing to Fluxo G (generation workflow)",
                    decision_id=decision.decision_id,
                    context_id=cognitive_plan.context_id,
                    reasoning=routing_reasoning,
                )
            else:
                workflow_cls = OrchestrationWorkflow
                routing_reasoning = cognitive_plan.workflow_reasoning or "Orchestration workflow (default)"
                logger.info(
                    "Routing to Fluxo C (orchestration workflow)",
                    decision_id=decision.decision_id,
                )

            # ✅ Passo 3: Buscar contexto rico se disponível
            context_data = {}
            if cognitive_plan.context_id and self.context_client:
                try:
                    context = await self.context_client.get_context(cognitive_plan.context_id)
                    context_data = context.dict()
                    logger.info(
                        "Context fetched successfully",
                        decision_id=decision.decision_id,
                        context_id=cognitive_plan.context_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to fetch context (continuing without)",
                        decision_id=decision.decision_id,
                        context_id=cognitive_plan.context_id,
                        error=str(e),
                    )

            # ✅ Passo 4: Executar workflow correto
            workflow_input = {
                "cognitive_plan": cognitive_plan.dict(),
                "consolidated_decision": decision.dict(),
                "context": context_data,
                "routing": {
                    "workflow_type": workflow_type.value,
                    "reasoning": routing_reasoning,
                },
            }

            await self.temporal.start_workflow(
                workflow_cls.run,
                workflow_input,
                id=decision.decision_id,
                task_queue=self.settings.temporal_task_queue,
            )

            logger.info(
                "Workflow started successfully",
                decision_id=decision.decision_id,
                workflow_type=workflow_type,
            )

        except Exception as e:
            logger.exception(
                "Failed to process decision",
                decision_id=decision.decision_id,
                error=str(e),
            )
            # ✅ Publicar no DLQ ou tentar retry
            await self._publish_to_dlq(decision, error=str(e))

    async def _publish_to_dlq(self, decision: ConsolidatedDecision, error: str):
        """Publica decisão falha no DLQ"""
        # Implementação DLQ...
        pass
```

### Testes de Integração
```python
import pytest
from src.models.cognitive_plan import CognitivePlan, WorkflowType
from src.models.consolidated_decision import ConsolidatedDecision
from src.consumers.decision_consumer import DecisionConsumer

@pytest.mark.asyncio
async def test_decision_consumer_routes_to_fluxo_g():
    """Testa roteamento para Fluxo G quando workflow_type=GENERATION"""
    # Setup
    temporal_client = MockTemporalClient()
    context_client = MockContextManagerClient()
    consumer = DecisionConsumer(settings=temporal_settings, temporal_client=temporal_client, context_manager_client=context_client)

    # Criar decisão com workflow_type=GENERATION
    cognitive_plan = CognitivePlan(
        plan_id="plan-123",
        intent_id="intent-456",
        tasks=[],
        risk_score=0.7,
        requires_approval=False,
        is_destructive=False,
        workflow_type=WorkflowType.GENERATION,
        workflow_reasoning="Intent contains 'criar novo sistema'",
        context_id="ctx-abc",
    )

    decision = ConsolidatedDecision(
        decision_id="decision-789",
        plan_id="plan-123",
        intent_id="intent-456",
        cognitive_plan=cognitive_plan.dict(),
        final_decision="approved",
    )

    # Executar
    await consumer.process_decision(decision)

    # ✅ Verificar que FluxoGWorkflow foi invocado
    temporal_client.start_workflow.assert_called_once()
    call_args = temporal_client.start_workflow.call_args

    assert call_args[0][0].__name__ == "FluxoGWorkflow"  # Workflow classe
    assert call_args[1]["id"] == "decision-789"  # Workflow ID

@pytest.mark.asyncio
async def test_decision_consumer_routes_to_fluxo_c():
    """Testa roteamento para Fluxo C quando workflow_type=ORCHESTRATION"""
    # Setup
    temporal_client = MockTemporalClient()
    context_client = MockContextManagerClient()
    consumer = DecisionConsumer(settings=temporal_settings, temporal_client=temporal_client, context_manager_client=context_client)

    # Criar decisão com workflow_type=ORCHESTRATION (default)
    cognitive_plan = CognitivePlan(
        plan_id="plan-123",
        intent_id="intent-456",
        tasks=[],
        risk_score=0.7,
        requires_approval=False,
        is_destructive=False,
        # workflow_type não especificado → default=ORCHESTRATION
    )

    decision = ConsolidatedDecision(
        decision_id="decision-789",
        plan_id="plan-123",
        intent_id="intent-456",
        cognitive_plan=cognitive_plan.dict(),
        final_decision="approved",
    )

    # Executar
    await consumer.process_decision(decision)

    # ✅ Verificar que OrchestrationWorkflow foi invocado
    temporal_client.start_workflow.assert_called_once()
    call_args = temporal_client.start_workflow.call_args

    assert call_args[0][0].__name__ == "OrchestrationWorkflow"  # Workflow classe

@pytest.mark.asyncio
async def test_decision_consumer_fetches_context():
    """Testa que contexto rico é buscado quando context_id presente"""
    # Setup
    temporal_client = MockTemporalClient()
    context_client = MockContextManagerClient()
    consumer = DecisionConsumer(settings=temporal_settings, temporal_client=temporal_client, context_manager_client=context_client)

    # Mock contexto rico
    context_client.get_context.return_value = MockContext(
        context_id="ctx-abc",
        system=MockSystemContext(active_services=["service-1", "service-2"]),
        security=MockSecurityContext(user_id="user-123"),
    )

    # Criar decisão com context_id
    cognitive_plan = CognitivePlan(
        plan_id="plan-123",
        intent_id="intent-456",
        tasks=[],
        risk_score=0.7,
        requires_approval=False,
        is_destructive=False,
        workflow_type=WorkflowType.GENERATION,
        context_id="ctx-abc",
    )

    decision = ConsolidatedDecision(
        decision_id="decision-789",
        plan_id="plan-123",
        intent_id="intent-456",
        cognitive_plan=cognitive_plan.dict(),
        final_decision="approved",
    )

    # Executar
    await consumer.process_decision(decision)

    # ✅ Verificar que contexto foi buscado
    context_client.get_context.assert_called_once_with("ctx-abc")

    # ✅ Verificar que contexto foi passado para o workflow
    call_args = temporal_client.start_workflow.call_args
    workflow_input = call_args[1][0]
    assert "context" in workflow_input
    assert workflow_input["context"]["context_id"] == "ctx-abc"
```

---

## 3. Exemplo 3: Context Router Básico

### Localização
`services/context-manager/src/services/context_router.py`

### Implementação
```python
from typing import Tuple
from enum import Enum
import structlog

from src.models.cognitive_plan import CognitivePlan, WorkflowType
from src.models.rich_context import RichContext

logger = structlog.get_logger(__name__)

class ContextRouter:
    """Roteamento inteligente baseado em contexto rico"""

    # Keywords para cada tipo de workflow
    GENERATION_KEYWORDS = [
        "criar", "novo sistema", "desenvolver", "implementar",
        "greenfield", "do zero", "from scratch", "nova feature",
        "construir", "arquitetar", "build"
    ]

    ORCHESTRATION_KEYWORDS = [
        "executar", "processar", "calcular", "consultar",
        "buscar", "listar", "atualizar", "deletar",
        "modificar", "alterar", "mudar"
    ]

    async def route_workflow(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
    ) -> Tuple[WorkflowType, float, str]:
        """
        Decide qual workflow executar baseado em contexto.

        Returns:
            (workflow_type, confidence, reasoning)
        """
        # 1. Verificar indicação explícita no plano
        if cognitive_plan.workflow_type != WorkflowType.ORCHESTRATION:
            confidence = cognitive_plan.workflow_confidence or 0.7
            reasoning = cognitive_plan.workflow_reasoning or f"Explicit workflow type: {cognitive_plan.workflow_type}"
            return (
                cognitive_plan.workflow_type,
                confidence,
                reasoning,
            )

        # 2. Análise semântica da intenção
        workflow_type, confidence, reasoning = self._analyze_semantic_keywords(
            cognitive_plan, context
        )

        # 3. Verificar se domínio alvo existe no sistema
        if workflow_type == WorkflowType.ORCHESTRATION:
            workflow_type, confidence, reasoning = self._check_domain_exists(
                cognitive_plan, context, confidence, reasoning
            )

        # 4. Verificar contexto conversacional
        if workflow_type == WorkflowType.ORCHESTRATION:
            workflow_type, confidence, reasoning = self._check_conversational_context(
                cognitive_plan, context, confidence, reasoning
            )

        # 5. Análise de complexidade
        if workflow_type == WorkflowType.ORCHESTRATION:
            workflow_type, confidence, reasoning = self._check_complexity(
                cognitive_plan, context, confidence, reasoning
            )

        # 6. Verificar se há serviços afectados
        if workflow_type == WorkflowType.ORCHESTRATION:
            workflow_type, confidence, reasoning = self._check_affected_services(
                cognitive_plan, context, confidence, reasoning
            )

        # Default: Orchestration (comportamento conservador)
        if workflow_type is None:
            workflow_type = WorkflowType.ORCHESTRATION
            confidence = 0.5
            reasoning = "Default routing to orchestration (no strong signal for generation)"

        return workflow_type, confidence, reasoning

    def _analyze_semantic_keywords(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
    ) -> Tuple[WorkflowType, float, str]:
        """Analisa keywords para inferir tipo de workflow"""
        intent_lower = context.intent.raw_intent.lower()

        # Contar keywords de cada tipo
        gen_score = sum(1 for kw in self.GENERATION_KEYWORDS if kw in intent_lower)
        op_score = sum(1 for kw in self.ORCHESTRATION_KEYWORDS if kw in intent_lower)

        if gen_score > op_score:
            confidence = 0.7 + (gen_score * 0.05)  # Mínimo 0.7
            confidence = min(confidence, 0.95)  # Máximo 0.95
            reasoning = f"Semantic analysis: {gen_score} generation keywords vs {op_score} operation keywords"
            return WorkflowType.GENERATION, confidence, reasoning

        elif op_score > gen_score:
            confidence = 0.7 + (op_score * 0.05)
            confidence = min(confidence, 0.95)
            reasoning = f"Semantic analysis: {op_score} operation keywords vs {gen_score} generation keywords"
            return WorkflowType.ORCHESTRATION, confidence, reasoning

        else:
            # Empate → não determinístico por keywords
            return None, 0.0, "Semantic analysis inconclusive (equal keyword scores)"

    def _check_domain_exists(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
        current_confidence: float,
        current_reasoning: str,
    ) -> Tuple[WorkflowType, float, str]:
        """Verifica se domínio alvo existe no sistema"""
        if not context.intent.target_domain:
            return None, current_confidence, current_reasoning

        domain_exists = context.intent.target_domain in context.system.active_services

        if not domain_exists:
            confidence = max(current_confidence, 0.8)  # Strong signal
            reasoning = f"Target domain '{context.intent.target_domain}' does not exist in system (active_services: {context.system.active_services})"
            return WorkflowType.GENERATION, confidence, reasoning

        return None, current_confidence, current_reasoning

    def _check_conversational_context(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
        current_confidence: float,
        current_reasoning: str,
    ) -> Tuple[WorkflowType, float, str]:
        """Verifica contexto conversacional"""
        if not context.conversational:
            return None, current_confidence, current_reasoning

        prev_intents = " ".join(context.conversational.previous_intents)

        # Se context anterior menciona "sistema existente" ou similar
        if "sistema existente" in prev_intents or "já está" in prev_intents:
            confidence = max(current_confidence, 0.75)
            reasoning = "Conversational context indicates existing system operation"
            return WorkflowType.ORCHESTRATION, confidence, reasoning

        return None, current_confidence, current_reasoning

    def _check_complexity(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
        current_confidence: float,
        current_reasoning: str,
    ) -> Tuple[WorkflowType, float, str]:
        """Verifica complexidade estimada"""
        if not context.intent.estimated_complexity:
            return None, current_confidence, current_reasoning

        # Alta complexidade pode indicar criação de sistema novo
        if context.intent.estimated_complexity in ["high", "very_high"]:
            confidence = max(current_confidence, 0.6)
            reasoning = f"High complexity ({context.intent.estimated_complexity}) suggests system creation"
            return WorkflowType.GENERATION, confidence, reasoning

        return None, current_confidence, current_reasoning

    def _check_affected_services(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
        current_confidence: float,
        current_reasoning: str,
    ) -> Tuple[WorkflowType, float, str]:
        """Verifica se há serviços afectados"""
        if not cognitive_plan.tasks:
            return None, current_confidence, current_reasoning

        # Extrair serviços afectados das tarefas
        affected_services = set()
        for task in cognitive_plan.tasks:
            if hasattr(task, "target_service") and task.target_service:
                affected_services.add(task.target_service)

        # Sem serviços afectados → provavelmente greenfield
        if not affected_services:
            confidence = max(current_confidence, 0.65)
            reasoning = "No affected services identified, suggests greenfield"
            return WorkflowType.GENERATION, confidence, reasoning

        return None, current_confidence, current_reasoning
```

### Testes de Unidade
```python
import pytest
from src.models.cognitive_plan import CognitivePlan, WorkflowType
from src.models.rich_context import RichContext, IntentContext, SystemContext
from src.services.context_router import ContextRouter

@pytest.mark.asyncio
async def test_context_router_generation_keywords():
    """Testa roteamento para GENERATION com keywords de criação"""
    router = ContextRouter()

    # Criar contexto com intenção de geração
    intent_context = IntentContext(
        intent_type="create",
        raw_intent="Criar novo sistema de pagamentos do zero",
        normalized_intent="criar novo sistema de pagamentos do zero",
        confidence_score=0.85,
        target_domain="payments",
        is_greenfield=True,
    )

    system_context = SystemContext(
        active_services=[],  # Nenhum serviço activo → greenfield
    )

    context = RichContext(
        correlation_id="corr-123",
        intent_id="intent-456",
        intent=intent_context,
        system=system_context,
        security=MockSecurityContext(),
    )

    cognitive_plan = CognitivePlan(
        plan_id="plan-123",
        intent_id="intent-456",
        tasks=[],
        risk_score=0.7,
        requires_approval=False,
        is_destructive=False,
    )

    # Executar roteamento
    workflow_type, confidence, reasoning = await router.route_workflow(
        cognitive_plan, context
    )

    # ✅ Verificar resultado
    assert workflow_type == WorkflowType.GENERATION
    assert confidence >= 0.7
    assert "generation keywords" in reasoning.lower()

@pytest.mark.asyncio
async def test_context_router_orchestration_keywords():
    """Testa roteamento para ORCHESTRATION com keywords de operação"""
    router = ContextRouter()

    # Criar contexto com intenção de operação
    intent_context = IntentContext(
        intent_type="operate",
        raw_intent="Consultar dados de usuários ativos",
        normalized_intent="consultar dados de usuários ativos",
        confidence_score=0.90,
        target_domain="users",
        is_greenfield=False,
    )

    system_context = SystemContext(
        active_services=["users-service", "auth-service"],  # Serviço existe
    )

    context = RichContext(
        correlation_id="corr-123",
        intent_id="intent-456",
        intent=intent_context,
        system=system_context,
        security=MockSecurityContext(),
    )

    cognitive_plan = CognitivePlan(
        plan_id="plan-123",
        intent_id="intent-456",
        tasks=[],
        risk_score=0.3,
        requires_approval=False,
        is_destructive=False,
    )

    # Executar roteamento
    workflow_type, confidence, reasoning = await router.route_workflow(
        cognitive_plan, context
    )

    # ✅ Verificar resultado
    assert workflow_type == WorkflowType.ORCHESTRATION
    assert confidence >= 0.7
    assert "operation keywords" in reasoning.lower()

@pytest.mark.asyncio
async def test_context_router_domain_not_exists():
    """Testa roteamento para GENERATION quando domínio não existe"""
    router = ContextRouter()

    # Criar contexto onde domínio alvo não existe
    intent_context = IntentContext(
        intent_type="operate",
        raw_intent="Consultar dados de usuários",
        normalized_intent="consultar dados de usuários",
        confidence_score=0.85,
        target_domain="payments",  # ← Alvo
        is_greenfield=False,
    )

    system_context = SystemContext(
        active_services=["users-service", "auth-service"],  # ← payments não existe
    )

    context = RichContext(
        correlation_id="corr-123",
        intent_id="intent-456",
        intent=intent_context,
        system=system_context,
        security=MockSecurityContext(),
    )

    cognitive_plan = CognitivePlan(
        plan_id="plan-123",
        intent_id="intent-456",
        tasks=[],
        risk_score=0.5,
        requires_approval=False,
        is_destructive=False,
    )

    # Executar roteamento
    workflow_type, confidence, reasoning = await router.route_workflow(
        cognitive_plan, context
    )

    # ✅ Verificar resultado (deve ser GENERATION pois domínio não existe)
    assert workflow_type == WorkflowType.GENERATION
    assert confidence >= 0.8
    assert "does not exist" in reasoning.lower()
```

---

## 4. Exemplo 4: PII Detector Básico

### Localização
`services/context-manager/src/services/pii_detector.py`

### Implementação
```python
import re
from typing import List, Tuple
import structlog

logger = structlog.get_logger(__name__)

class PIIDetector:
    """Detecção de Informação Pessoalmente Identificável"""

    PII_PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE": r'\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})(?: *x(\d+))?\b',
        "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
        "CREDIT_CARD": r'\b(?:\d[ -]*?){13,16}\b',
        "IP_ADDRESS": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        "PASSPORT": r'\b[A-Z0-9<]{9}\b',
    }

    def __init__(self):
        # Compilar patterns regex para performance
        self.compiled_patterns = {
            entity_type: re.compile(pattern, re.IGNORECASE)
            for entity_type, pattern in self.PII_PATTERNS.items()
        }

    async def detect_pii(self, text: str) -> List[str]:
        """
        Detecta entidades PII no texto.

        Args:
            text: Texto a ser analisado

        Returns:
            Lista de tipos de PII detectados
        """
        if not text:
            return []

        detected = []

        for entity_type, pattern in self.compiled_patterns.items():
            if pattern.search(text):
                detected.append(entity_type)
                logger.debug(
                    "PII entity detected",
                    entity_type=entity_type,
                    text_preview=text[:100],
                )

        return detected

    async def mask_pii(self, text: str, entities: List[str]) -> Tuple[str, dict]:
        """
        Mascara entidades PII no texto.

        Args:
            text: Texto original
            entities: Lista de tipos de PII a mascarar

        Returns:
            (masked_text, mapping) onde mapping contém {placeholder: original_value}
        """
        if not text or not entities:
            return text, {}

        masked = text
        mapping = {}
        counter = 0

        for entity_type in entities:
            if entity_type not in self.compiled_patterns:
                logger.warning(f"Unknown PII entity type: {entity_type}")
                continue

            pattern = self.compiled_patterns[entity_type]
            matches = list(pattern.finditer(text))

            # Iterar em ordem inversa para manter índices corretos após substituição
            for match in reversed(matches):
                original = match.group()
                placeholder = f"[{entity_type}_{counter}]"
                masked = masked[:match.start()] + placeholder + masked[match.end():]
                mapping[placeholder] = original
                counter += 1

            logger.info(
                "PII entities masked",
                entity_type=entity_type,
                count=len(matches),
            )

        return masked, mapping

    async def validate_masking(self, original: str, masked: str, mapping: dict) -> bool:
        """
        Valida que masking removeu todas as entidades PII.

        Args:
            original: Texto original
            masked: Texto mascarado
            mapping: Mapeamento de placeholder → original

        Returns:
            True se masking válido, False caso contrário
        """
        # Verificar que todos os placeholders estão presentes
        for placeholder in mapping.keys():
            if placeholder not in masked:
                logger.error(
                    "PII masking validation failed",
                    placeholder=placeholder,
                    error="Placeholder not found in masked text",
                )
                return False

        # Verificar que nenhum PII original permanece
        for original_value in mapping.values():
            if original_value in masked:
                logger.error(
                    "PII masking validation failed",
                    original_value=original_value,
                    error="Original PII still present in masked text",
                )
                return False

        return True
```

### Testes de Unidade
```python
import pytest
from src.services.pii_detector import PIIDetector

@pytest.mark.asyncio
async def test_pii_detector_email():
    """Testa detecção de EMAIL"""
    detector = PIIDetector()
    text = "Contacte user@example.com para suporte"

    detected = await detector.detect_pii(text)

    assert "EMAIL" in detected
    assert len(detected) == 1

@pytest.mark.asyncio
async def test_pii_detector_phone():
    """Testa detecção de PHONE"""
    detector = PIIDetector()
    text = "Ligue para +1-555-123-4567 ou 555.123.4567"

    detected = await detector.detect_pii(text)

    assert "PHONE" in detected
    assert len(detected) == 1

@pytest.mark.asyncio
async def test_pii_detector_multiple_entities():
    """Testa detecção de múltiplos tipos de PII"""
    detector = PIIDetector()
    text = "User john@example.com, phone 555-123-4567, IP 192.168.1.1"

    detected = await detector.detect_pii(text)

    assert "EMAIL" in detected
    assert "PHONE" in detected
    assert "IP_ADDRESS" in detected
    assert len(detected) == 3

@pytest.mark.asyncio
async def test_pii_detector_no_pii():
    """Testa que texto sem PII retorna lista vazia"""
    detector = PIIDetector()
    text = "Este texto não contém informações pessoais"

    detected = await detector.detect_pii(text)

    assert len(detected) == 0

@pytest.mark.asyncio
async def test_pii_masking():
    """Testa masking de PII"""
    detector = PIIDetector()
    text = "Contacte user@example.com e user2@example.com"

    detected = await detector.detect_pii(text)
    masked, mapping = await detector.mask_pii(text, detected)

    # Verificar que emails foram mascarados
    assert "[EMAIL_0]" in masked
    assert "[EMAIL_1]" in masked
    assert "user@example.com" not in masked
    assert "user2@example.com" not in masked

    # Verificar mapping
    assert mapping["[EMAIL_0]"] == "user@example.com"
    assert mapping["[EMAIL_1]"] == "user2@example.com"

@pytest.mark.asyncio
async def test_pii_masking_validation():
    """Testa validação de masking"""
    detector = PIIDetector()
    text = "Email: user@example.com"

    detected = await detector.detect_pii(text)
    masked, mapping = await detector.mask_pii(text, detected)

    # Validar masking
    is_valid = await detector.validate_masking(text, masked, mapping)

    assert is_valid is True

@pytest.mark.asyncio
async def test_pii_masking_invalid():
    """Testa validação de masking inválido"""
    detector = PIIDetector()
    text = "Email: user@example.com"

    # Masking simulado com erro (placeholder ausente)
    masked = "Email: [EMAIL_0] - mas placeholder não substituído"
    mapping = {"[EMAIL_0]": "user@example.com"}

    # Validar masking (deve falhar)
    is_valid = await detector.validate_masking(text, masked, mapping)

    assert is_valid is False
```

---

*Exemplos de código práticos - 2026-04-23*
