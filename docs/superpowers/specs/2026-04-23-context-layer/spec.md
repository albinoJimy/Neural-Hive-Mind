# Context Layer - Spec Document

> Spec: Context Layer para Neural Hive Mind
> Created: 2026-04-23
> Status: Implementation

---

## Overview

Implementar **Context Layer** para Neural Hive Mind, resolvendo o bloqueio crítico do Fluxo G (Generation), que nunca é executado devido ao `decision_consumer.py` estar hardcoded para `OrchestrationWorkflow`.

**Problema Crítico Identificado:**
- `decision_consumer.py` (lines 560-570) sempre executa `OrchestrationWorkflow`
- `CognitivePlan` não possui campo `workflow_type`
- Fluxo G (Generation) nunca é executado

**Solução:**
1. **WorkflowClassifier multi-sinal** (80-85% precisão)
2. **RichContext** com múltiplas dimensões
3. **PII Detector** para dados sensíveis
4. **Active Learning** para coleta de dataset ML (90-95% precisão futura)

---

## User Stories

### US-1: Routing Inteligente
Como **sistema Neural Hive Mind**, quero **rotear intents para o workflow correto** (Orchestration vs Generation), para que **capacidades de geração sejam executadas quando apropriado**.

**Workflow:**
1. Usuário envia intent via Gateway
2. STE adiciona `workflow_type` ao `CognitivePlan` (via classificação)
3. Decision Consumer roteia baseado no `workflow_type`
4. Workflow apropriado é executado

### US-2: Detecção de Dados Sensíveis
Como **especialista humano**, quero **ser alertado sobre dados sensíveis (PII)**, para que **posso aprovar/rejeitar com consciência do risco**.

**Workflow:**
1. Intent contém potencial PII (email, CPF, cartão)
2. PII Detector classifica risco
3. High/Critical risk favorece Orchestration (aprovação humana)
4. Dados são mascarados nos logs

### US-3: Aprendizado Contínuo
Como **engenheiro de ML**, quero **coletar feedback estruturado**, para que **modelo ML possa ser treinado para 90-95% precisão**.

**Workflow:**
1. Sistema classifica incertamente (confiança < 0.65)
2. Active Learning prioriza para revisão humana
3. Especialista rotula corretamente
4. Dataset cresce balanceado

---

## Spec Scope

1. **CognitivePlan Extension** - Campo `workflow_type` com default non-breaking
2. **Decision Consumer Fix** - Lógica de routing baseada em `workflow_type`
3. **WorkflowClassifier Multi-Sinal** - 5 sinais ponderados
4. **neural_hive_context Library** - Models e interfaces compartilhadas
5. **PII Detector** - Detecção de 12 tipos de dados sensíveis
6. **Context Manager Service** - Construção de RichContext
7. **Active Learning System** - Coleta de dataset ML

### Out of Scope

- ML Classifier treinado (requer dataset coletado)
- Integração com NLPFeatureGenerator (features semânticas)
- Dashboard UI para revisão de amostras
- Auto-retrain do modelo
- Multi-idioma suporte

---

## Expected Deliverable

1. **Fluxo G executando** - intents de geração são roteados corretamente
2. **Cobertura de testes** > 80% para novos componentes
3. **Performance p95 < 50ms** para classificação de workflow
4. **Dataset com 100+ amostras** coletadas via Active Learning
5. **Documentação completa** - APIs, schemas, deploy

---

## Architecture Overview

```
                    ┌─────────────────────────────────────────┐
                    │         Gateway (intenção recebida)      │
                    └─────────────────┬───────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │     Semantic Translation Engine          │
                    │  (CognitivePlan com workflow_type)       │
                    └─────────────────┬───────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │         Context Manager Service          │
                    │  - RichContext construction              │
                    │  - PII Detection                         │
                    │  - Workflow Classification               │
                    └─────────────────┬───────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │           Orchestrator Dynamic           │
                    │  Decision Consumer (routing logic)       │
                    └───────┬───────────────────────┬─────────┘
                            │                       │
                ┌───────────▼───────┐   ┌──────────▼──────────┐
                │ Orchestration WF  │   │   Generation WF     │
                │ (aprovação, etc)  │   │   (criação, geração)│
                └───────────────────┘   └─────────────────────┘
```

---

## Implementation Epics

### Epic 1: Foundation Library (3-5 dias)
- Criar skeleton `neural_hive_context`
- Models base: RichContext, WorkflowType, PIIEntity
- Interfaces: IWorkflowClassifier, IPIIDetector, IContextBuilder

### Epic 2: Routing Foundation (5-7 dias)
- CognitivePlan extension (workflow_type field)
- MultiSignalWorkflowClassifier implementation
- Decision Consumer fix (routing logic)
- Avro schema update (backward compatible)

### Epic 3: PII Detector (4-6 dias)
- PIIDetector core (12 tipos)
- Risk level calculation
- Masking logic
- Integration with WorkflowClassifier

### Epic 4: Context Manager Service (7-10 dias)
- ContextBuilder (RichContext aggregation)
- SystemContextCollector (Service Registry integration)
- API REST endpoints
- Cache strategies (Redis)

### Epic 5: Active Learning System (8-10 dias)
- UncertaintySampler, DiversitySampler
- BalanceAnalyzer
- API REST (samples, labeling)
- Kafka consumer for feedback
- FeatureExtractor

### Epic 6: Integration & Deploy (3-4 dias)
- E2E integration tests
- K8s deployment manifests
- Monitoring & observability
- Documentation

---

## Performance Requirements

| Operação | Target p95 | Target p99 | Max |
|----------|-----------|-----------|-----|
| WorkflowClassifier.classify() | 20ms | 40ms | 100ms |
| PIIDetector.detect() | 15ms | 30ms | 50ms |
| ContextBuilder.build() | 50ms | 100ms | 200ms |
| Context Manager POST /build | 80ms | 150ms | 300ms |

---

## Critical Contracts

### WorkflowClassifier Interface
```python
class IWorkflowClassifier(ABC):
    @abstractmethod
    async def classify(self, context: RichContext) -> WorkflowClassification:
        """
        Returns:
            WorkflowClassification com:
            - workflow_type: ORCHESTRATION | GENERATION
            - confidence: 0.0 a 1.0
            - reasoning: Explicação da decisão
            - signals: Sinais extraídos e seus pesos
        """
        pass
```

### PIIDetector Interface
```python
class IPIIDetector(ABC):
    @abstractmethod
    def detect(self, text: str) -> PIIResult:
        """
        Returns:
            PIIResult com:
            - has_pii: Bool
            - entities: Lista de PIIEntity
            - masked_text: Texto mascarado
            - risk_level: none | low | medium | high | critical
        """
        pass
```

---

## Deploy Checklist

### Pré-deploy
- [ ] Todos os testes passando (unit + integration)
- [ ] Coverage > 80%
- [ ] Performance targets atingidos
- [ ] Schemas Avro atualizados
- [ ] MongoDB indexes criados
- [ ] Redis cache configurado

### Deploy Steps
1. Build images com tags SHA-specific
2. Deploy neural_hive_context library
3. Deploy context-manager
4. Deploy active-learning
5. Atualizar semantic-translation-engine
6. Atualizar orchestrator-dynamic
7. Rolling update dos serviços dependentes

### Post-deploy Validation
- [ ] Verificar pods healthy
- [ ] Testar Generation workflow
- [ ] Testar PII detection
- [ ] Verificar Active Learning collecting
- [ ] Checar métricas Prometheus

---

## Success Criteria

1. **Funcional**: Generation workflow é executado para intents apropriadas
2. **Performance**: Classificação < 50ms p95
3. **Qualidade**: Cobertura de testes > 80%
4. **Dados**: 100+ amostras coletadas em 2 semanas
5. **Confiabilidade**: 80-85% precisão no routing (multi-sinal)

---

*Spec criado em 2026-04-23*
*Estimativa total: 24-33 dias (4-5 semanas)*
