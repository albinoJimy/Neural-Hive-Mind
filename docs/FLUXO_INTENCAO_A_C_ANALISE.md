# Análise Técnica Consolidada: Fluxo Completo de uma Intenção (A → C)

## Resumo Executivo

O Neural-Hive-Mind implementa um **pipeline inteligente de processamento de intenções** em três fluxos principais que transformam requisições de usuários em ações executáveis através de consenso multi-agente e orquestração distribuída.

| Fluxo | Responsabilidade | Serviços Principais | Latência Típica |
|-------|------------------|---------------------|-----------------|
| **A** | Captura e Classificação | Gateway Intenções | 200-500ms |
| **B** | Tradução Semântica e Consenso | STE, Consensus Engine, Specialists | 2-5s |
| **C** | Orquestração e Execução | Orchestrator Dynamic, Worker Agents | 30s-5min |

---

## Diagrama de Arquitetura Consolidado

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 FLUXO A - CAPTURA                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌─────────────┐      ┌────────────────────────────────────────────────────────┐   │
│   │   Cliente   │──────│              GATEWAY INTENÇÕES                          │   │
│   │  REST/Voice │      │  ┌─────────┐  ┌─────────┐  ┌────────────┐  ┌────────┐  │   │
│   └─────────────┘      │  │  Auth   │→ │ASR(voz) │→ │NLU Pipeline│→ │Producer│  │   │
│                        │  │Keycloak │  │Whisper  │  │   spaCy    │  │ Kafka  │  │   │
│                        │  └─────────┘  └─────────┘  └────────────┘  └───┬────┘  │   │
│                        └─────────────────────────────────────────────────│──────┘   │
│                                                                          │          │
│   Artefato: IntentEnvelope (Avro)                                       │          │
│   Tópicos: intentions.{business|technical|infrastructure|security}       │          │
└──────────────────────────────────────────────────────────────────────────┼──────────┘
                                                                           │
                                                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          FLUXO B - TRADUÇÃO E CONSENSO                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌────────────────────────────────────────────────────────────────────────────┐   │
│   │                    SEMANTIC TRANSLATION ENGINE                              │   │
│   │  ┌─────────────┐  ┌───────────────┐  ┌─────────────┐  ┌──────────────┐    │   │
│   │  │Intent       │→ │Semantic Parser│→ │DAG Generator│→ │Risk Scorer   │    │   │
│   │  │Consumer     │  │  + Neo4j      │  │ + NetworkX  │  │              │    │   │
│   │  └─────────────┘  └───────────────┘  └─────────────┘  └──────┬───────┘    │   │
│   │                                                               │            │   │
│   │  Artefato: CognitivePlan                                      │            │   │
│   │  Tópico: plans.ready                                          │            │   │
│   └───────────────────────────────────────────────────────────────┼────────────┘   │
│                                                                    │                │
│                                                                    ▼                │
│   ┌────────────────────────────────────────────────────────────────────────────┐   │
│   │                        CONSENSUS ENGINE                                     │   │
│   │                                                                             │   │
│   │  ┌─────────────┐      ┌───────────────────────────────────────────────┐   │   │
│   │  │Plan Consumer│─────→│        ESPECIALISTAS (gRPC paralelo)          │   │   │
│   │  └─────────────┘      │  ┌────────┐ ┌─────────┐ ┌────────┐ ┌────────┐│   │   │
│   │                       │  │Business│ │Technical│ │Behavior│ │Evolut. ││   │   │
│   │                       │  └───┬────┘ └────┬────┘ └───┬────┘ └───┬────┘│   │   │
│   │                       │      │           │          │          │     │   │   │
│   │                       │  ┌───┴───────────┴──────────┴──────────┴───┐ │   │   │
│   │                       │  │           Architecture                   │ │   │   │
│   │                       │  └─────────────────┬───────────────────────┘ │   │   │
│   │                       └────────────────────┼─────────────────────────┘   │   │
│   │                                            ▼                             │   │
│   │                       ┌────────────────────────────────────────────┐     │   │
│   │                       │      CONSENSUS ORCHESTRATOR                │     │   │
│   │                       │  ┌─────────────┐  ┌──────────────────┐    │     │   │
│   │                       │  │  Bayesian   │  │ Voting Ensemble  │    │     │   │
│   │                       │  │  Aggregator │  │   + Compliance   │    │     │   │
│   │                       │  └──────┬──────┘  └────────┬─────────┘    │     │   │
│   │                       │         └────────┬─────────┘              │     │   │
│   │                       └──────────────────┼────────────────────────┘     │   │
│   │                                          │                               │   │
│   │  Artefato: ConsolidatedDecision          │                               │   │
│   │  Tópico: plans.consensus                 │                               │   │
│   └──────────────────────────────────────────┼───────────────────────────────┘   │
└──────────────────────────────────────────────┼───────────────────────────────────┘
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           FLUXO C - ORQUESTRAÇÃO E EXECUÇÃO                         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌────────────────────────────────────────────────────────────────────────────┐   │
│   │                      ORCHESTRATOR DYNAMIC                                   │   │
│   │                                                                             │   │
│   │  ┌────────────────┐    ┌─────────────────────────────────────────────────┐│   │
│   │  │Decision        │───→│         TEMPORAL WORKFLOW (C1-C6)               ││   │
│   │  │Consumer        │    │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐    ││   │
│   │  └────────────────┘    │  │ C1 │→│ C2 │→│ C3 │→│ C4 │→│ C5 │→│ C6 │    ││   │
│   │                        │  │Val.│ │Gen │ │Allo│ │Pub │ │Cons│ │Tel │    ││   │
│   │                        │  │+OPA│ │Tick│ │Res │ │Tick│ │Res │ │    │    ││   │
│   │                        │  └────┘ └────┘ └────┘ └─┬──┘ └────┘ └────┘    ││   │
│   │                        └────────────────────────┼───────────────────────┘│   │
│   │                                                 │                        │   │
│   │  Artefato: ExecutionTicket                      │                        │   │
│   │  Tópico: execution.tickets                      │                        │   │
│   └─────────────────────────────────────────────────┼────────────────────────┘   │
│                                                      │                           │
│                                                      ▼                           │
│   ┌────────────────────────────────────────────────────────────────────────────┐ │
│   │                         WORKER AGENTS                                      │ │
│   │  ┌──────────────┐    ┌───────────────────────────────────────────────┐   │ │
│   │  │Ticket        │───→│            EXECUTION ENGINE                    │   │ │
│   │  │Consumer      │    │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │   │ │
│   │  └──────────────┘    │  │ BUILD  │ │ DEPLOY │ │  TEST  │ │VALIDATE│ │   │ │
│   │                      │  │Executor│ │Executor│ │Executor│ │Executor│ │   │ │
│   │                      │  └────────┘ └────────┘ └────────┘ └────────┘ │   │ │
│   │                      └────────────────────────────┬──────────────────┘   │ │
│   │                                                   │                      │ │
│   │  Artefato: ExecutionResult                        │                      │ │
│   │  Tópico: execution.results                        │                      │ │
│   └───────────────────────────────────────────────────┼──────────────────────┘ │
└───────────────────────────────────────────────────────┼────────────────────────┘
                                                        │
                                                        ▼
                                              ┌───────────────────┐
                                              │   FEEDBACK LOOP   │
                                              │  (ML Learning)    │
                                              │  Neo4j + MongoDB  │
                                              └───────────────────┘
```

---

## 1. FLUXO A - GATEWAY DE INTENÇÕES

### 1.1 Visão Geral

O Fluxo A é a **camada de experiência** do Neural-Hive-Mind, responsável por:
- Receber intenções via REST API (texto ou áudio)
- Autenticar e autorizar usuários via Keycloak
- Processar linguagem natural (NLU) para classificação
- Publicar intenções enriquecidas no Kafka

### 1.2 Endpoints REST

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/intentions` | POST | Processa intenção textual |
| `/intentions/voice` | POST | Processa intenção por áudio (Whisper) |
| `/health` | GET | Health check do serviço |
| `/ready` | GET | Readiness probe para Kubernetes |
| `/metrics` | GET | Métricas Prometheus |

### 1.3 Pipeline de Processamento

```
Requisição HTTP
      │
      ▼
┌─────────────────┐
│ 1. Autenticação │  JWT via Keycloak
│    (OAuth2)     │  Extração de user_context
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Deduplicação │  Redis: verifica correlation_id
│    (Redis)      │  TTL: 5 minutos
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. ASR Pipeline │  Whisper (se áudio)
│    (Whisper)    │  Modelos: tiny → large
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. NLU Pipeline │  spaCy + regras customizadas
│    (spaCy)      │  Classificação de domínio
│                 │  Extração de entidades
│                 │  Cálculo de confiança
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. Roteamento   │  confidence >= 0.5 → domínio
│    por Confiança│  confidence < 0.3 → validação
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. Kafka        │  Serialização Avro
│    Producer     │  Exactly-once semantics
└─────────────────┘
```

### 1.4 Domínios de Classificação

| Domínio | Keywords | Padrões | Exemplo |
|---------|----------|---------|---------|
| **BUSINESS** | vendas, relatório, cliente, faturamento | `/\b(vendas|faturamento|roi)\b/` | "Gerar relatório de vendas" |
| **TECHNICAL** | API, bug, erro, performance, código | `/\b(api|bug|erro|debug)\b/` | "Corrigir bug na API REST" |
| **INFRASTRUCTURE** | deploy, kubernetes, servidor, pipeline | `/\b(deploy|k8s|ci\/cd)\b/` | "Fazer deploy em produção" |
| **SECURITY** | autenticação, criptografia, vulnerabilidade | `/\b(oauth|jwt|ssl|auth)\b/` | "Implementar OAuth2" |

### 1.5 Estrutura IntentEnvelope

```json
{
  "id": "uuid-v4",
  "version": "1.0.0",
  "correlationId": "uuid-para-rastreamento",
  "traceId": "opentelemetry-trace-id",
  "spanId": "opentelemetry-span-id",
  "actor": {
    "id": "user-id",
    "actorType": "HUMAN|SYSTEM|SERVICE|BOT",
    "name": "Nome do Usuário"
  },
  "intent": {
    "text": "Texto original da intenção",
    "domain": "BUSINESS|TECHNICAL|INFRASTRUCTURE|SECURITY",
    "classification": "subcategoria",
    "originalLanguage": "pt-BR",
    "processedText": "Texto processado/normalizado",
    "entities": [
      {
        "entityType": "PERSON|ORG|PRODUCT|...",
        "value": "valor extraído",
        "confidence": 0.95,
        "start": 10,
        "end": 25
      }
    ],
    "keywords": ["keyword1", "keyword2"]
  },
  "confidence": 0.87,
  "context": {
    "sessionId": "session-uuid",
    "userId": "user-id",
    "tenantId": "tenant-id",
    "channel": "WEB|MOBILE|API|VOICE|CHAT",
    "userAgent": "curl/7.68.0",
    "clientIp": "192.168.1.100"
  },
  "constraints": {
    "priority": "LOW|NORMAL|HIGH|CRITICAL",
    "deadline": 1701878400000,
    "maxRetries": 3,
    "timeoutMs": 30000,
    "securityLevel": "PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED"
  },
  "qos": {
    "deliveryMode": "EXACTLY_ONCE",
    "durability": "PERSISTENT",
    "consistency": "STRONG"
  },
  "timestamp": 1701792000000,
  "schemaVersion": 1,
  "metadata": {}
}
```

### 1.6 Tópicos Kafka - Fluxo A

| Tópico | Partições | Retenção | Uso |
|--------|-----------|----------|-----|
| `intentions.business` | 6 | 7 dias | Intenções de negócio |
| `intentions.technical` | 8 | 7 dias | Intenções técnicas |
| `intentions.infrastructure` | 6 | 14 dias | Intenções de infra |
| `intentions.security` | 4 | 30 dias | Intenções de segurança |
| `intentions.validation` | 3 | 30 dias | Baixa confiança |
| `dlq.intentions.*` | 3 | 30 dias | Dead Letter Queue |

### 1.7 Métricas Prometheus - Fluxo A

```
# Requisições
neural_hive_requests_total{component, layer, domain, channel, status}

# Latência
neural_hive_captura_duration_seconds{component, layer, domain, channel}

# Confiança
neural_hive_intent_confidence{component, layer, domain, channel}

# Roteamento baixa confiança
neural_hive_low_confidence_routed_total{component, layer, domain, channel, route_target}
```

---

## 2. FLUXO B - TRADUÇÃO SEMÂNTICA

### 2.1 Visão Geral

O Fluxo B é a **camada cognitiva** do Neural-Hive-Mind, dividido em duas fases:

**Fase B1: Semantic Translation Engine (STE)**
- Enriquece intenções com contexto histórico (Neo4j)
- Decompõe em DAG de tarefas executáveis
- Avalia risco e complexidade

**Fase B2: Consensus Engine**
- Consulta 5 especialistas em paralelo (gRPC)
- Agrega opiniões via Bayesian Model Averaging
- Decide aprovação/rejeição via Voting Ensemble

### 2.2 Semantic Translation Engine

#### Pipeline de Processamento

```
IntentEnvelope (Kafka)
         │
         ▼
┌─────────────────────┐
│ B1: Validação       │  Campos obrigatórios
│                     │  Confidence >= 0.5
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ B2: Enriquecimento  │  Neo4j: histórico similar
│     Semântico       │  MongoDB: contexto operacional
│                     │  Redis: cache 5 min
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ B3: Decomposição    │  Extração de objetivos
│     em DAG          │  Geração de TaskNodes
│                     │  Ordem topológica (NetworkX)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ B4: Avaliação       │  Cálculo de risk_score
│     de Risco        │  Classificação em bands
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ B5: Versionamento   │  Append ao ledger MongoDB
│     e Ledger        │  Hash SHA-256
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ B6: Publicação      │  Kafka: plans.ready
│                     │  Avro serialization
└─────────────────────┘
```

#### Risk Bands

| Band | Score Range | Max Retries | Delivery Mode |
|------|-------------|-------------|---------------|
| LOW | 0.0 - 0.3 | 1 | AT_LEAST_ONCE |
| MEDIUM | 0.3 - 0.6 | 2 | AT_LEAST_ONCE |
| HIGH | 0.6 - 0.95 | 3 | EXACTLY_ONCE |
| CRITICAL | 0.95 - 1.0 | 5 | EXACTLY_ONCE |

### 2.3 Consensus Engine

#### Arquitetura de Consenso

```
CognitivePlan (Kafka)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                 INVOCAÇÃO PARALELA (gRPC)               │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────┐ │
│  │ Business  │ │ Technical │ │ Behavior  │ │Evolution│ │
│  │ Specialist│ │ Specialist│ │ Specialist│ │Specialist│ │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └────┬────┘ │
│        │             │             │            │       │
│        └─────────────┴─────────────┴────────────┘       │
│                          │                               │
│                 ┌────────┴────────┐                     │
│                 │   Architecture  │                     │
│                 │   Specialist    │                     │
│                 └────────┬────────┘                     │
└──────────────────────────┼──────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  CONSENSUS ORCHESTRATOR │
              │                        │
              │  1. Pesos Dinâmicos    │  Redis: feromônios
              │     (Feromônios)       │
              │                        │
              │  2. Bayesian Model     │  Agregação de confiança
              │     Averaging          │  e risco
              │                        │
              │  3. Voting Ensemble    │  Voto ponderado
              │                        │
              │  4. Compliance Check   │  Guardrails
              │                        │
              │  5. Decisão Final      │  APPROVE|REJECT|REVIEW
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  ConsolidatedDecision  │
              │  Kafka: plans.consensus│
              └────────────────────────┘
```

#### Especialistas

| Especialista | Responsabilidade | Peso Base |
|--------------|------------------|-----------|
| **Business** | Viabilidade comercial, ROI, impacto | 0.25 |
| **Technical** | Viabilidade técnica, complexidade | 0.25 |
| **Behavior** | Conformidade comportamental, UX | 0.20 |
| **Evolution** | Potencial de evolução, roadmap | 0.15 |
| **Architecture** | Alinhamento arquitetural, padrões | 0.15 |

#### Algoritmo Bayesian

```python
# Agregação de Confiança
posterior_mean = α × prior + (1-α) × Σ(specialist_confidence × weight)

# Onde:
# α = prior_weight (default: 0.1)
# prior = 0.5 (Beta(1,1) uniforme)

# Divergência
divergence = std(confidences) / aggregated_confidence
# < 0.2: Alta convergência
# > 0.6: Alta divergência (requer revisão)
```

### 2.4 Estrutura CognitivePlan

```json
{
  "plan_id": "uuid-v4",
  "version": "1.0.0",
  "intent_id": "referência-intent",
  "correlation_id": "uuid-rastreamento",
  "tasks": [
    {
      "task_id": "uuid-task",
      "task_type": "create|update|query|validate|transform",
      "description": "Descrição da tarefa",
      "dependencies": ["task-id-anterior"],
      "estimated_duration_ms": 1000,
      "required_capabilities": ["write", "read"],
      "parameters": {},
      "metadata": {}
    }
  ],
  "execution_order": ["task-1", "task-2", "task-3"],
  "risk_score": 0.63,
  "risk_band": "medium",
  "risk_factors": {
    "priority": 0.4,
    "security_level": 0.3,
    "complexity": 0.2
  },
  "explainability_token": "exp-token-abc",
  "reasoning_summary": "Justificativa em linguagem natural",
  "status": "validated",
  "created_at": 1701792000000,
  "valid_until": 1701878400000,
  "complexity_score": 0.4,
  "original_domain": "business",
  "original_priority": "high",
  "original_security_level": "internal",
  "metadata": {},
  "schema_version": 1
}
```

### 2.5 Estrutura ConsolidatedDecision

```json
{
  "decision_id": "uuid-v4",
  "plan_id": "referência-plan",
  "intent_id": "referência-intent",
  "correlation_id": "uuid-rastreamento",
  "final_decision": "approve|reject|review_required|conditional",
  "consensus_method": "bayesian|voting|unanimous|fallback",
  "aggregated_confidence": 0.82,
  "aggregated_risk": 0.42,
  "specialist_votes": [
    {
      "specialist_type": "business",
      "opinion_id": "uuid-opinion",
      "confidence_score": 0.88,
      "risk_score": 0.35,
      "recommendation": "approve",
      "weight": 0.25,
      "processing_time_ms": 450
    }
  ],
  "consensus_metrics": {
    "divergence_score": 0.12,
    "convergence_time_ms": 2500,
    "unanimous": false,
    "fallback_used": false,
    "pheromone_strength": 0.85,
    "bayesian_confidence": 0.82,
    "voting_confidence": 0.85
  },
  "explainability_token": "exp-token-decision",
  "reasoning_summary": "Resumo da decisão",
  "compliance_checks": {
    "security": true,
    "business_rules": true,
    "sla": true
  },
  "guardrails_triggered": [],
  "cognitive_plan": "{JSON serializado}",
  "requires_human_review": false,
  "created_at": 1701792000000,
  "valid_until": 1701878400000,
  "hash": "sha256-hash",
  "schema_version": 1
}
```

---

## 3. FLUXO C - ORQUESTRAÇÃO E EXECUÇÃO

### 3.1 Visão Geral

O Fluxo C é a **camada de execução** do Neural-Hive-Mind, implementado com Temporal.io para workflows resilientes:

**Orchestrator Dynamic**: Coordena workflows C1-C6
**Worker Agents**: Executam tickets individuais

### 3.2 Fases do Workflow Temporal

```
ConsolidatedDecision (Kafka)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                    TEMPORAL WORKFLOW                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ C1: VALIDAÇÃO DE PLANO                             │ │
│  │     - Campos obrigatórios                          │ │
│  │     - Validação DAG                                │ │
│  │     - Políticas OPA (se habilitado)                │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ C2: GERAÇÃO DE TICKETS                             │ │
│  │     - Task → ExecutionTicket                       │ │
│  │     - Mapeamento de dependências                   │ │
│  │     - Cálculo de SLA (deadline, timeout)           │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ C3: ALOCAÇÃO DE RECURSOS                           │ │
│  │     - IntelligentScheduler                         │ │
│  │     - ML-enhanced scheduling                       │ │
│  │     - Service Registry discovery                   │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ C4: PUBLICAÇÃO DE TICKETS                          │ │
│  │     - Kafka: execution.tickets                     │ │
│  │     - Avro serialization                           │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ C5: CONSOLIDAÇÃO DE RESULTADOS                     │ │
│  │     - Aguarda conclusão de tickets                 │ │
│  │     - Valida consistência                          │ │
│  │     - Aciona self-healing se necessário            │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ C6: PUBLICAÇÃO DE TELEMETRIA                       │ │
│  │     - Métricas de execução                         │ │
│  │     - Feedback loop ML                             │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Worker Agents - Execução

```
ExecutionTicket (Kafka)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                     WORKER AGENT                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ KafkaTicketConsumer                                │ │
│  │     - Deserializa Avro                             │ │
│  │     - Valida schema                                │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ ExecutionEngine                                    │ │
│  │     - Semaphore: controle de concorrência          │ │
│  │     - DependencyCoordinator: aguarda deps          │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ Task Executors                                     │ │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐  │ │
│  │  │ BUILD  │ │ DEPLOY │ │  TEST  │ │  VALIDATE  │  │ │
│  │  └────────┘ └────────┘ └────────┘ └────────────┘  │ │
│  │  ┌────────┐ ┌────────────┐                        │ │
│  │  │EXECUTE │ │ COMPENSATE │                        │ │
│  │  └────────┘ └────────────┘                        │ │
│  └──────────────────────┬─────────────────────────────┘ │
│                         │                                │
│  ┌──────────────────────▼─────────────────────────────┐ │
│  │ KafkaResultProducer                                │ │
│  │     - Publica ExecutionResult                      │ │
│  │     - Kafka: execution.results                     │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 3.4 Estrutura ExecutionTicket

```json
{
  "ticket_id": "uuid-v4",
  "plan_id": "referência-plan",
  "intent_id": "referência-intent",
  "decision_id": "referência-decision",
  "correlation_id": "uuid-rastreamento",
  "task_id": "referência-task",
  "task_type": "BUILD|DEPLOY|TEST|VALIDATE|EXECUTE|COMPENSATE",
  "description": "Descrição da tarefa",
  "dependencies": ["ticket-id-anterior"],
  "status": "PENDING|RUNNING|COMPLETED|FAILED|COMPENSATING|COMPENSATED",
  "priority": "LOW|NORMAL|HIGH|CRITICAL",
  "risk_band": "low|medium|high|critical",
  "sla": {
    "deadline": 1701878400000,
    "timeout_ms": 45000,
    "max_retries": 3
  },
  "qos": {
    "delivery_mode": "EXACTLY_ONCE",
    "consistency": "STRONG",
    "durability": "PERSISTENT"
  },
  "parameters": {},
  "required_capabilities": ["write", "deploy"],
  "security_level": "INTERNAL",
  "created_at": 1701792000000,
  "started_at": null,
  "completed_at": null,
  "estimated_duration_ms": 30000,
  "actual_duration_ms": null,
  "retry_count": 0,
  "error_message": null,
  "compensation_ticket_id": null,
  "allocation_metadata": {
    "agent_id": "worker-agent-1",
    "agent_type": "dedicated",
    "predicted_queue_ms": 150,
    "predicted_load_pct": 65.2,
    "ml_enriched": true
  },
  "metadata": {},
  "schema_version": 1
}
```

### 3.5 Validação de Políticas OPA

```rego
# Política de Limites de Recursos
package orchestration.resource_limits

default allow = false

allow {
    input.ticket.priority != "CRITICAL"
    count(input.active_tickets) < 100
    input.ticket.estimated_duration_ms < 600000  # 10 min
}

deny[msg] {
    count(input.active_tickets) >= 100
    msg := "Limite máximo de tickets concorrentes atingido"
}

# Política de Enforcement de SLA
package orchestration.sla_enforcement

allow {
    input.ticket.sla.deadline > now_ns() / 1000000
    remaining_ms := input.ticket.sla.deadline - (now_ns() / 1000000)
    remaining_ms > input.ticket.estimated_duration_ms * 1.5
}
```

---

## 4. MAPA DE INTEGRAÇÕES

### 4.1 Tópicos Kafka

| Tópico | Producer | Consumer | Schema Avro |
|--------|----------|----------|-------------|
| `intentions.business` | Gateway | STE | IntentEnvelope |
| `intentions.technical` | Gateway | STE | IntentEnvelope |
| `intentions.infrastructure` | Gateway | STE | IntentEnvelope |
| `intentions.security` | Gateway | STE | IntentEnvelope |
| `intentions.validation` | Gateway | (humano) | IntentEnvelope |
| `plans.ready` | STE | Consensus Engine | CognitivePlan |
| `plans.consensus` | Consensus Engine | Orchestrator | ConsolidatedDecision |
| `execution.tickets` | Orchestrator | Worker Agents | ExecutionTicket |
| `execution.results` | Worker Agents | Orchestrator | ExecutionResult |

### 4.2 Serviços gRPC

| Serviço | Endpoint | Chamado por |
|---------|----------|-------------|
| specialist-business | `:50051` | Consensus Engine |
| specialist-technical | `:50051` | Consensus Engine |
| specialist-behavior | `:50051` | Consensus Engine |
| specialist-evolution | `:50051` | Consensus Engine |
| specialist-architecture | `:50051` | Consensus Engine |
| service-registry | `:50051` | Orchestrator, Workers |

### 4.3 MongoDB Collections

| Database | Collection | Usado por |
|----------|------------|-----------|
| neural_hive | `cognitive_ledger` | STE, Orchestrator |
| neural_hive | `consensus_decisions` | Consensus Engine |
| neural_hive | `specialist_opinions` | Consensus Engine |
| neural_hive | `execution_tickets` | Orchestrator |
| neural_hive | `workflows` | Orchestrator |

### 4.4 Redis (Cluster)

| Uso | TTL | Serviço |
|-----|-----|---------|
| Dedup intenções | 5 min | Gateway |
| Cache NLU | 1h | Gateway |
| Cache Ontologia | 1h | STE |
| Feromônios especialistas | 1h | Consensus Engine |
| Service Registry cache | 5 min | Orchestrator |

### 4.5 Neo4j

| Nó/Relação | Uso |
|------------|-----|
| `Intent` | Histórico de intenções |
| `Entity` | Entidades extraídas |
| `Ontology` | Ontologia de tipos |
| `CAUSES`, `DEPENDS_ON` | Dependências causais |

---

## 5. FLUXO DE RASTREAMENTO DISTRIBUÍDO

### 5.1 Propagação de correlation_id

```
correlation_id: "corr-12345"
│
├── Fluxo A (Gateway)
│   trace_id: trace-001
│   spans: auth → nlu_pipeline → kafka_produce
│   duration: ~500ms
│
├── Fluxo B (STE + Consensus)
│   trace_id: trace-002
│   spans: consume → parse → dag_gen → risk → produce
│   spans: plan_consume → specialists_parallel → consensus
│   duration: ~3s
│
├── Fluxo C (Orchestrator + Workers)
│   trace_id: trace-003
│   spans: decision_consume → C1-C6 activities
│   spans: ticket_consume → execute → result_produce
│   duration: ~30s-5min
│
└── Total E2E: ~35s-6min
```

### 5.2 Headers Kafka para Rastreamento

```
intent-id: uuid
correlation-id: uuid
trace-id: opentelemetry-trace
span-id: opentelemetry-span
content-type: application/avro
schema-version: 1.0.0
confidence-score: 0.87
timestamp: epoch-ms
```

---

## 6. OBSERVABILIDADE

### 6.1 Métricas por Fluxo

#### Fluxo A
```
neural_hive_requests_total{component, layer, domain, channel, status}
neural_hive_captura_duration_seconds{component, layer, domain, channel}
neural_hive_intent_confidence{component, layer, domain, channel}
neural_hive_low_confidence_routed_total{...}
```

#### Fluxo B
```
semantic_translation_plans_generated_total{channel, status}
semantic_translation_geracao_duration_seconds{channel}
consensus_decisions_total{decision_type, consensus_method}
consensus_convergence_time_ms{consensus_method}
specialist_response_time_ms{specialist_type}
consensus_divergence_score{consensus_method}
```

#### Fluxo C
```
orchestration_workflows_started_total{status, risk_band}
orchestration_workflows_completed_total{status, risk_band}
orchestration_workflow_duration_seconds{status, risk_band}
orchestration_tickets_generated_total{task_type, risk_band, priority}
orchestration_tickets_completed_total{status, task_type}
orchestration_sla_violations_total{risk_band, task_type}
ml_scheduling_predictions_total{model_type, outcome}
ml_prediction_errors_total{model_type}
```

### 6.2 Health Checks

| Serviço | Endpoint | Componentes Verificados |
|---------|----------|-------------------------|
| Gateway | `/health`, `/ready` | Redis, Kafka, NLU |
| STE | `/health`, `/ready` | Kafka, Neo4j, MongoDB |
| Consensus | `/health`, `/ready` | Kafka, Specialists, MongoDB |
| Orchestrator | `/health`, `/ready` | Kafka, Temporal, MongoDB, OPA |
| Workers | `/health`, `/ready` | Kafka, Executors |

---

## 7. TRATAMENTO DE ERROS E RESILIÊNCIA

### 7.1 Circuit Breakers

| Serviço | Trigger | Ação |
|---------|---------|------|
| Gateway → Kafka | 5 erros consecutivos | Abre circuit, retorna 503 |
| STE → Neo4j | 3 timeouts | Fallback: sem histórico |
| Consensus → Specialist | 2 timeouts | Continua com N-1 especialistas |
| Orchestrator → MongoDB | 5 erros | Abre circuit, para consumo |

### 7.2 Retry Policies

| Operação | Max Attempts | Backoff |
|----------|--------------|---------|
| Kafka produce | 5 | Exponential 2^n |
| gRPC specialist | 3 | Fixed 500ms |
| MongoDB write | 3 | Exponential |
| Temporal activity | Configurável por task | Exponential |

### 7.3 Dead Letter Queues

| Tópico Original | DLQ |
|-----------------|-----|
| intentions.* | dlq.intentions.* |
| plans.ready | dlq.plans.ready |
| plans.consensus | dlq.plans.consensus |
| execution.tickets | dlq.execution.tickets |

---

## 8. EXEMPLO DE FLUXO COMPLETO

### Entrada
```json
{
  "text": "Criar novo microserviço de pagamentos e fazer deploy em produção",
  "language": "pt-BR",
  "correlation_id": "demo-12345",
  "constraints": {
    "priority": "high",
    "security_level": "restricted"
  }
}
```

### Fluxo A - Gateway
```
1. Autenticação: JWT validado
2. NLU: domain=infrastructure, confidence=0.89
3. Entidades: [microserviço, pagamentos, produção]
4. Kafka: intentions.infrastructure
```

### Fluxo B - STE
```
1. Enriquecimento: 3 intenções similares encontradas
2. DAG: 4 tasks geradas
   - task-1: CREATE_SERVICE
   - task-2: CONFIGURE_CI_CD (dep: task-1)
   - task-3: DEPLOY_STAGING (dep: task-2)
   - task-4: DEPLOY_PRODUCTION (dep: task-3)
3. Risk: score=0.72, band=HIGH
4. Kafka: plans.ready
```

### Fluxo B - Consensus
```
1. Especialistas:
   - Business: approve (0.88)
   - Technical: approve (0.82)
   - Behavior: conditional (0.75)
   - Evolution: approve (0.78)
   - Architecture: approve (0.85)
2. Bayesian: confidence=0.82, risk=0.42
3. Voting: approve (0.85)
4. Decisão: APPROVE
5. Kafka: plans.consensus
```

### Fluxo C - Orchestrator
```
1. C1: Validação OK
2. C2: 4 tickets gerados
3. C3: Workers alocados via ML scheduler
4. C4: Tickets publicados
5. Execução:
   - ticket-1: COMPLETED (28s)
   - ticket-2: COMPLETED (15s)
   - ticket-3: COMPLETED (45s)
   - ticket-4: COMPLETED (60s)
6. C5: Consolidação OK
7. C6: Telemetria publicada
```

### Saída
```json
{
  "workflow_id": "orch-plan-123",
  "status": "success",
  "total_duration_ms": 148000,
  "tickets_completed": 4,
  "sla_met": true
}
```

---

## 9. REFERÊNCIAS DE CÓDIGO

### Arquivos Principais por Fluxo

#### Fluxo A
- [services/gateway-intencoes/src/main.py](services/gateway-intencoes/src/main.py)
- [services/gateway-intencoes/src/pipelines/nlu_pipeline.py](services/gateway-intencoes/src/pipelines/nlu_pipeline.py)
- [services/gateway-intencoes/src/kafka/producer.py](services/gateway-intencoes/src/kafka/producer.py)

#### Fluxo B
- [services/semantic-translation-engine/src/services/orchestrator.py](services/semantic-translation-engine/src/services/orchestrator.py)
- [services/semantic-translation-engine/src/services/semantic_parser.py](services/semantic-translation-engine/src/services/semantic_parser.py)
- [services/consensus-engine/src/services/consensus_orchestrator.py](services/consensus-engine/src/services/consensus_orchestrator.py)

#### Fluxo C
- [services/orchestrator-dynamic/src/workflows/orchestration_workflow.py](services/orchestrator-dynamic/src/workflows/orchestration_workflow.py)
- [services/orchestrator-dynamic/src/activities/ticket_generation.py](services/orchestrator-dynamic/src/activities/ticket_generation.py)
- [services/worker-agents/src/engine/execution_engine.py](services/worker-agents/src/engine/execution_engine.py)

### Schemas Avro
- [schemas/intent-envelope/intent-envelope.avsc](schemas/intent-envelope/intent-envelope.avsc)
- [schemas/cognitive-plan/cognitive-plan.avsc](schemas/cognitive-plan/cognitive-plan.avsc)
- [schemas/consolidated-decision/consolidated-decision.avsc](schemas/consolidated-decision/consolidated-decision.avsc)
- [schemas/execution-ticket/execution-ticket.avsc](schemas/execution-ticket/execution-ticket.avsc)

---

## 10. GLOSSÁRIO

| Termo | Definição |
|-------|-----------|
| **IntentEnvelope** | Estrutura que encapsula uma intenção do usuário com metadados |
| **CognitivePlan** | Plano de execução gerado a partir de uma intenção |
| **ConsolidatedDecision** | Decisão final após consenso dos especialistas |
| **ExecutionTicket** | Unidade atômica de trabalho para execução |
| **Risk Band** | Classificação de risco (LOW, MEDIUM, HIGH, CRITICAL) |
| **Bayesian Model Averaging** | Técnica de agregação de opiniões com pesos |
| **Voting Ensemble** | Votação ponderada para decisão final |
| **Feromônios** | Pesos dinâmicos baseados em histórico de performance |
| **DAG** | Directed Acyclic Graph - grafo de dependências de tarefas |
| **STE** | Semantic Translation Engine |
| **OPA** | Open Policy Agent - validação de políticas |

---

*Documento gerado com base na análise completa do código-fonte do Neural-Hive-Mind*
*Versão: 1.0.0*
*Data: 2025-12-06*
