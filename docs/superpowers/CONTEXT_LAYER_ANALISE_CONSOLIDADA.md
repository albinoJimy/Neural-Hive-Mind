# Context Layer - Análise Consolidada para Excelência

> **Data:** 2026-04-23
> **Status:** Análise Executiva Consolidada (Revisada - Soluções Confiáveis)
> **Propósito:** Visão unificada para atingir excelência no Context Layer
>
> **Documentos Analisados:**
> - [Espec Original](./specs/2026-04-22-context-layer-deep-analysis.md)
> - [Análise Técnica Profunda](./context-layer-analise-tecnica-profunda.md)
> - [Código Prático](./context-layer-codigo-pratico.md)
> - [Guia de Implementação](./context-layer-guia-implementacao.md)

---

## Resumo Executivo

O **Context Layer** é o componente crítico que desbloqueia a diferenciação entre **Fluxo C** (Orchestration - modificar existente) e **Fluxo G** (Generation - criar novo). Actualmente, o Fluxo G **nunca é executado** devido a um gap crítico de implementação.

**Estado Actual:**
```
┌─────────────────────────────────────────────────────────────────┐
│  PROBLEMA CRÍTICO IDENTIFICADO                                  │
├─────────────────────────────────────────────────────────────────┤
│  decision_consumer.py:562-567                                   │
│  ❌ HARDCODED: OrchestrationWorkflow.run                         │
│  ❌ Ausente: workflow_type em CognitivePlan                      │
│  ❌ Ausente: Context Manager service                             │
│  ❌ Ausente: Roteamento confiável C↔G                            │
└─────────────────────────────────────────────────────────────────┘
```

**⚠️ AVISO CRÍTICO:** Heurísticas baseadas em keywords **NÃO são confiáveis** para roteamento (precisão ~60-70%). Este documento propõe apenas soluções validadas.

---

## Parte 1: Diagnóstico Consolidado

### 1.1 Gaps Críticos (P0) - Bloqueantes

| Gap | Local | Problema | Impacto |
|-----|-------|----------|---------|
| **GAP-1** | `decision_consumer.py:562` | Sempre executa `OrchestrationWorkflow` | Fluxo G nunca executa |
| **GAP-2** | `CognitivePlan` | Sem campo `workflow_type` | Impossível rotear |
| **GAP-3** | `context-manager/` | Service não existe | Sem contexto rico |

**Linha 562 do decision_consumer.py:**
```python
await self.temporal_client.start_workflow(
    OrchestrationWorkflow.run,  # ❌ HARDCODED - Bloqueia Fluxo G
    input_data,
    id=workflow_id,
    task_queue=self.config.temporal_task_queue,
)
```

### 1.2 Gaps Altos (P1) - Funcionalidade

| Gap | Componente | Ausente | Impacto |
|-----|-----------|---------|---------|
| **GAP-4** | SystemContext | Integração com Service Registry | Impossível verificar se domínio existe |
| **GAP-5** | PIIDetector | Detecção de PII | Compliance em risco |
| **GAP-6** | WorkflowClassifier | Classificação confiável | Roteamento por heurísticas falha |

### 1.3 Análise de Confiabilidade de Abordagens

| Abordagem | Precisão Real | Confiável? | Quando Usar |
|-----------|---------------|------------|-------------|
| **Keywords apenas** | 60-70% | ❌ NÃO | Nunca em produção |
| **Keywords + System Context** | 75-80% | ⚠️ Parcial | MVP com fallback humano |
| **Multi-sinal ponderado** | 80-85% | ✅ Sim | Produção com monitorização |
| **ML Classifier treinado** | 90-95% | ✅✅ Excelência | Com dataset validado |
| **Input humano explícito** | 95-99% | ✅✅✅ Ouro | Casos críticos/ambíguos |

---

## Parte 2: Arquitectura de Excelência

### 2.1 Visão Unificada (Revisada)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONTEXT LAYER - EXCELÊNCIA                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    RichContext (Modelo Unificado)                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ Intent   │ │ System   │ │ Temporal │ │ Security │ │ Routing  │  │  │
│  │  │ Context  │ │ Context  │ │ Context  │ │ Context  │ │ Decision │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                         │  │
│  │  │Conv.     │ │ Business │ │ Decision │                         │  │
│  │  │ Context  │ │ Context  │ │ Context  │                         │  │
│  │  └──────────┘ └──────────┘ └──────────┘                         │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │              WorkflowClassifier (Multi-Sinal Confiável)              │  │
│  │  Sinais Ponderados:                                                  │  │
│  │  1. System Context (domínio existe?) ──────── peso: 40%              │  │
│  │  2. Affected Services (vazio?) ─────────────── peso: 25%              │  │
│  │  3. User/Analyst Input ─────────────────────── peso: 20%              │  │
│  │  4. Semantic Analysis (NLP classifier) ────── peso: 10%              │  │
│  │  5. Conversational History ────────────────── peso: 5%               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ⚠️ Threshold de Confiança:                                                │
│     - confidence >= 0.85 → Auto-route                                     │
│     - 0.60 <= confidence < 0.85 → Flag para revisão                        │
│     - confidence < 0.60 → Requer input humano                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 WorkflowClassifier - Especificação Confiável

```python
# services/context-manager/src/services/workflow_classifier.py

from enum import Enum
from typing import tuple, Optional
import structlog

from neural_hive_context.models.context import RichContext, CognitivePlan
from neural_hive_context.models.workflow import WorkflowType

logger = structlog.get_logger(__name__)

class ConfidenceLevel(str, Enum):
    """Nível de confiança da classificação"""
    HIGH = "high"           # >= 0.85: Auto-route permitido
    MEDIUM = "medium"       # 0.60 - 0.85: Requer revisão
    LOW = "low"           # < 0.60: Requer input humano

class WorkflowClassifier:
    """
    Classificador de workflow baseado em multi-sinal ponderado.

    Precisão alvo: 80-85% (MVP) → 90-95% (com ML)
    """

    # Pesos dos sinais (total = 1.0)
    WEIGHT_SYSTEM_CONTEXT = 0.40    # Verificar se domínio existe
    WEIGHT_AFFECTED_SERVICES = 0.25  # Verificar services afectados
    WEIGHT_USER_INPUT = 0.20         # Input explícito do usuário
    WEIGHT_SEMANTIC = 0.10           # NLP classifier (quando disponível)
    WEIGHT_CONVERSATIONAL = 0.05     # Histórico da conversa

    # Thresholds
    THRESHOLD_AUTO_ROUTE = 0.85
    THRESHOLD_REQUIRES_REVIEW = 0.60

    def __init__(
        self,
        service_registry_client,  # Para verificar se domínio existe
        nlp_classifier=None,      # Opcional: ML classifier para semântica
    ):
        self.service_registry = service_registry_client
        self.nlp_classifier = nlp_classifier

    async def classify_workflow(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
    ) -> tuple[WorkflowType, float, ConfidenceLevel, str]:
        """
        Classifica o tipo de workflow baseado em múltiplos sinais.

        Returns:
            (workflow_type, confidence, confidence_level, reasoning)
        """

        scores = {
            WorkflowType.GENERATION: 0.0,
            WorkflowType.ORCHESTRATION: 0.0,
        }

        signals = []

        # ─────────────────────────────────────────────────────────────
        # SINAL 1: System Context (40%) - MAIS CONFIÁVEL
        # ─────────────────────────────────────────────────────────────
        system_score, system_reasoning = await self._analyze_system_context(context)
        scores[WorkflowType.GENERATION] += system_score * self.WEIGHT_SYSTEM_CONTEXT
        scores[WorkflowType.ORCHESTRATION] += (1.0 - system_score) * self.WEIGHT_SYSTEM_CONTEXT
        signals.append(system_reasoning)

        # ─────────────────────────────────────────────────────────────
        # SINAL 2: Affected Services (25%)
        # ─────────────────────────────────────────────────────────────
        services_score, services_reasoning = self._analyze_affected_services(cognitive_plan)
        scores[WorkflowType.GENERATION] += services_score * self.WEIGHT_AFFECTED_SERVICES
        scores[WorkflowType.ORCHESTRATION] += (1.0 - services_score) * self.WEIGHT_AFFECTED_SERVICES
        signals.append(services_reasoning)

        # ─────────────────────────────────────────────────────────────
        # SINAL 3: User Input (20%) - EXPLÍCITO
        # ─────────────────────────────────────────────────────────────
        user_score, user_reasoning = self._analyze_user_input(cognitive_plan, context)
        scores[WorkflowType.GENERATION] += user_score * self.WEIGHT_USER_INPUT
        scores[WorkflowType.ORCHESTRATION] += (1.0 - user_score) * self.WEIGHT_USER_INPUT
        signals.append(user_reasoning)

        # ─────────────────────────────────────────────────────────────
        # SINAL 4: Semantic Analysis (10%) - NLP CLASSIFIER
        # ─────────────────────────────────────────────────────────────
        if self.nlp_classifier:
            semantic_score, semantic_reasoning = await self._analyze_semantic_ml(context)
        else:
            # Fallback: análise básica SEM keywords (usa NLP library)
            semantic_score, semantic_reasoning = await self._analyze_semantic_basic(context)

        scores[WorkflowType.GENERATION] += semantic_score * self.WEIGHT_SEMANTIC
        scores[WorkflowType.ORCHESTRATION] += (1.0 - semantic_score) * self.WEIGHT_SEMANTIC
        signals.append(semantic_reasoning)

        # ─────────────────────────────────────────────────────────────
        # SINAL 5: Conversational History (5%)
        # ─────────────────────────────────────────────────────────────
        if context.conversational:
            conv_score, conv_reasoning = self._analyze_conversational(context)
            scores[WorkflowType.GENERATION] += conv_score * self.WEIGHT_CONVERSATIONAL
            scores[WorkflowType.ORCHESTRATION] += (1.0 - conv_score) * self.WEIGHT_CONVERSATIONAL
            signals.append(conv_reasoning)

        # ─────────────────────────────────────────────────────────────
        # DECISÃO FINAL
        # ─────────────────────────────────────────────────────────────
        generation_score = scores[WorkflowType.GENERATION]
        orchestration_score = scores[WorkflowType.ORCHESTRATION]

        if generation_score > orchestration_score:
            workflow_type = WorkflowType.GENERATION
            confidence = generation_score
        else:
            workflow_type = WorkflowType.ORCHESTRATION
            confidence = orchestration_score

        # Determinar nível de confiança
        if confidence >= self.THRESHOLD_AUTO_ROUTE:
            confidence_level = ConfidenceLevel.HIGH
        elif confidence >= self.THRESHOLD_REQUIRES_REVIEW:
            confidence_level = ConfidenceLevel.MEDIUM
        else:
            confidence_level = ConfidenceLevel.LOW

        reasoning = " | ".join(signals)

        logger.info(
            "Workflow classification complete",
            workflow_type=workflow_type,
            confidence=confidence,
            confidence_level=confidence_level,
            reasoning=reasoning,
        )

        return workflow_type, confidence, confidence_level, reasoning

    # ─────────────────────────────────────────────────────────────────
    # MÉTODOS DE ANÁLISE DE SINAIS
    # ─────────────────────────────────────────────────────────────────

    async def _analyze_system_context(
        self,
        context: RichContext,
    ) -> tuple[float, str]:
        """
        Analisa System Context para verificar se domínio alvo existe.

        Este é o SINAL MAIS CONFIÁVEL (40% do peso).

        Returns:
            (score_generation, reasoning)
            - score_generation = 1.0 se domínio NÃO existe (forte sinal de greenfield)
            - score_generation = 0.0 se domínio existe (sinal de orchestration)
            - score_generation = 0.5 se sem target_domain
        """
        if not context.intent.target_domain:
            return 0.5, "System: No target domain specified"

        domain_exists = context.intent.target_domain in context.system.active_services

        if not domain_exists:
            # Domínio NÃO existe → forte sinal de greenfield
            return (
                1.0,
                f"System: Domain '{context.intent.target_domain}' does NOT exist (strong greenfield signal)"
            )
        else:
            # Domínio existe → sinal de orchestration
            return (
                0.0,
                f"System: Domain '{context.intent.target_domain}' EXISTS (orchestration signal)"
            )

    def _analyze_affected_services(
        self,
        cognitive_plan: CognitivePlan,
    ) -> tuple[float, str]:
        """
        Analisa se há serviços afectados no plano.

        Returns:
            (score_generation, reasoning)
            - score_generation = 1.0 se SEM affected services (greenfield provável)
            - score_generation = 0.0 se COM affected services (orchestration provável)
        """
        if not cognitive_plan.tasks:
            return 0.5, "Services: No tasks in plan"

        affected_services = set()
        for task in cognitive_plan.tasks:
            if hasattr(task, "target_service") and task.target_service:
                affected_services.add(task.target_service)
            # Verificar também em parameters
            if task.parameters.get("target_service"):
                affected_services.add(task.parameters["target_service"])

        if not affected_services:
            return (
                1.0,
                "Services: No affected services identified (suggests greenfield)"
            )
        else:
            return (
                0.0,
                f"Services: {len(affected_services)} affected service(s) (suggests orchestration)"
            )

    def _analyze_user_input(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
    ) -> tuple[float, str]:
        """
        Analisa input explícito do usuário/analista.

        Este é o SINAL MAIS CONFIÁVEL após System Context.

        Returns:
            (score_generation, reasoning)
        """
        # Verificar se há indicação explícita no plano
        if cognitive_plan.workflow_type != WorkflowType.ORCHESTRATION:
            if cognitive_plan.workflow_type == WorkflowType.GENERATION:
                return (
                    1.0,
                    f"User: Explicit workflow_type=GENERATION (confidence: {cognitive_plan.workflow_confidence:.2f})"
                )
            return (
                0.0,
                f"User: Explicit workflow_type=ORCHESTRATION (confidence: {cognitive_plan.workflow_confidence:.2f})"
            )

        # Verificar se usuário indicou greenfield explicitamente
        if context.intent.is_greenfield:
            return (
                1.0,
                "User: Explicit is_greenfield=True in intent"
            )

        # Verificar metadados do plano
        if cognitive_plan.metadata.get("greenfield"):
            return (
                1.0,
                "User: greenfield=True in plan metadata"
            )

        return 0.5, "User: No explicit workflow indication"

    async def _analyze_semantic_ml(
        self,
        context: RichContext,
    ) -> tuple[float, str]:
        """
        Analisa semântica usando ML classifier treinado.

        Returns:
            (score_generation, reasoning)
        """
        try:
            result = await self.nlp_classifier.classify(
                text=context.intent.raw_intent,
                context=context.dict(),
            )

            if result.get("is_greenfield"):
                confidence = result.get("confidence", 0.5)
                return (
                    confidence,
                    f"Semantic: ML classifies as GREENFIELD (confidence: {confidence:.2f})"
                )
            else:
                confidence = result.get("confidence", 0.5)
                return (
                    1.0 - confidence,
                    f"Semantic: ML classifies as ORCHESTRATION (confidence: {confidence:.2f})"
                )
        except Exception as e:
            logger.warning("ML classifier failed, using fallback", error=str(e))
            return await self._analyze_semantic_basic(context)

    async def _analyze_semantic_basic(
        self,
        context: RichContext,
    ) -> tuple[float, str]:
        """
        Análise semântica básica SEM keywords (usa NLP library).

        ❌ NÃO usa keyword matching (não confiável)
        ✅ Usa spaCy/scikit-learn para análise estrutural
        """
        # TODO: Implementar análise estrutural com:
        # - POS tagging (verb patterns)
        # - Dependency parsing (object entities)
        # - Named Entity Recognition
        # Por ora, retorna neutro
        return 0.5, "Semantic: Basic analysis not yet implemented (neutral)"

    def _analyze_conversational(
        self,
        context: RichContext,
    ) -> tuple[float, str]:
        """
        Analisa histórico conversacional.

        Returns:
            (score_generation, reasoning)
        """
        if not context.conversational or not context.conversational.previous_intents:
            return 0.5, "Conversational: No history available"

        prev_intents = " ".join(context.conversational.previous_intents).lower()

        # Verificar se contexto menciona sistema existente
        existing_system_patterns = [
            "sistema existente",
            "já está",
            "está funcionando",
            "atualmente",
            "production",
        ]

        greenfield_patterns = [
            "novo sistema",
            "do zero",
            "greenfield",
            "from scratch",
        ]

        existing_score = sum(1 for p in existing_system_patterns if p in prev_intents)
        greenfield_score = sum(1 for p in greenfield_patterns if p in prev_intents)

        if existing_score > greenfield_score:
            return (
                0.0,
                f"Conversational: Mentions existing system ({existing_score} vs {greenfield_score})"
            )
        elif greenfield_score > existing_score:
            return (
                1.0,
                f"Conversational: Mentions greenfield ({greenfield_score} vs {existing_score})"
            )
        else:
            return 0.5, "Conversational: No clear pattern in history"
```

---

## Parte 3: Plano de Implementação Revisado

### 3.1 Fase 1: Foundation (Semana 1-2) - Non-Breaking

| Tarefa | Deliverable | Status |
|--------|-------------|--------|
| 1.1 | Criar `libraries/python/neural_hive_context/` | ⬜ |
| 1.2 | Definir modelos Pydantic (RichContext, etc.) | ⬜ |
| 1.3 | Criar cliente gRPC básico (mock inicial) | ⬜ |
| 1.4 | Criar service skeleton `context-manager/` | ⬜ |
| 1.5 | Testes unitários dos modelos | ⬜ |

### 3.2 Fase 2: CognitivePlan Extension (Semana 2-3) - Non-Breaking

| Tarefa | Deliverable | Risco |
|--------|-------------|-------|
| 2.1 | Adicionar `workflow_type`, `context_id` ao CognitivePlan | Baixo (defaults) |
| 2.2 | Update Avro schema (backward compatible) | Baixo |
| 2.3 | Testes de backward compatibility | Baixo |

**Código Non-Breaking:**
```python
# services/semantic-translation-engine/src/models/cognitive_plan.py

class WorkflowType(str, Enum):
    ORCHESTRATION = "orchestration"  # Fluxo C
    GENERATION = "generation"        # Fluxo G

class CognitivePlan(BaseModel):
    # ... campos existentes ...

    # ✅ NOVOS CAMPOS COM DEFAULTS (NON-BREAKING)
    workflow_type: WorkflowType = Field(
        default=WorkflowType.ORCHESTRATION,  # ← Mantém comportamento actual
        description="Tipo de workflow a executar"
    )
    context_id: Optional[str] = Field(None)
    workflow_confidence: float = Field(default=0.5)
    workflow_reasoning: Optional[str] = Field(None)
```

### 3.3 Fase 3: Decision Consumer Fix (Semana 3-4) - CRÍTICO

| Tarefa | Deliverable | Risco |
|--------|-------------|-------|
| 3.1 | Modificar `decision_consumer.py` para roteamento | Médio |
| 3.2 | Criar `FluxoGWorkflow` se não existir | Alto |
| 3.3 | Testes E2E (Fluxo C e G) | Alto |

**Código Crítico:**
```python
# services/orchestrator-dynamic/src/consumers/decision_consumer.py

async def process_decision(self, consolidated_decision: dict):
    # ... validações existentes ...

    # ✅ NOVO: Extrair workflow_type
    cognitive_plan_dict = consolidated_decision.get("cognitive_plan", {})
    workflow_type = cognitive_plan_dict.get("workflow_type", "orchestration")
    confidence = cognitive_plan_dict.get("workflow_confidence", 0.5)

    # ⚠️ VERIFICAR CONFIANÇA antes de rotear automaticamente
    if confidence < 0.60:
        logger.warning(
            "Low confidence routing - manual review required",
            workflow_type=workflow_type,
            confidence=confidence,
            plan_id=plan_id,
        )
        # TODO: Enviar para fila de revisão humana
        # Por ora, default para Orchestration (conservador)
        workflow_type = "orchestration"

    # ✅ Roteamento baseado em workflow_type validado
    if workflow_type == "generation":
        workflow_cls = FluxoGWorkflow
        logger.info("Routing to Fluxo G", plan_id=plan_id, confidence=confidence)
    else:
        workflow_cls = OrchestrationWorkflow
        logger.info("Routing to Fluxo C", plan_id=plan_id, confidence=confidence)

    await self.temporal_client.start_workflow(
        workflow_cls.run,
        input_data,
        id=workflow_id,
        task_queue=self.config.temporal_task_queue,
    )
```

### 3.4 Fase 4: WorkflowClassifier (Semana 4-6) - CRÍTICO

| Tarefa | Deliverable | Precisão Alvo |
|--------|-------------|---------------|
| 4.1 | Criar `WorkflowClassifier` multi-sinal | 80-85% |
| 4.2 | Service Registry integration (System Context) | N/A |
| 4.3 | Integração com Semantic Translation Engine | 80-85% |
| 4.4 | Testes de classificação | 80-85% |

**⚠️ NOTA:** Esta fase usa **multi-sinal ponderado**, não keywords. Precisão alvo realista: 80-85%.

### 3.5 Fase 5: PII Detector (Semana 6-7) - Compliance

| Tarefa | Deliverable | Precisão Alvo |
|--------|-------------|---------------|
| 5.1 | Criar `PIIDetector` com regex patterns | >95% |
| 5.2 | Integração no Gateway | >95% |
| 5.3 | Testes de detecção | >95% |

### 3.6 Fase 6: ML Classifier (Semana 7-10) - Excelência

| Tarefa | Deliverable | Precisão Alvo |
|--------|-------------|---------------|
| 6.1 | Colectar dataset de treino (intenção + label) | - |
| 6.2 | Treinar ML classifier (scikit-learn/transformers) | 90-95% |
| 6.3 | Integração no WorkflowClassifier | 90-95% |
| 6.4 | A/B testing vs multi-sinal | Validação |

**⚠️ NOTA:** ML classifier requer dataset de treino validado. Não assumir disponibilidade imediata.

### 3.7 Fase 7: Testing & Deploy (Semana 10-12)

| Tarefa | Deliverable | Status |
|--------|-------------|--------|
| 7.1 | Testes E2E completos (C e G) | ⬜ |
| 7.2 | Documentação de API | ⬜ |
| 7.3 | Performance testing | ⬜ |
| 7.4 | Deploy EKS | ⬜ |

---

## Parte 4: Critérios de Excelência (Revisados)

### 4.1 Critérios Técnicos

| Métrica | SLO | Estado Actual | Alvo Realista |
|---------|-----|---------------|---------------|
| **Latência de contexto** | <100ms p95 | N/A | 50ms p95 |
| **Precisão de routing (MVP)** | >80% | 0% | 80-85% (multi-sinal) |
| **Precisão de routing (Excelência)** | >90% | 0% | 90-95% (com ML) |
| **Detecção de PII** | >95% | 0% | 98% |
| **Disponibilidade** | >99.9% | N/A | 99.95% |
| **Throughput** | >100 req/s/pod | N/A | 200 req/s/pod |

### 4.2 Critérios Funcionais

| Funcionalidade | Estado Actual | Alvo | Abordagem Confiável |
|----------------|---------------|------|---------------------|
| **Roteamento C↔G** | ❌ Não implementado | ✅ Funcional | Multi-sinal + ML |
| **Contexto rico** | ❌ Parcial | ✅ Completo | System Context primeiro |
| **PII masking** | ❌ Ausente | ✅ Funcional | Regex validado |
| **Sessões** | ❌ Ausente | ✅ Funcional | MongoDB sessions |
| **Auditoria** | ❌ Parcial | ✅ Completa | Audit trail |

### 4.3 Critérios de Qualidade

| Critério | Definição | Como Medir | Alvo |
|----------|-----------|------------|------|
| **Completude** | % de dimensões preenchidas | `calculate_completeness()` | >80% |
| **Consistência** | Contexto mantém-se na cadeia | Tracing end-to-end | 100% |
| **Causalidade** | Capacidade de rastrear origem | `causality_chain` não vazio | >90% |
| **Explainabilidade** | Cada decision tem reasoning | `routing_decision` preenchido | 100% |

---

## Parte 5: Riscos e Mitigações (Revisado)

### 5.1 Riscos Técnicos

| Risco | Probabilidade | Impacto | Mitigação Confiável |
|-------|---------------|---------|-------------------|
| **Routing errors (G→C)** | Médio | Alto | Threshold de confiança + revisão humana |
| **Latência > 100ms** | Média | Médio | Cache Redis, lazy loading |
| **Context Manager unavailable** | Baixa | Alto | Fallback para ORCHESTRATION + alerta |
| **PII false positives** | Baixa | Alto | Whitelist de padrões, threshold |
| **ML model drift** | Média | Médio | Monitorização contínua, re-treino |

### 5.2 Riscos de Implementação

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| **Dataset ML insuficiente** | Alta | Alto | Multi-sinal como fallback |
| **Time overrun** | Média | Alto | MVP com multi-sinal primeiro |
| **Scope creep** | Média | Médio | Fases bem definidas |

---

## Parte 6: Abordagem Confiável - Resumo

### O que NÃO fazer (Anti-patterns):

❌ **Keywords apenas** para roteamento (precisão ~60-70%)
❌ Assumir que "criar" = greenfield (ambíguo)
❌ Routing sem threshold de confiança
❌ Ignorar System Context (domínio existe?)

### O que fazer (Padrões Confiáveis):

✅ **Multi-sinal ponderado** (precisão ~80-85%)
✅ **System Context primeiro** (40% do peso)
✅ **Threshold de confiança** + revisão humana
✅ **ML Classifier** quando dataset disponível (90-95%)
✅ **Input explícito** do usuário como sinal forte

### Matriz de Decisão:

```
Confidence >= 0.85 → Auto-route OK
Confidence 0.60-0.85 → Flag para revisão + continuar
Confidence < 0.60 → Requer input humano (pausa)
```

---

## Parte 7: Conclusão

### Resumo da Análise

O Context Layer é um **componente estratégico** que requer abordagem confiável:

1. **Fases 1-3 (3-4 semanas):** Foundation + CognitivePlan + Decision Consumer Fix
2. **Fase 4 (2-3 semanas):** WorkflowClassifier multi-sinal (80-85% precisão)
3. **Fase 5 (1-2 semanas):** PII Detector
4. **Fase 6 (3-4 semanas):** ML Classifier para excelência (90-95% precisão)

**Tempo Total Estimado:**
- **MVP Confiável (multi-sinal):** 10-11 semanas
- **Excelência (com ML):** 12-14 semanas

**Recomendação:** Executar Fases 1-4 primeiro (multi-sinal confiável), depois evoluir para ML quando dataset estiver disponível.

---

*Análise Consolidada para Excelência (Revisada com Soluções Confiáveis) - 2026-04-23*
