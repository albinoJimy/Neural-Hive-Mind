# Ciclo de Vida Completo de uma Intenção - Neural-Hive-Mind

**Versão:** 1.0.0
**Data:** 2026-04-19
**Status:** Final

## Índice

1. [Visão Geral dos Tipos de Intenção](#visão-geral-dos-tipos-de-intenção)
2. [Fluxo 1: Intenção Simples](#fluxo-1-intenção-simples)
3. [Fluxo 2: Intenção Novo do Zero](#fluxo-2-intenção-novo-do-zero)
4. [Fluxo 3: Intenção de Refatoração](#fluxo-3-intenção-de-refatoração)
5. [Matriz de Decisão](#matriz-de-decisão)
6. [State Machine](#estados-de-uma-intenção)

---

## Visão Geral dos Tipos de Intenção

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    TIPOS DE INTENÇÃO NO NEURAL HIVE MIND                            │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────┐     │
│  │  1. INTENÇÃO SIMPLES                                                         │     │
│  │     "Buscar usuários ativos"                                                │     │
│  │     "Listar pedidos da última semana"                                       │     │
│  │     "Criar novo registro de cliente"                                        │     │
│  │                                                                              │     │
│  │     CARACTERÍSTICAS:                                                         │     │
│  │     - Requer only Query (leitura)                                           │     │
│  │     - Baixa complexidade (1-2 especialistas)                                │     │
│  │     - Sem aprovação humana (auto-approve)                                   │     │
│  │     - Execução imediata                                                    │     │
│  │     - Threshold: confiança > 0.8 → auto-executa                             │     │
│  └────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────┐     │
│  │  2. INTENÇÃO NOVO DO ZERO (GREENFIELD)                                      │     │
│  │     "Criar sistema completo de autenticação"                                │     │
│  │     "Implementar API de pagamentos com Stripe"                              │     │
│  │     "Construir módulo de notificações"                                      │     │
│  │                                                                              │     │
│  │     CARACTERÍSTICAS:                                                         │     │
│  │     - Requer Query + Transform + Validate                                   │     │
│  │     - Alta complexidade (5-6 especialistas)                                 │     │
│  │     - Aprovação humana OBRIGATÓRIA                                          │     │
│  │     - Gera Requirements + User Stories + Documentation                     │     │
│  │     - Threshold: confiança < 0.7 → SEMPRE aprovação                        │     │
│  └────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────┐     │
│  │  3. INTENÇÃO DE REFACTORAÇÃO                                                │     │
│  │     "Refatorar UserService para usar repository pattern"                   │     │
│  │     "Migrar de callbacks para async/await"                                  │     │
│  │     "Extrair lógica de negócio para domain layer"                          │     │
│  │                                                                              │     │
│  │     CARACTERÍSTICAS:                                                         │     │
│  │     - Requer Análise de Impacto + Guard Agents                              │     │
│  │     - Complexidade variável (3-5 especialistas)                             │     │
│  │     - Aprovação condicional (depende do risco)                              │     │
│  │     - Gera Rollback Plan + Migration Strategy                              │     │
│  │     - Threshold: risco ALTO → aprovação + rollback                         │     │
│  └────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Fluxo 1: Intenção Simples (Query-only)

### Definição

Intenções simples são operações de leitura que não requerem modificações no sistema. São caracterizadas por:

- **Confiança do NLU**: > 0.8
- **Especialistas envolvidos**: 1-2
- **Aprovação humana**: Não necessária
- **Tempo de execução**: < 1 segundo

### Exemplo

> "Listar usuários cadastrados na última semana"

### Fluxo Detalhado

```
USUÁRIO
    │
    │ POST /api/v1/intentions
    │ {
    │   "text": "Listar usuários cadastrados na última semana",
    │   "language": "pt-BR",
    │   "actor": {
    │     "id": "user-123",
    │     "type": "human"
    │   }
    │ }
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. GATEWAY INTENÇÕES (:8000) - Intent Envelope                               │
│                                                                             │
│  {                                                                          │
│    "id": "int-uuid-001",                                                    │
│    "actor": {...},                                                          │
│    "intent": {                                                              │
│      "text": "Listar usuários cadastrados na última semana",               │
│      "domain": "BUSINESS",                                                  │
│      "entities": [                                                          │
│        {"type": "resource", "value": "usuarios"},                           │
│        {"type": "timeframe", "value": "última semana"}                     │
│      ]                                                                      │
│    },                                                                       │
│    "confidence": 0.92                                                       │
│    "confidence_status": "high"                                              │
│  }                                                                          │
│                                                                             │
│  ✅ NLU: classificação → QueryIntent                                         │
│  ✅ Confiança: 0.92 > 0.8 → AUTO-EXECUTE                                    │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. SEMANTIC TRANSLATION ENGINE (:8001)                                      │
│                                                                             │
│  CognitivePlan {                                                            │
│    "plan_id": "plan-001",                                                   │
│    "original_intent": "Listar usuários...",                                │
│    "classified_domain": "BUSINESS",                                         │
│    "complexity": "SIMPLE",                                                  │
│    "estimated_effort": "XS",                                                │
│    "requires_approval": false,  ← AUTO-APPROVE                             │
│    "execution_strategy": {                                                 │
│      "type": "query_only",                                                 │
│      "specialists": ["business"]  ← Apenas 1 especialista                 │
│    },                                                                       │
│    "target_system": "database"                                             │
│  }                                                                          │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. CONSENSUS ENGINE (:8002) - FAST TRACK                                   │
│                                                                             │
│  SKIP: Hierarchical Consensus (confiança alta)                              │
│  → DirectRoute to Business Specialist                                      │
│                                                                             │
│  ConsolidatedDecision {                                                    │
│    "decision_id": "dec-001",                                                │
│    "consensus_type": "auto_approved",                                       │
│    "decision": "EXECUTE_QUERY",                                             │
│    "parameters": {                                                          │
│      "query_type": "user_list",                                             │
│      "filters": {                                                           │
│        "created_after": "now() - 7 days",                                   │
│        "status": "active"                                                   │
│      }                                                                      │
│    },                                                                       │
│    "requires_approval": false,                                              │
│    "estimated_duration_ms": 500                                             │
│  }                                                                          │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. ORCHESTRATOR (:8003) - MINIMAL                                           │
│                                                                             │
│  SKIP: Temporal Workflow (baixa complexidade)                               │
│  → Direct Execution Ticket                                                  │
│                                                                             │
│  ExecutionTicket {                                                          │
│    "ticket_id": "tick-001",                                                 │
│    "type": "query",                                                         │
│    "priority": "normal",                                                    │
│    "tasks": [                                                               │
│      {                                                                      │
│        "executor": "query_executor",                                        │
│        "action": "execute_query",                                           │
│        "target": "mongodb.users",                                           │
│        "query": {...}                                                       │
│      }                                                                      │
│    ]                                                                        │
│  }                                                                          │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. WORKER AGENTS (:8005) - Query Executor                                   │
│                                                                             │
│  QueryExecutor.execute()                                                   │
│    ├─ Connect to MongoDB                                                   │
│    ├─ Execute: db.users.find({                                             │
│    │      created_at: {$gte: new Date(Date.now() - 7*24*60*60*1000)},     │
│    │      status: "active"                                                  │
│    │    })                                                                  │
│    ├─ Process results (45 users found)                                     │
│    └─ Format response                                                      │
│                                                                             │
│  ExecutionResult {                                                         │
│    "ticket_id": "tick-001",                                                │
│    "status": "completed",                                                  │
│    "result": {                                                             │
│      "users": [...],           // 45 users                                 │
│      "count": 45,                                                         │
│      "query_duration_ms": 127                                             │
│    },                                                                      │
│    "executed_at": "2026-04-19T10:30:45Z"                                   │
│  }                                                                          │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. RESPOSTA AO USUÁRIO                                                     │
│                                                                             │
│  HTTP 200 OK                                                               │
│  {                                                                         │
│    "intent_id": "int-uuid-001",                                            │
│    "status": "completed",                                                  │
│    "result": {                                                             │
│      "users": [                                                            │
│        {"id": "u1", "name": "Alice", "email": "alice@..."},                 │
│        {"id": "u2", "name": "Bob", "email": "bob@..."},                     │
│        ...                                                                 │
│      ],                                                                    │
│      "total": 45,                                                          │
│      "execution_time_ms": 450                                              │
│    },                                                                      │
│    "metrics": {                                                            │
│      "confidence": 0.92,                                                   │
│      "auto_approved": true,                                                │
│      "specialists_involved": ["business"]                                  │
│    }                                                                       │
│  }                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘

⏱️ TEMPO TOTAL: ~500ms (end-to-end)
```

---

## Fluxo 2: Intenção Novo do Zero (Greenfield)

### Definição

Intenções de greenfield envolvem a criação de novas funcionalidades do zero. Características:

- **Confiança do NLU**: < 0.7 (média baixa)
- **Especialistas envolvidos**: 5-6
- **Aprovação humana**: OBRIGATÓRIA
- **Tempo de execução**: Horas/Dias
- **Artifacts**: Requirements, User Stories, Documentação, Código

### Exemplo

> "Criar sistema completo de autenticação com JWT"

### Fluxo Detalhado

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                  FLUXO 2 - INTENÇÃO NOVO DO ZERO                                     │
│                  "Criar sistema completo de autenticação com JWT"                    │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  USUÁRIO                                                                             │
│    │                                                                                 │
│    │ POST /api/v1/intentions                                                        │
│    │ {                                                                               │
│    │   "text": "Criar sistema completo de autenticação com JWT",                    │
│    │   "language": "pt-BR",                                                         │
│    │   "context": {                                                                 │
│    │     "requirements": [                                                          │
│    │       "Login com email e senha",                                               │
│    │       "Recuperação de senha",                                                 │
│    │       "Refresh token",                                                        │
│    │       "Logout em todos os dispositivos"                                        │     │
│    │     ]                                                                         │
│    │   }                                                                            │
│    │ }                                                                              │
│    │                                                                                 │
│    ▼                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 1. GATEWAY INTENÇÕES (:8000) - Deep Analysis                                 │    │
│  │                                                                             │    │
│  │  IntentEnvelope {                                                          │    │
│  │    "id": "int-uuid-002",                                                    │    │
│  │    "intent": {                                                              │    │
│  │      "text": "Criar sistema completo de autenticação...",                   │    │
│  │      "domain": "TECHNICAL",                                                  │    │
│  │      "entities": [                                                          │    │
│  │        {"type": "feature", "value": "autenticação"},                         │    │
│  │        {"type": "protocol", "value": "JWT"},                                │    │
│  │        {"type": "component", "value": "login"},                              │    │
│  │        {"type": "component", "value": "refresh_token"}                       │    │
│  │      ]                                                                      │    │
│  │    },                                                                       │    │
│  │    "confidence": 0.65           ← Confiança média baixa                     │    │
│  │    "confidence_status": "medium"  ← Requer validação                        │    │
│  │  }                                                                          │    │
│  │                                                                             │    │
│  │  ⚠️ FLAGS DE RISCO:                                                          │    │
│  │     - security_feature: ALTA                                                  │    │
│  │     - data_persistence: SIM                                                   │    │
│  │     - api_changes: SIM                                                        │    │
│  │     - breaking_change: POSSIVEL                                               │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 2. SEMANTIC TRANSLATION ENGINE (:8001)                                      │    │
│  │                                                                             │    │
│  │  CognitivePlan {                                                            │    │
│  │    "plan_id": "plan-002-greenfield",                                        │    │
│  │    "original_intent": "Criar sistema completo...",                          │    │
│  │    "original_intent_text": "Criar sistema completo de autenticação...",     │    │
│  │    "classified_domain": "TECHNICAL",                                         │    │
│  │    "complexity": "HIGH",                                                    │    │
│  │    "estimated_effort": "XL",       ← 3+ semanas                             │    │
│  │    "requires_approval": true,       ← OBRIGATÓRIO                           │    │
│  │    "execution_strategy": {                                                 │    │
│  │      "type": "full_development",                                            │    │
│  │      "specialists": [                                                      │    │
│  │        "security",       ← PRIMÁRIO (autenticação)                          │    │
│  │        "technical",      ← Implementação                                    │    │
│  │        "architecture",   ← Design do sistema                                │    │
│  │        "business",       ← Requisitos funcionais                           │    │
│  │        "behavior"        ← UX/Fluxos                                        │    │
│  │      ]                                                                      │    │
│  │    },                                                                       │    │
│  │    "target_system": {                                                       │    │
│  │      "api": "gateway-intencoes",                                            │    │
│  │      "database": "PostgreSQL + Redis",                                      │    │
│  │      "new_endpoints": [                                                    │    │
│  │        "POST /api/v1/auth/login",                                           │    │
│  │        "POST /api/v1/auth/logout",                                          │    │
│  │        "POST /api/v1/auth/refresh",                                         │    │
│  │        "POST /api/v1/auth/forgot-password",                                 │    │
│  │        "POST /api/v1/auth/reset-password"                                  │    │
│  │      ]                                                                      │    │
│  │    }                                                                        │    │
│  │  }                                                                          │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 3. CONSENSUS ENGINE (:8002) - Hierarchical Consensus                       │    │
│  │                                                                             │    │
│  │  ┌───────────────────────────────────────────────────────────────────┐     │    │
│  │  │ SPECIALIST CONVOCATION                                             │     │    │
│  │  │                                                                   │     │    │
│  │  │ 1. Security Specialist (senior: expert, weight: 0.30)             │     │    │
│  │  │    - Analyze: JWT implementation, password hashing, token        │     │    │
│  │  │      storage, session management                                    │     │    │
│  │  │    Decision: {                                                       │     │    │
│  │  │      "feasible": true,                                               │     │    │
│  │  │      "security_risk": "medium",                                       │     │    │
│  │  │      "recommendations": [                                            │     │    │
│  │  │        "Use bcrypt com cost factor 12",                               │     │    │
│  │  │        "Implement rate limiting no login",                            │     │    │
│  │  │        "JWT com refresh token rotation",                              │     │    │
│  │  │        "Armazenar apenas hash de senhas"                              │     │    │
│  │  │      ]                                                                 │     │    │
│  │  │    }                                                                  │     │    │
│  │  │                                                                   │     │    │
│  │  │ 2. Technical Specialist (senior: senior, weight: 0.25)              │     │    │
│  │  │    - Analyze: Stack, dependencies, implementation complexity      │     │    │
│  │  │    Decision: {                                                       │     │    │
│  │  │      "feasible": true,                                               │     │    │
│  │  │      "estimated_hours": 120,                                          │     │    │
│  │  │      "dependencies": [                                                │     │    │
│  │  │        {"name": "python-jose", "version": "^3.3"},                   │     │    │
│  │  │        {"name": "passlib", "version": "^1.7"},                        │     │    │
│  │  │        {"name": "bcrypt", "version": "^4.0"}                         │     │    │
│  │  │      ],                                                                 │     │    │
│  │  │      "implementation_notes": [                                         │     │    │
│  │  │        "Criar AuthService separado",                                   │     │    │
│  │  │        "Middleware de validação de JWT",                               │     │    │
│  │  │        "Redis para blacklist de tokens"                                │     │    │
│  │  │      ]                                                                 │     │    │
│  │  │    }                                                                  │     │    │
│  │  │                                                                   │     │    │
│  │  │ 3. Architecture Specialist (senior: expert, weight: 0.25)           │     │    │
│  │  │    - Analyze: System design, integration points, scalability        │     │    │
│  │  │    Decision: {                                                       │     │    │
│  │  │      "feasible": true,                                               │     │    │
│  │  │      "architecture_pattern": "Stateless Authentication",             │     │    │
│  │  │      "storage_strategy": {                                            │     │    │
│  │  │        "users": "PostgreSQL",                                         │     │    │
│  │  │        "sessions": "Redis",                                            │     │    │
│  │  │        "refresh_tokens": "PostgreSQL",                                 │     │    │
│  │  │        "blacklist": "Redis"                                            │     │    │
│  │  │      },                                                                 │     │    │
│  │  │      "api_integration": [                                              │     │    │
│  │  │        "Gateway: Adicionar auth middleware",                           │     │    │
│  │  │        "Service Registry: Register AuthService",                      │     │    │
│  │  │        "Kafka: auth.events para login/logout"                          │     │    │
│  │  │      ]                                                                 │     │    │
│  │  │    }                                                                  │     │    │
│  │  │                                                                   │     │    │
│  │  │ 4. Business Specialist (senior: mid_level, weight: 0.10)            │     │    │
│  │  │    - Analyze: Functional requirements, user stories                  │     │    │
│  │  │    Decision: {                                                       │     │    │
│  │  │      "user_stories": [                                                 │     │    │
│  │  │        {                                                               │     │    │
│  │  │          "id": "US-001",                                               │     │    │
│  │  │          "title": "Login com credenciais",                             │     │    │
│  │  │          "story": "Como usuário, quero fazer login com email          │     │    │
│  │  │                   e senha para acessar o sistema",                     │     │    │
│  │  │          "acceptance_criteria": [                                      │     │    │
│  │  │            "Usuário consegue fazer login com credenciais válidas",    │     │    │
│  │  │            "Usuário NÃO consegue fazer login com credenciais inv.",    │     │    │
│  │  │            "Usuário recebe erro específico para cada caso de falha"  │     │    │
│  │  │          ],                                                              │     │    │
│  │  │          "size": "M",                                                   │     │    │
│  │  │          "points": 5                                                    │     │    │
│  │  │        },                                                              │     │    │
│  │  │        { "id": "US-002", "title": "Logout", ... },                     │     │    │
│  │  │        { "id": "US-003", "title": "Refresh token", ... },              │     │    │
│  │  │        { "id": "US-004", "title": "Recuperação de senha", ... }        │     │    │
│  │  │      ]                                                                 │     │    │
│  │  │    }                                                                  │     │    │
│  │  │                                                                   │     │    │
│  │  │ 5. Behavior Specialist (senior: mid_level, weight: 0.10)             │     │    │
│  │  │    - Analyze: UX flows, error handling, edge cases                   │     │    │
│  │  │    Decision: {                                                       │     │    │
│  │  │      "ux_flows": [                                                      │     │    │
│  │  │        {                                                               │     │    │
│  │  │          "flow": "login",                                               │     │    │
│  │  │          "happy_path": "Login → Dashboard",                            │     │    │
│  │  │          "error_cases": [                                               │     │    │
│  │  │            "Credenciais inválidas → 401 com mensagem genérica",       │     │    │
│  │  │            "Conta bloqueada → 403 com instruções",                    │     │    │
│  │  │            "Muitas tentativas → 429 aguarde 5min"                      │     │    │
│  │  │          ]                                                              │     │    │
│  │  │        }                                                               │     │    │
│  │  │      ]                                                                 │     │    │
│  │  │    }                                                                  │     │    │
│  │  └───────────────────────────────────────────────────────────────────┘     │    │
│  │                                                                             │    │
│  │  ┌───────────────────────────────────────────────────────────────────┐     │    │
│  │  │ WEIGHTED CONSOLIDATION                                            │     │    │
│  │  │                                                                   │     │    │
│  │  │  Final Decision {                                                  │     │    │
│  │  │    "decision_id": "dec-002-auth-system",                           │     │    │
│  │  │    "consensus_type": "hierarchical",                                │     │    │
│  │  │    "unanimous": false,              ← 4/5 concordaram              │     │    │
│  │  │    "approval_percentage": 0.87,     ← 87% de concordância          │     │    │
│  │  │    "decision": "PROCEED_WITH_APPROVAL",  ← Requer aprovação        │     │    │
│  │  │    "priority": "HIGH",                                            │     │    │
│  │  │    "consolidated_recommendations": [                               │     │    │
│  │  │      "Implementar bcrypt com cost factor 12",                       │     │    │
│  │  │      "Rate limiting: 5 tentativas por 15min",                      │     │    │
│  │  │      "JWT expiry: 15min, Refresh token: 7 dias",                    │     │    │
│  │  │      "Criar AuthService (:8023) novo",                              │     │    │
│  │  │      "Middleware no Gateway para validação"                         │     │    │
│  │  │    ],                                                                 │     │    │
│  │  │    "risk_assessment": {                                              │     │    │
│  │  │      "overall": "MEDIUM",                                             │     │    │
│  │  │      "security": "MEDIUM-HIGH",                                       │     │    │
│  │  │      "complexity": "HIGH",                                            │     │    │
│  │  │      "requires_rollback_plan": true                                  │     │    │
│  │  │    }                                                                  │     │    │
│  │  │  }                                                                  │     │    │
│  │  └───────────────────────────────────────────────────────────────────┘     │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 4. APPROVAL SERVICE (:8004) - Human Approval Required                       │    │
│  │                                                                             │    │
│  │  POST /api/v1/approvals/requests                                            │    │
│  │  {                                                                          │    │
│  │    "approval_id": "apr-002",                                                │    │
│  │    "decision_id": "dec-002-auth-system",                                    │    │
│  │    "type": "greenfield_development",                                        │    │
│  │    "priority": "HIGH",                                                      │    │
│  │    "summary": "Sistema de autenticação com JWT",                            │    │
│  │    "specialist_votes": {                                                    │    │
│  │      "security": "approve",                                                 │    │
│  │      "technical": "approve",                                                │    │
│  │      "architecture": "approve",                                             │    │
│  │      "business": "approve",                                                 │    │
│  │      "behavior": "approve"                                                  │    │
│  │    },                                                                       │    │
│  │    "risk_level": "MEDIUM",                                                  │    │
│  │    "estimated_effort": "120 horas (3 semanas)",                             │    │
│  │    "requires_approval_from": [                                              │    │
│  │      "tech_lead",                                                           │    │
│  │      "security_lead"                                                        │    │
│  │    ],                                                                       │    │
│  │    "consolidated_plan": {                                                   │    │
│  │      "phases": [                                                            │    │
│  │        {                                                                    │    │
│  │          "phase": 1,                                                        │    │
│  │          "name": "Setup e Schema",                                          │    │
│  │          "tasks": [                                                         │    │
│  │            "Criar tabelas users, sessions, refresh_tokens",                 │    │
│  │            "Configurar Redis para blacklist",                               │    │
│  │            "Setup de dependências (bcrypt, jwt)"                            │    │
│  │          ]                                                                  │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "phase": 2,                                                        │    │
│  │          "name": "Core Auth Service",                                       │    │
│  │          "tasks": [                                                         │    │
│  │            "Implementar login endpoint",                                    │    │
│  │            "Implementar token generation",                                  │    │
│  │            "Implementar password hashing",                                  │    │
│  │            "Unit tests"                                                     │    │
│  │          ]                                                                  │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "phase": 3,                                                        │    │
│  │          "name": "Advanced Features",                                       │    │
│  │          "tasks": [                                                         │    │
│  │            "Implementar refresh token",                                     │    │
│  │            "Implementar logout em todos os dispositivos",                   │    │
│  │            "Implementar recuperação de senha",                              │    │
│  │            "Integration tests"                                              │    │
│  │          ]                                                                  │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "phase": 4,                                                        │    │
│  │          "name": "Integration e Deploy",                                    │    │
│  │          "tasks": [                                                         │    │
│  │            "Adicionar middleware no Gateway",                               │    │
│  │            "Registrar no Service Registry",                                 │    │
│  │            "E2E tests",                                                      │    │
│  │            "Deploy staging"                                                 │    │
│  │          ]                                                                  │    │
│  │        }                                                                    │    │
│  │      ]                                                                      │    │
│  │    }                                                                        │    │
│  │  }                                                                          │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│  ⏸️ ESTADO: AWAITING_HUMAN_APPROVAL                                               │
│  ⏱️ TEMPO MÉDIO APROVAÇÃO: 2-24 horas                                               │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Continuação: Pós-Aprovação

```
[Humano aprova a solicitação]
    │
    │ PATCH /api/v1/approvals/:id
    │ { "action": "approve", "comments": "OK, prosseguir com fase 1" }
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. REQUIREMENTS ENGINEERING (:8015)                                         │
│                                                                             │
│  POST /api/v1/requirements/generate                                         │
│                                                                             │
│  → Gera RequirementsSet:                                                   │
│    {                                                                       │
│      "requirements_set_id": "req-001",                                     │
│      "cognitive_plan_id": "plan-002-greenfield",                           │
│      "requirements": [                                                      │
│        {                                                                     │
│          "id": "REQ-FUNC-001",                                              │
│          "type": "functional",                                              │
│          "title": "Login de Usuário",                                       │
│          "description": "Sistema deve permitir login com email e senha",   │
│          "priority": "must_have",                                           │
│          "acceptance_criteria": [                                           │
│            "Dado email válido e senha correta, login é bem-sucedido",      │
│            "Dado email inválido, retorna 401",                              │
│            "Dado senha incorreta, retorna 401 sem revelar existência"      │
│          ]                                                                  │
│        },                                                                    │
│        { "id": "REQ-FUNC-002", "title": "Logout", ... },                    │
│        { "id": "REQ-FUNC-003", "title": "Refresh Token", ... },              │
│        { "id": "REQ-NF-001", "type": "non_functional",                      │
│          "title": "Segurança de Senha",                                     │
│          "description": "Senhas devem ser hashead com bcrypt (cost>=12)"  │
│        },                                                                    │
│        { "id": "REQ-NF-002", "type": "non_functional",                      │
│          "title": "Rate Limiting",                                          │
│          "description": "Máximo 5 tentativas de login por 15 minutos"      │
│        }                                                                     │
│      ]                                                                       │
│    }                                                                        │
│                                                                             │
│  → Gera UserStorySet:                                                      │
│    {                                                                       │
│      "user_story_set_id": "uss-001",                                       │
│      "requirements_set_id": "req-001",                                     │
│      "stories": [                                                          │
│        {                                                                     │
│          "id": "US-001",                                                    │
│          "requirement_id": "REQ-FUNC-001",                                  │
│          "title": "Login com Email e Senha",                               │
│          "story": "Como usuário, quero fazer login com minhas              │
│                   credenciais para acessar o sistema",                     │
│          "size": "M", "points": 5,                                         │
│          "acceptance_criteria": [...]                                      │
│        },                                                                    │
│        { "id": "US-002", "title": "Logout", "size": "S", "points": 3 },    │
│        { "id": "US-003", "title": "Refresh Token", "size": "M", "points": 5 },│    │
│        { "id": "US-004", "title": "Recuperação de Senha", "size": "L", "points": 8 }│    │
│      ]                                                                       │
│    }                                                                        │
│                                                                             │
│  → Publica em Kafka: requirements.generated, user_stories.generated          │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. DOCUMENTATION GENERATION (:8016)                                        │
│                                                                             │
│  → Gera OpenAPI Spec:                                                      │
│    {                                                                       │
│      "openapi": "3.0.0",                                                    │
│      "info": {                                                              │
│        "title": "Authentication API",                                       │
│        "version": "1.0.0"                                                   │
│      },                                                                     │
│      "paths": {                                                             │
│        "/api/v1/auth/login": {                                              │
│          "post": {                                                          │
│            "summary": "Autenticar usuário",                                 │
│            "requestBody": {                                                 │
│              "content": {                                                   │
│                "application/json": {                                        │
│                  "schema": {                                                │
│                    "type": "object",                                         │
│                    "required": ["email", "password"],                        │
│                    "properties": {                                          │
│                      "email": {"type": "string", "format": "email"},        │
│                      "password": {"type": "string", "minLength": 8}          │
│                    }                                                         │
│                  }                                                           │
│                }                                                             │
│              }                                                                │
│            },                                                                │
│            "responses": {                                                    │
│              "200": {                                                        │
│                "description": "Login bem-sucedido",                           │
│                "content": {                                                 │
│                  "application/json": {                                        │
│                    "schema": {                                              │
│                      "type": "object",                                       │
│                      "properties": {                                         │
│                        "access_token": {"type": "string"},                    │
│                        "refresh_token": {"type": "string"},                   │
│                        "expires_in": {"type": "integer", "example": 900}       │
│                      }                                                        │
│                    }                                                         │
│                  }                                                           │
│                }                                                             │
│              },                                                              │
│              "401": {"description": "Credenciais inválidas"}                 │
│            }                                                                  │
│          }                                                                    │
│        },                                                                     │
│        "/api/v1/auth/logout": {...},                                         │
│        "/api/v1/auth/refresh": {...}                                         │
│      }                                                                       │
│    }                                                                        │
│                                                                             │
│  → Gera Diagramas de Sequência                                             │
│  → Gera README do serviço                                                   │
│  → Gera Code Documentation                                                  │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 7. ORCHESTRATOR (:8003) - Temporal Workflow                                │
│                                                                             │
│  Workflow: "AuthSystemDevelopmentWorkflow"                                  │
│                                                                             │
│  Activities:                                                               │
│    1. SetupPhaseActivity                                                   │
│    2. CoreAuthServiceActivity                                              │
│    3. AdvancedFeaturesActivity                                             │
│    4. IntegrationActivity                                                  │
│    5. DeploymentActivity                                                   │
│    6. ValidationActivity                                                   │
│                                                                             │
│  ExecutionTickets: [                                                       │
│    {                                                                       │
│      "ticket_id": "tick-002-001",                                          │
│      "phase": 1,                                                           │
│      "assignee": "backend_team",                                           │
│      "tasks": [                                                             │
│        {                                                                   │
│          "id": "task-001",                                                 │
│          "title": "Criar schema PostgreSQL",                               │
│          "executor": "transform_executor",                                 │
│          "action": "create_database_schema",                               │
│          "spec": {...}                                                     │
│        }                                                                   │
│      ]                                                                     │
│    },                                                                      │
│    { "ticket_id": "tick-002-002", "phase": 2, ... },                       │
│    { "ticket_id": "tick-002-003", "phase": 3, ... },                       │
│    { "ticket_id": "tick-002-004", "phase": 4, ... }                        │
│  ]                                                                         │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 8. WORKER AGENTS (:8005) - Execução                                         │
│                                                                             │
│  Phase 1: Setup                                                             │
│    ├─ Transform Executor → Cria migration SQL                               │
│    ├─ Transform Executor → Configura Redis                                  │
│    └─ Validate Executor → Verifica schemas                                  │
│                                                                             │
│  Phase 2: Core Auth Service                                                │
│    ├─ Transform Executor → Gera código AuthService                          │
│    ├─ Transform Executor → Gera JWT utils                                  │
│    ├─ Transform Executor → Gera password hashing                           │
│    └─ Validate Executor → Unit tests                                       │
│                                                                             │
│  [CODE FORGE - OPCIONAL]                                                   │
│  Se auto_codigo=true: Code Forge (:8019) gera implementação completa       │
│                                                                             │
│  Phase 3: Advanced Features                                                 │
│    ├─ Transform Executor → Refresh token logic                             │
│    ├─ Transform Executor → Password reset flow                             │
│    └─ Validate Executor → Integration tests                                │
│                                                                             │
│  Phase 4: Integration                                                       │
│    ├─ Transform Executor → Gateway middleware                              │
│    ├─ Query Executor → Service Registry update                             │
│    └─ Validate Executor → E2E tests                                       │
└────────────────────────────┬────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 9. RESPOSTA FINAL                                                          │
│                                                                             │
│  {                                                                         │
│    "intent_id": "int-uuid-002",                                            │
│    "status": "development_in_progress",                                    │
│    "summary": {                                                             │
│      "requirements_generated": 7,                                           │
│      "user_stories_created": 4,                                            │
│      "total_story_points": 21,                                             │
│      "estimated_weeks": 3,                                                 │
│      "documentation": {                                                    │
│        "openapi_spec": "generated",                                        │
│        "sequence_diagrams": 3,                                             │
│        "readme": "generated"                                               │
│      },                                                                    │
│      "development_plan": {                                                  │
│        "phases": 4,                                                         │
│        "current_phase": 1,                                                 │
│        "repository": "https://github.com/.../auth-service",                 │
│        "tracking": {                                                        │
│          "project_board": "Jira/Linear",                                    │
│          "ticket_ids": ["TICK-001", "TICK-002", ...]                       │
│        }                                                                   │
│      }                                                                     │
│    },                                                                      │
│    "next_steps": [                                                          │
│      "Aguardar setup do ambiente de desenvolvimento",                       │
│      "Equipe backend iniciará Phase 1",                                    │
│      "Review de segurança antes do deploy staging"                         │
│    ]                                                                       │
│  }                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘

📊 GERAÇÃO DE ARTEFATOS:
├─ requirements.json (Requisitos funcionais e não-funcionais)
├─ user_stories.json (User stories com pontos)
├─ openapi.json (Especificação da API)
├─ auth_service_design.md (Arquitetura do serviço)
├─ sequence_diagrams.mermaid (Diagramas de sequência)
├─ migration.sql (Schema PostgreSQL)
└─ development_plan.md (Plano de implementação)

⏱️ TEMPO TOTAL (end-to-end): 3-6 horas (incluindo aprovação humana)
```

---

## Fluxo 3: Intenção de Refatoração

### Definição

Intenções de refatoração modificam código existente. Características:

- **Confiança do NLU**: 0.6 - 0.85 (variável)
- **Especialistas envolvidos**: 3-4 (incluindo Guard)
- **Aprovação**: Condicional ao risco
- **Tempo de execução**: Dias/Semanas
- **Requisitos**: Rollback Plan OBRIGATÓRIO

### Exemplo

> "Refatorar UserService para usar Repository Pattern"

### Fluxo Detalhado

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                     FLUXO 3 - INTENÇÃO DE REFACTORAÇÃO                              │
│                     "Refatorar UserService para usar Repository Pattern"             │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  USUÁRIO                                                                             │
│    │                                                                                 │
│    │ POST /api/v1/intentions                                                        │
│    │ {                                                                               │
│  │    "text": "Refatorar UserService para usar Repository Pattern",                 │
│  │    "language": "pt-BR",                                                         │
│  │    "context": {                                                                 │
│  │      "target_service": "user-service",                                          │
│  │      "current_implementation": "Active Record direto no MongoDB",                │
│  │      "reason": "Dificuldade de testar e baixa coesão"                          │
│  │    }                                                                            │
│    │ }                                                                              │
│    │                                                                                 │
│    ▼                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 1. GATEWAY INTENÇÕES (:8000) - Refactoring Detection                         │    │
│  │                                                                             │    │
│  │  IntentEnvelope {                                                          │    │
│  │    "id": "int-uuid-003",                                                    │    │
│  │    "intent": {                                                              │    │
│  │      "text": "Refatorar UserService para usar Repository Pattern",           │    │
│  │      "domain": "TECHNICAL",                                                  │    │
│  │      "classification": "REFACTORING",  ← TIPO ESPECÍFICO                   │    │
│  │      "entities": [                                                          │    │
│  │        {"type": "target", "value": "UserService"},                          │    │
│  │        {"type": "pattern", "value": "Repository Pattern"},                  │    │
│  │        {"type": "current_impl", "value": "Active Record"}                   │    │
│  │      ]                                                                      │    │
│  │    },                                                                       │    │
│  │    "confidence": 0.78                                                       │    │
│  │    "confidence_status": "medium"                                            │    │
│  │  }                                                                          │    │
│  │                                                                             │    │
│  │  🏷️ FLAGS ESPECIAIS:                                                         │    │
│  │     - refactoring_type: "structural"                                         │    │
│  │     - impact_analysis: REQUIRED                                              │    │
│  │     - rollback_plan: REQUIRED                                                │    │
│  │     - guard_review: REQUIRED                                                 │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 2. SEMANTIC TRANSLATION ENGINE (:8001) - Refactoring Strategy               │    │
│  │                                                                             │    │
│  │  CognitivePlan {                                                            │    │
│  │    "plan_id": "plan-003-refactor",                                          │    │
│  │    "original_intent": "Refatorar UserService...",                           │    │
│  │    "original_intent_text": "Refatorar UserService para usar Repository...",  │    │
│  │    "classified_domain": "TECHNICAL",                                         │    │
│  │    "complexity": "MEDIUM-HIGH",                                              │    │
│  │    "estimated_effort": "L",        ← 2 semanas                              │    │
│  │    "requires_approval": true,       ← Depende do risco                     │    │
│  │    "execution_strategy": {                                                 │    │
│  │      "type": "refactoring",                                                │    │
│  │      "specialists": [                                                      │    │
│  │        "technical",      ← Análise de código existente                      │    │
│  │        "architecture",   ← Avaliação do padrão                             │    │
│  │        "guard",          ← VERIFICAÇÃO DE SEGURANÇA CRÍTICA                 │    │
│  │        "analyst"         ← Análise de impacto                              │    │
│  │      ]                                                                      │    │
│  │    },                                                                       │    │
│  │    "refactoring_analysis": {                                               │    │
│  │      "target_file": "user_service.py",                                      │    │
│  │      "current_pattern": "Active Record",                                    │    │
│  │      "target_pattern": "Repository Pattern",                                │    │
│  │      "affected_components": [                                              │    │
│  │        "UserService",                                                       │    │
│  │        "UserController",                                                    │    │
│  │        "AuthService",                                                       │    │
│  │        "Tests de UserService"                                                │    │
│  │      ]                                                                      │    │
│  │    }                                                                        │    │
│  │  }                                                                          │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 3. ANALYST AGENTS (:8008) - Impact Analysis                                │    │
│  │                                                                             │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ ANALYZE REFACTORING IMPACT                                          │   │    │
│  │  │                                                                      │   │    │
│  │  │  CodebaseScanner.scan("UserService") →                              │   │    │
│  │  │    {                                                                 │   │    │
│  │  │      "file": "services/user-service/src/user_service.py",            │   │    │
│  │  │      "lines_of_code": 847,                                           │   │    │
│  │  │      "methods": 23,                                                  │   │    │
│  │  │      "dependencies": [                                                │   │    │
│  │  │        "MongoClient",                                                 │   │    │
│  │  │        "UserModel",                                                    │   │    │
│  │  │        "EmailService"                                                 │   │    │
│  │  │      ],                                                                │   │    │
│  │  │      "dependents": [                                                   │   │    │
│  │  │        "UserController: 12 chamadas diretas",                          │   │    │
│  │  │        "AuthService: 8 chamadas diretas",                              │   │    │
│  │  │        "BatchProcessor: 3 chamadas diretas"                            │   │    │
│  │  │      ],                                                                 │   │    │
│  │  │      "test_coverage": {                                                │   │    │
│  │  │        "unit_tests": 45,                                                │   │    │
│  │  │        "integration_tests": 12,                                         │   │    │
│  │  │        "coverage_percentage": 78                                        │   │    │
│  │  │      }                                                                  │   │    │
│  │  │    }                                                                  │   │    │
│  │  │                                                                      │   │    │
│  │  │  ImpactAnalysisResult {                                               │   │    │
│  │  │    "impact_level": "MEDIUM",                                           │   │    │
│  │  │    "breaking_changes": false,                                         │   │    │
│  │  │    "affected_tests": 57,                                              │   │    │
│  │  │    "estimated_refactoring_hours": 80,                                 │   │    │
│  │  │    "risk_factors": [                                                   │   │    │
│  │  │      "Muitos dependentes diretos (23)",                                 │   │    │
│  │  │      "Cobertura de testes < 80%",                                      │   │    │
│  │  │      "Métodos complexos (cyclomatic complexity > 10 em 5 métodos)"     │   │    │
│  │  │    ],                                                                 │   │    │
│  │  │    "recommendations": [                                                 │   │    │
│  │  │      "Criar UserRepository interface primeiro",                        │   │    │
│  │  │      "Implementar MongoUserRepository",                                │   │    │
│  │  │      "Refatorar UserService gradualmente",                             │   │    │
│  │  │      "Usar Facade/Adapter para manter compatibilidade",                │   │    │
│  │  │      "Aumentar cobertura de testes antes da refatoração"               │   │    │
│  │  │    ]                                                                  │   │    │
│  │  │  }                                                                    │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 4. CONSENSUS ENGINE (:8002) - Technical + Guard Review                     │    │
│  │                                                                             │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │    │
│  │  │ SPECIALIST CONVOCATION                                             │   │    │
│  │  │                                                                   │   │    │
│  │  │ 1. Technical Specialist (senior: senior, weight: 0.30)              │   │    │
│  │  │    Analyze: Código atual, viabilidade do padrão, esforço            │   │    │
│  │  │    Decision: {                                                       │   │    │
│  │  │      "feasible": true,                                               │   │    │
│  │  │      "approach": "Strangler Pattern + Facade",                        │   │    │
│  │  │      "steps": [                                                        │   │    │
│  │  │        "1. Criar UserRepository interface",                           │   │    │
│  │  │        "2. Implementar MongoUserRepository",                           │   │    │
│  │  │        "3. Criar UserServiceFacade",                                   │   │    │
│  │  │        "4. Migrar métodos um por um",                                  │   │    │
│  │  │        "5. Remover facade quando completado"                          │   │    │
│  │  │      ],                                                                │   │    │
│  │  │      "estimated_hours": 80                                             │   │    │
│  │  │    }                                                                  │   │    │
│  │  │                                                                   │   │    │
│  │  │ 2. Architecture Specialist (senior: expert, weight: 0.25)            │   │    │
│  │  │    Analyze: Padrão adequado, impacto na arquitetura                  │   │    │
│  │  │    Decision: {                                                       │   │    │
│  │  │      "pattern_approved": true,                                        │   │    │
│  │  │      "architectural_concerns": [                                       │   │    │
│  │  │        "Repository Pattern adequado para este caso",                  │   │    │
│  │  │        "Considerar Unit of Work para transações",                      │   │    │
│  │  │        "Facade pattern para compatibilidade"                          │   │    │
│  │  │      ],                                                                │   │    │
│  │  │      "new_components": [                                               │   │    │
│  │  │        "UserRepository (interface)",                                   │   │    │
│  │  │        "MongoUserRepository (implementação)",                          │   │    │
│  │  │        "UserRepositoryFactory"                                         │   │    │
│  │  │      ]                                                                 │   │    │
│  │  │    }                                                                  │   │    │
│  │  │                                                                   │   │    │
│  │  │ 3. Guard Specialist (senior: expert, weight: 0.25) ← CRÍTICO          │   │    │
│  │  │    Analyze: Riscos de segurança na refatoração                         │   │    │
│  │  │    Decision: {                                                       │   │    │
│  │  │      "security_risk": "LOW-MEDIUM",                                    │   │    │
│  │  │      "concerns_identified": [                                           │   │    │
│  │  │        "UserService contém lógica de autorização",                     │   │    │
│  │  │        "Métodos sensíveis: hasPermission, isAdmin, checkAccess"       │   │    │
│  │  │        "Garantir que refatoração NÃO altera comportamento de auth"    │   │    │
│  │  │      ],                                                                │   │    │
│  │  │      "requirements": [                                                  │   │    │
│  │  │        "Manter testes de autorização existentes",                      │   │    │
│  │  │        "Adicionar testes de segurança adicionais",                     │   │    │
│  │  │        "Review de segurança antes de merge"                            │   │    │
│  │  │      ],                                                                 │   │    │
│  │  │      "guard_approved": true  ← PODE PROSEGUIR                          │   │    │
│  │  │    }                                                                  │   │    │
│  │  │                                                                   │   │    │
│  │  │ 4. Analyst Specialist (senior: senior, weight: 0.20)                  │   │    │
│  │  │    Analyze: Impacto nos dependentes, esforço de migração              │   │    │
│  │  │    Decision: {                                                       │   │    │
│  │  │      "impact_summary": {                                               │   │    │
│  │  │        "direct_dependents": 3,                                          │   │    │
│  │  │        "indirect_dependents": 7,                                        │   │    │
│  │  │        "tests_to_update": 57,                                           │   │    │
│  │  │        "apis_affected": 5                                               │   │    │
│  │  │      },                                                                 │   │    │
│  │  │      "migration_strategy": "phased_replacement"                        │   │    │
│  │  │    }                                                                  │   │    │
│  │  └─────────────────────────────────────────────────────────────────────┘   │    │
│  │                                                                             │    │
│  │  ConsolidatedDecision {                                                    │    │
│  │    "decision_id": "dec-003-refactor",                                      │    │
│  │    "consensus_type": "hierarchical_with_guard",                            │    │
│  │    "decision": "PROCEED_WITH_CONDITIONS",                                  │    │
│  │    "approval_percentage": 0.92,     ← 92% concordância                    │    │
│  │    "guard_approval": true,               ← Guard aprovou                    │    │
│  │    "conditions": [                                                        │    │
│  │      "Aumentar cobertura de testes para > 85% antes",                      │    │
│  │      "Review de segurança obrigatório",                                    │    │
│  │      "Rollback plan obrigatório",                                          │    │
│  │      "Feature flag para habilitar nova implementação"                       │    │
│  │    ],                                                                     │    │
│  │    "rollback_plan": {                                                     │    │
│  │      "strategy": "feature_flag",                                           │    │
│  │      "rollback_time": "< 5 minutos",                                       │    │
│  │      "data_migration": false                                               │    │
│  │    },                                                                      │    │
│  │    "requires_approval": true,        ← Ainda requer aprovação             │    │
│  │    "priority": "MEDIUM"                                                   │    │
│  │  }                                                                          │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 5. APPROVAL SERVICE (:8004) - Approval with Conditions                    │    │
│  │                                                                             │    │
│  │  ApprovalRequest {                                                         │    │
│  │    "approval_id": "apr-003",                                                │    │
│  │    "type": "refactoring",                                                   │    │
│  │    "risk_level": "MEDIUM",                                                  │    │
│  │    "guard_approved": true,                                                  │    │
│  │    "conditions": [                                                          │    │
│  │      "Cobertura de testes > 85%",                                           │    │
│  │      "Feature flag implementada",                                           │    │
│  │      "Rollback plan documentado"                                            │    │
│  │    ],                                                                      │    │
│  │    "refactoring_plan": {                                                    │    │
│  │      "approach": "Strangler Pattern",                                       │    │
│  │      "phases": [                                                            │    │
│  │        {                                                                    │    │
│  │          "phase": 1, "name": "Preparação",                                  │    │
│  │          "tasks": ["Criar interface UserRepository",                        │    │
│  │                    "Implementar MongoUserRepository",                       │    │
│  │                    "Aumentar test coverage para 85%"]                      │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "phase": 2, "name": "Facade + Feature Flag",                      │    │
│  │          "tasks": ["Criar UserServiceFacade",                               │    │
│  │                    "Implementar feature flag",                              │    │
│  │                    "Configurar environment flags"]                         │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "phase": 3, "name": "Migração Gradual",                           │    │
│  │          "tasks": ["Migrar 5 métodos por vez",                              │    │
│  │                    "Atualizar testes",                                      │    │
│  │                    "Validar comportamento"]                                 │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "phase": 4, "name": "Cleanup",                                     │    │
│  │          "tasks": ["Remover código legado",                                  │    │
│  │                    "Remover facade",                                         │    │
│  │                    "Remover feature flag"]                                  │    │
│  │        }                                                                    │    │
│  │      ]                                                                      │    │
│  │    }                                                                        │    │
│  │  }                                                                          │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                  [Aprovação humana - condicional]                                 │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 6. ORCHESTRATOR (:8003) - Refactoring Workflow                              │    │
│  │                                                                             │    │
│  │  Workflow: "RefactoringWorkflow"                                           │    │
│  │                                                                             │    │
│  │  ExecutionTickets: [                                                       │    │
│  │    {                                                                       │    │
│  │      "ticket_id": "tick-003-001",                                          │    │
│  │      "phase": 1,                                                           │    │
│  │      "type": "preparation",                                                 │    │
│  │      "tasks": [                                                             │    │
│  │        {                                                                    │    │
│  │          "executor": "transform_executor",                                  │    │
│  │          "action": "create_interface",                                     │    │
│  │          "spec": {                                                          │    │
│  │            "interface": "UserRepository",                                   │    │
│  │            "methods": ["get_by_id", "get_by_email", "save", "delete"]      │    │
│  │          }                                                                  │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "executor": "transform_executor",                                  │    │
│  │          "action": "implement_repository",                                 │    │
│  │          "spec": {                                                          │    │
│  │            "class": "MongoUserRepository",                                 │    │
│  │            "implements": "UserRepository"                                  │    │
│  │          }                                                                  │    │
│  │        },                                                                   │    │
│  │        {                                                                    │    │
│  │          "executor": "validate_executor",                                   │    │
│  │          "action": "check_coverage",                                       │    │
│  │          "threshold": 85                                                    │    │
│  │        }                                                                   │    │
│  │      ]                                                                     │    │
│  │    },                                                                      │    │
│  │    { "ticket_id": "tick-003-002", "phase": 2, "type": "facade", ... },     │    │
│  │    { "ticket_id": "tick-003-003", "phase": 3, "type": "migration", ... },  │    │
│  │    { "ticket_id": "tick-003-004", "phase": 4, "type": "cleanup", ... }     │    │
│  │  ]                                                                         │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 7. WORKER AGENTS - Execução da Refatoração                                 │    │
│  │                                                                             │    │
│  │  Phase 1: Preparação                                                        │    │
│  │    ├─ Transform Executor → Gera UserRepository interface                    │    │
│  │    │   user_repository.py                                                   │    │
│  │    │   ```python                                                           │    │
│  │    │   from abc import ABC, abstractmethod                                 │    │
│  │    │   from typing import Optional                                          │    │
│  │    │   from src.models.user import User                                     │    │
│  │    │                                                                       │    │
│  │    │   class UserRepository(ABC):                                          │    │
│  │    │       @abstractmethod                                                │    │
│  │    │       async def get_by_id(self, user_id: str) → Optional[User]:      │    │
│  │    │           pass                                                        │    │
│  │    │       @abstractmethod                                                │    │
│  │    │       async def get_by_email(self, email: str) → Optional[User]:    │    │
│  │    │           pass                                                        │    │
│  │    │   ```                                                               │    │
│  │    │                                                                       │    │
│  │    ├─ Transform Executor → Gera MongoUserRepository                         │    │
│  │    │   mongo_user_repository.py                                             │    │
│  │    │   ```python                                                           │    │
│  │    │   class MongoUserRepository(UserRepository):                         │    │
│  │    │       def __init__(self, mongo_client):                              │    │
│  │    │           self._collection = mongo_client.db.users                   │    │
│  │    │       async def get_by_id(self, user_id: str):                       │    │
│  │    │           doc = await self._collection.find_one({"_id": user_id})   │    │
│  │    │           return User(**doc) if doc else None                         │    │
│  │    │   ```                                                               │    │
│  │    │                                                                       │    │
│  │    └─ Validate Executor → Verifica cobertura > 85%                         │    │
│  │                                                                             │    │
│  │  Phase 2: Facade + Feature Flag                                              │    │
│  │    ├─ Transform Executor → UserServiceFacade                                 │    │
│  │    │   ```python                                                           │    │
│  │    │   class UserServiceFacade:                                            │    │
│  │    │       def __init__(self, legacy_service, new_service):               │    │
│  │    │           self._legacy = legacy_service                                │    │
│  │    │           self._new = new_service  # Repository-based                │    │
│  │    │           self._use_new = os.getenv("USE_NEW_USER_SERVICE") == "true"│    │
│  │    │       async def get_user(self, user_id):                              │    │
│  │    │           if self._use_new:                                           │    │
│  │    │               return await self._new.get_user(user_id)                │    │
│  │    │           return await self._legacy.get_user(user_id)                  │    │
│  │    │   ```                                                               │    │
│  │    │                                                                       │    │
│  │    └─ Transform Executor → Feature flag configuration                         │    │
│  │                                                                             │    │
│  │  Phase 3: Migração Gradual (Método por método)                              │    │
│  │    ├─ Transform Executor → Migração do método get_user()                    │    │
│  │    │   - Atualiza UserService para usar repository                          │    │
│  │    │   - Atualiza testes                                                    │    │
│  │    │   - Validate Executor → Verifica comportamento idêntico              │    │
│  │    │                                                                       │    │
│  │    ├─ Transform Executor → Migração do método create_user()                 │    │
│  │    │   - Atualiza UserService                                                │    │
│  │    │   - Atualiza testes                                                    │    │
│  │    │   - Validate → Verifica                                                │    │
│  │    │                                                                       │    │
│  │    └─ [Repete para outros 21 métodos...]                                    │    │
│  │                                                                             │    │
│  │  Phase 4: Cleanup                                                            │    │
│  │    ├─ Transform Executor → Remove código legado                              │    │
│  │    ├─ Transform Executor → Remove Facade                                     │    │
│  │    ├─ Transform Executor → Remove feature flag                              │    │
│  │    └─ Validate Executor → E2E tests completos                              │    │
│  └────────────────────────────┬────────────────────────────────────────────────┘    │
│                               │                                                     │
│                               ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │ 8. DOCUMENTAÇÃO GERADA                                                    │    │
│  │                                                                             │    │
│  │  → refactoring_plan.md                                                     │    │
│  │    - Abordagem Strangler Pattern                                            │    │
│  │    - 4 fases detalhadas                                                     │    │
│  │    - Rollback plan: feature flag off                                        │    │
│  │                                                                             │    │
│  │  → architecture_decision_record.md                                          │    │
│  │    - DEC-003: Repository Pattern em UserService                             │    │
│  │    - Context: Baixa testabilidade, alta complexidade                       │    │
│  │    - Decision: Implementar Repository com Facade                            │    │
│  │    - Consequences: Maior testabilidade, separação de concerns              │    │
│  │                                                                             │    │
│  │  → security_review.md                                                       │    │
│  │    - Guard aprovou com condições                                           │    │
│  │    - Métodos sensíveis identificados                                        │    │
│  │    - Testes de segurança adicionais                                        │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ⏱️ TEMPO TOTAL: 2 semanas (execução) + 4-24 horas (aprovação + análise)              │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Matriz de Decisão

### Quando Usar Cada Fluxo

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    MATRIZ DE DECISÃO - TIPO DE INTENÇÃO                           │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌────────────────┬─────────────────────┬──────────────────┬─────────────────────┐ │
│  │   CARACTERÍSTICA│   INTENÇÃO SIMPLES   │ NOVO DO ZERO      │    REFACTORAÇÃO    │ │
│  ├────────────────┼─────────────────────┼──────────────────┼─────────────────────┤ │
│  │ Complexidade   │ Baixa (1-2 espec)   │ Alta (5-6 espec) │ Média (3-5 espec) │ │
│  │ Confiança NLU  │ > 0.8              │ < 0.7            │ 0.6 - 0.85         │ │
│  │ Aprovação      │ Auto                │ Humana           │ Condicional        │ │
│  │ Especialistas  │ 1                   │ 5-6              │ 3-4                │ │
│  │ Guard Review   │ Não                 │ Sim              │ SIM (CRÍTICO)      │ │
│  │ Execução       │ Imediata (~500ms)   │ Planejada (sem)  │ Planejada (sem)    │ │
│  │ Code Forge     │ Não                 │ Opcional        │ Opcional           │ │
│  │ Rollback       │ N/A                │ Sim              │ SIM (Obrigatório)  │ │
│  │ Feature Flag   │ Não                │ Sim              │ SIM (Obrigatório)  │ │
│  │ Artifactos     │ Resultado only     │ Full artifact set │ Refactoring plan   │ │
│  │ Tempo E2E     │ Segundos           │ Horas/Dias       │ Dias/Semanas       │ │
│  └────────────────┴─────────────────────┴──────────────────┴─────────────────────┘ │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                   EXEMPLOS DE INTENÇÕES POR TIPO                           │   │
│  │  ┌──────────────────────┬───────────────────────────────────────────────┐   │   │
│  │  │ INTENÇÃO SIMPLES      │ "Listar produtos com estoque baixo"           │   │   │
│  │  │                      │ "Buscar usuário por ID"                        │   │   │
│  │  │                      │ "Contar pedidos do mês"                       │   │   │
│  │  │                      │ "Verificar status de um ticket"                │   │   │
│  │  ├──────────────────────┼───────────────────────────────────────────────┤   │   │
│  │  │ NOVO DO ZERO         │ "Criar sistema de notificações"                │   │   │
│  │  │                      │ "Implementar API de pagamentos"                │   │   │
│  │  │                      │ "Construir módulo de relatórios"                │   │   │
│  │  │                      │ "Adicionar sistema de busca"                   │   │   │
│  │  ├──────────────────────┼───────────────────────────────────────────────┤   │   │
│  │  │ REFACTORAÇÃO         │ "Refatorar para async/await"                    │   │   │
│  │  │                      │ "Aplicar Repository Pattern"                   │   │   │
│  │  │                      │ "Extrair lógica para domain layer"             │   │   │
│  │  │                      │ "Migrar para microsserviços"                   │   │   │
│  │  └──────────────────────┴───────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Estados de uma Intenção - State Machine

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    INTENTION STATE MACHINE                                         │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│                    ┌─────────────────┐                                           │
│                    │  RECEBIDA       │                                           │
│                    │  (received)     │                                           │
│                    └────────┬─────────┘                                           │
│                             │                                                    │
│                             ▼                                                    │
│                    ┌─────────────────┐                                           │
│                    │  CLASSIFICADA   │ ← NLU                                     │
│                    │  (classified)   │                                           │
│                    └────────┬─────────┘                                           │
│                             │                                                    │
│                ┌────────────┴────────────┐                                       │
│                │                         │                                       │
│         confiança > 0.8            confiança ≤ 0.8                                 │
│                │                         │                                       │
│                ▼                         ▼                                       │
│    ┌───────────────┐          ┌─────────────────┐                                  │
│    │ AUTO_APPROVE  │          │ CONSENSUS_START │                                  │
│    └───────┬───────┘          └────────┬─────────┘                                  │
│            │                           │                                         │
│            │                    ┌──────┴──────┐                                     │
│            │                    │             │                                     │
│            │               Refatoração      Greenfield                             │
│            │                    │             │                                     │
│            │                    ▼             ▼                                     │
│            │            ┌───────────┐ ┌─────────────┐                               │
│            │            │ GUARD_    │ │ APPROVAL_   │                               │
│            │            │ REVIEW    │ │ REQUESTED   │                               │
│            │            └─────┬─────┘ └──────┬──────┘                               │
│            │                  │              │                                     │
│            │            ┌─────┴──────┐      │                                     │
│            │            │            │      │                                     │
│            │         aprovado    rejeado  │                                     │
│            │            │            │      │                                     │
│            │            ▼            ▼      ▼                                     │
│            │    ┌───────────┐ ┌──────────┐                                     │
│            │    │ APPROVAL_ │ │ REJECTED │                                     │
│            │    │ REQUESTED │ │          │                                     │
│            │    └─────┬─────┘ └──────────┘                                     │
│            │          │                                                        │
│            │    [Humano aprova]                                                │
│            │          │                                                        │
│            └───────────┼───────────────────────────────────────┐                 │
│                        │                                       │                 │
│                        ▼                                       ▼                 │
│                ┌───────────────┐                   ┌─────────────────┐                │
│                │ ORCHESTRATING │                   │ DEVELOPMENT_    │                │
│                │ (executing)   │                   │ PLANNED         │                │
│                └───────┬───────┘                   └──────┬──────────┘                │
│                        │                                  │                         │
│                        │                          ┌────────┴────────┐                   │
│                        │                          │                 │                   │
│                   sucesso                     fase completa    erro                 │
│                        │                          │                 │                   │
│                        ▼                          ▼                 ▼                   │
│                ┌───────────┐              ┌───────────┐   ┌───────────┐              │
│                │ COMPLETED │              │ NEXT_     │   │ FAILED    │              │
│                │           │              │ PHASE     │   │           │              │
│                └───────────┘              └─────┬─────┘   └─────┬─────┘              │
│                                             │               │                     │
│                                             │         ┌─────┴─────┐                │
│                                             │         │           │                │
│                                             │    recuperável  não recuperável     │
│                                             │         │           │                │
│                                             ▼         ▼           ▼                │
│                                        ┌──────────────────────────┐             │
│                                        │         DLQ               │             │
│                                        │   (dead_letter_queue)    │             │
│                                        └──────────────────────────┘             │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Tabela de Transições

| Estado Atual | Condição | Próximo Estado | Ação |
|-------------|----------|----------------|------|
| received | NLU classificação | classified | Processar intenção |
| classified | confiança > 0.8 | auto_approve | Auto-executar |
| classified | confiança ≤ 0.8 | consensus_start | Iniciar consenso |
| consensus_start | tipo = refatoração | guard_review | Verificar segurança |
| consensus_start | tipo = greenfield | approval_requested | Solicitar aprovação |
| guard_review | guard = approve | approval_requested | Solicitar aprovação |
| guard_review | guard = reject | rejected | Rejeitar intenção |
| approval_requested | humano = approve | orchestrating | Iniciar orquestração |
| approval_requested | humano = reject | rejected | Rejeitar intenção |
| orchestrating | sucesso | completed | Finalizar intenção |
| orchestrating | erro (recuperável) | failed | Tentar recovery |
| orchestrating | fase completa | next_phase | Continuar workflow |
| failed | recovery possível | orchestrating | Retentar |
| failed | recovery impossível | dlq | Enviar para DLQ |

---

## Documento vs Implementação Real

> ⚠️ **NOTA IMPORTANTE:** Este documento é **conservador** em sua descrição. A implementação real no código base **excede** o documento em vários aspectos sofisticados.

### Onde a Implementação é Mais Robusta

| Aspecto | Documento | Implementação Real | Código |
|---------|-----------|-------------------|--------|
| **Thresholds** | Fixos (0.8) | Adaptativos com contexto | `nlu_pipeline.py:1148-1165` |
| **Confiança** | Estática | Boost por role match | +10% se developer→TECHNICAL |
| **Compliance** | Não mencionado | Compliance Fallback determinístico | `consensus_orchestrator.py:89-111` |
| **Consenso** | Simplificado | Bayesiano + Voting + Fallback | `consensus_orchestrator.py:62-87` |
| **Workflows** | Básico | Saga + Compensation + DLQ | `orchestrator-dynamic/` |
| **Aprendizado** | Não mencionado | Feromônios para pesos dinâmicos | `consensus_orchestrator.py:462-519` |
| **Hierarquia** | Básico | Hierarchical Weights (GAPS-03) | `hierarchical_weights.py:38-300` |

### Onde o Documento é Preciso

- ✅ Fluxos de alto nível (Simples / Greenfield / Refatoração)
- ✅ State machine de intenções
- ✅ Matriz de decisão por tipo
- ✅ Estrutura de CognitivePlan

### Gaps Conhecidos

| Área | Status | Nota |
|------|--------|------|
| **Autorização de intenção** | ⚠️ Parcial | Autenticação OAuth2 valida, mas `requires_approval` não verifica permissões do usuário |
| **Analyst Agents no greenfield** | ⚠️ Ausente | Usados apenas para refatoração, poderiam analisar impacto em greenfield |
| **Fluxo 4: Modificações** | ⚠️ Ausente | Modificações incrementais caem em zona cinza entre os 3 fluxos |

**Para detalhes completos, ver:** `docs/ANALISE_CRITICA_CICLO_VIDAS_ATUALIZADA.md`

---

# Análise Profunda: Implementação Real vs Documento

## Overview da Sofisticação do Sistema

A implementação do Neural-Hive-Mind possui camadas de sofisticação que transcendem a documentação de alto nível. Esta seção documenta **todas as nuances** descobertas através da análise profunda do código base.

---

## 1. NLU: Thresholds Adaptativos e Boosters de Confiança

### 1.1 Threshold Base Dinâmico

O sistema **não utiliza thresholds fixos**. O ponto de partida para auto-aprovação é **0.5 (50%)**, não 0.8 como documentado simplisticamente.

```python
# services/gateway-intencoes/src/pipelines/nlu_pipeline.py:1148-1165
BASE_CONFIDENCE_THRESHOLD = 0.5
```

### 1.2 Boosters Cumulativos de Confiança

A confiança final é calculada através de **boosters cumulativos** até um limite máximo:

| Booster | Condição | Incremento | Cap |
|---------|----------|------------|-----|
| **Base** | Sempre | 0.0 | - |
| **Comprimento do Texto** | Texto rico (>50 caracteres) | +5% | 0.95 |
| **Presença de Entidades** | Entidades detectadas | +5% | 0.95 |
| **Subcategorias Detectadas** | Múltiplas subcategorias | +5% | 0.95 |
| **Match de Role** | User role ↔ Domain | +10% | 0.95 |
| **Contexto Rico** | Múltiplos contextos | +5% | 0.95 |

**Boost Máximo Teórico:** +35% sobre a base (0.5 → 0.85 antes de role matching)

### 1.3 Cálculo Real de Confiança

```python
# Pseudocódigo do cálculo real
confidence = base_confidence  # 0.5

# Boost por comprimento
if text_length > 50:
    confidence = min(0.95, confidence + 0.05)

# Boost por entidades
if entities_detected:
    confidence = min(0.95, confidence + 0.05)

# Boost por subcategorias
if subcategory_count >= 2:
    confidence = min(0.95, confidence + 0.05)

# Boost por contexto
if context_richness >= 3:
    confidence = min(0.95, confidence + 0.05)

# Boost por role matching (MAIOR boost individual)
if role_matches_domain:
    confidence = min(0.95, confidence + 0.10)
```

### 1.4 Thresholds de Decisão

| Ação | Threshold Mínimo | Condições |
|------|------------------|-----------|
| **Auto-classify** | 0.50 | Base |
| **Auto-approve (baixo risco)** | 0.70 | +boosters |
| **Auto-approve (médio risco)** | 0.80 | +boosters + role match |
| **Auto-approve (alto risco)** | 0.90 | +boosters + role match + contexto rico |
| **Sempre requer revisão** | < 0.50 | Confiança insuficiente |

---

## 2. Sistema de Confiança Baseado em Roles

### 2.1 Matriz de Role-Domain Matching

O sistema confia **mais** na classificação quando o role do usuário combina com o domínio da intenção.

| Role do Usuário | Domínio da Intenção | Boost | Justificativa |
|-----------------|---------------------|-------|---------------|
| `developer`, `engineer` | TECHNICAL | +10% | Expertise técnica |
| `manager`, `analyst`, `business` | BUSINESS | +10% | Expertise de negócio |
| `devops`, `sre`, `admin` | INFRASTRUCTURE | +10% | Expertise de infra |
| `security`, `auditor` | SECURITY | +10% | Expertise de segurança |

### 2.2 Implementação

```python
# services/gateway-intencoes/src/pipelines/nlu_pipeline.py:1148-1165
if context and context.get("user_role"):
    user_role = context.get("user_role", "").lower()

    # Verificar match role ↔ domain
    if (
        (best_domain_name == "TECHNICAL" and "developer" in user_role)
        or (best_domain_name == "BUSINESS" and any(r in user_role for r in ["manager", "analyst", "business"]))
        or (best_domain_name == "INFRASTRUCTURE" and any(r in user_role for r in ["devops", "sre", "admin"]))
        or (best_domain_name == "SECURITY" and "security" in user_role)
    ):
        confidence = min(0.95, confidence + 0.10)  # Boost de 10%
```

### 2.3 Impacto no Auto-Approve

Um desenvolvedor classificando uma intenção como TECHNICAL tem **15% de vantagem** (5% text + 5% entities + 10% role) sobre um usuário sem role específico.

---

## 3. Mecanismos de Consenso: Bayesiano, Voting e Fallback

### 3.1 Quatro Métodos de Consenso

O sistema implementa **4 métodos distintos** de consenso, selecionados dinamicamente:

| Método | Condição de Uso | Características |
|--------|-----------------|-----------------|
| **UNANIMOUS** | Alto risco + unanimidade possível | Todos concordam |
| **BAYESIAN** | Múltiplos especialistas com confianças variadas | Agregação probabilística |
| **VOTING** | Opiniões divergentes mas recuperáveis | Votação ponderada |
| **FALLBACK** | Compliance violation ou especialistas unhealthy | Decisão determinística |

### 3.2 Agregação Bayesiana

```python
# services/consensus-engine/src/services/consensus_orchestrator.py:62-75
# Agregação Bayesiana: Combina confiança como probabilidade
def bayesian_aggregation(specialist_opinions):
    """
    Combina opiniões usando Bayes:
    - Cada opinião é uma distribuição P(approve|specialist_confidence)
    - Agrega usando média ponderada por peso do especialista
    """
    total_weight = sum(op.weight for op in specialist_opinions)
    weighted_confidence = sum(op.confidence * op.weight for op in specialist_opinions) / total_weight
    return weighted_confidence
```

### 3.3 Voting Ensemble

```python
# services/consensus-engine/src/services/consensus_orchestrator.py:77-87
# Voting: Decisão por maioria com pesos hierárquicos
def voting_ensemble(specialist_opinions):
    """
    Votação onde:
    - Opinion.approve = +1
    - Opinion.reject = -1
    - Opinion.abstain = 0
    - Voto × peso do especialista = contribution
    """
    votes = [op.decision.value * op.weight for op in specialist_opinions]
    final_decision = sum(votes) / len(votes)
    return final_decision
```

### 3.4 Fallback Determinístico

```python
# services/consensus-engine/src/services/consensus_orchestrator.py:89-111
# Compliance Fallback: Quando violação detectada
def compliance_fallback(cognitive_plan, specialist_opinions, violations):
    """
    Aplica regras determinísticas quando:
    - Compliance check falha
    - Especialistas estão unhealthy
    - Divergência excessiva

    Retorna decisão conservadora com flag requires_review = True
    """
    if any(v["severity"] == "critical" for v in violations):
        return DecisionType.REJECT, True  # Rejeita + requer revisão

    # Fallback para maioria simples
    approve_count = sum(1 for op in specialist_opinions if op.decision == DecisionType.APPROVE)
    return (DecisionType.APPROVE if approve_count > len(specialist_opinions) / 2 else DecisionType.REJECT), True
```

---

## 4. Pesos Dinâmicos: Feromônios, Senioridade e Domínio

### 4.1 Fórmula de Cálculo de Peso

O peso final de cada especialista é calculado dinamicamente:

```python
# services/consensus-engine/src/services/consensus_orchestrator.py:234-300
weight = pheromone_weight × seniority_multiplier × domain_multiplier
```

### 4.2 Multiplicadores de Senioridade (GAPS-03)

| Nível | Multiplicador | Descrição |
|-------|---------------|-----------|
| **trainee** | 0.5× | Em treinamento |
| **junior** | 0.75× | Júnior |
| **mid_level** | 1.0× | Nível médio (baseline) |
| **senior** | 1.5× | Sênior |
| **expert** | 2.0× | Especialista |

**Impacto:** Um expert tem **4x mais peso** que um trainee no consenso.

### 4.3 Multiplicadores de Domínio

```python
# Configuração padrão (ajustável)
DOMAIN_MULTIPLIERS = {
    "business_BUSINESS": 1.25,      # Business specialist em domínio BUSINESS
    "technical_TECHNICAL": 1.25,     # Technical specialist em domínio TECHNICAL
    "architecture_ARCHITECTURE": 1.30,  # Architecture specialist em domínio ARCHITECTURE
    "security_SECURITY": 1.35,       # Security specialist em domínio SECURITY
    # Cross-domain: 1.0 (baseline)
}
```

### 4.4 Feromônios: Ajuste Temporal de Peso

```python
# services/consensus-engine/src/services/consensus_orchestrator.py:462-519
# Peso baseado em histórico de performance do especialista
def calculate_pheromone_weight(specialist_id, domain):
    """
    Pheromone = Successes / (Successes + Failures) × decay_factor

    O feromônio decai com o tempo para favorecer aprendizado recente.
    """
    pheromone = pheromone_store.get(specialist_id, domain)

    # Decay: 50% a cada 30 dias sem atividade
    days_since_last = (now - pheromone.last_update).days
    decay_factor = 0.5 ** (days_since_last / 30)

    return pheromone.strength × decay_factor
```

### 4.5 Exemplo de Cálculo Real

```
Especialista: Security Specialist (senior)
Domínio da intenção: SECURITY
Histórico: 45 sucessos, 5 falhas (90% success rate)

Peso = 0.90 × 1.5 (senior) × 1.35 (security domain)
Peso = 1.8225 (82.25% acima do baseline)

Comparação:
- Trainee em cross-domain: 0.5 × 1.0 = 0.5
- Expert em domain-matched: 2.0 × 1.35 = 2.7
- **Diferença: 5.4× entre extremos**
```

---

## 5. Aprendizado Contínuo com Feromônios

### 5.1 Tipos de Feromônios

O sistema publica **3 tipos** de feromônios para ajuste futuro de pesos:

| Tipo | Gatilho | Strength | Impacto |
|------|---------|----------|---------|
| **SUCCESS** | Decisão APPROVE e execução bem-sucedida | aggregated_confidence | Aumenta peso futuro |
| **FAILURE** | Decisão REJECT ou execução falhou | aggregated_risk | Diminui peso futuro |
| **WARNING** | Decisão APPROVE mas com issues | min(confidence, 0.7) | Ajuste neutro/leve ↓ |

### 5.2 Publicação de Feromônios

```python
# services/consensus-engine/src/services/consensus_orchestrator.py:489-497
if decision.final_decision == DecisionType.APPROVE:
    pheromone_type = PheromoneType.SUCCESS
    strength = decision.aggregated_confidence
elif decision.final_decision == DecisionType.REJECT:
    pheromone_type = PheromoneType.FAILURE
    strength = decision.aggregated_risk
else:
    pheromone_type = PheromoneType.WARNING
    strength = min(decision.aggregated_confidence, 0.7)

# Publicar no Kafka para todos os serviços consumirem
await pheromone_publisher.publish(
    specialist_id=opinion.specialist_id,
    domain=cognitive_plan.domain,
    pheromone_type=pheromone_type,
    strength=strength,
)
```

### 5.3 Decay Temporal

Os feromônios **decaem com o tempo** para evitar obsolescência:

- **Decay rate:** 50% a cada 30 dias sem atividade
- **Fórmula:** `current_strength = original_strength × (0.5 ^ (days_inactive / 30))`

Exemplo:
- Dia 0: strength = 0.90
- Dia 30: strength = 0.45
- Dia 60: strength = 0.225
- Dia 90: strength = 0.1125

### 5.4 Impacto no Comportamento

Este sistema permite que o consenso **aprenda quais especialistas são confiáveis** em quais domínios ao longo do tempo, criando um ciclo virtuoso de melhoria contínua.

---

## 6. Compliance Fallback com Thresholds Adaptativos

### 6.1 Detecção de Compliance Violation

```python
# services/consensus-engine/src/services/consensus_orchestrator.py:89-111
# Verificação de compliance antes da decisão final
is_compliant, violations, adaptive_thresholds = self.compliance.check_compliance(
    cognitive_plan,
    specialist_opinions,
    aggregated_confidence,
    aggregated_risk,
    divergence,
    is_unanimous,
)
```

### 6.2 Thresholds Adaptativos em Modo Degradado

Quando o sistema detecta que especialistas estão unhealthy ou a divergência é excessiva, **ajusta os thresholds dinamicamente**:

| Métrica | Threshold Normal | Threshold Degradado |
|---------|------------------|---------------------|
| **min_confidence** | 0.70 | 0.50 (-20%) |
| **max_divergence** | 0.30 | 0.50 (+67%) |
| **min_specialists_healthy** | 75% | 50% (-25%) |

### 6.3 Gatilhos de Compliance Violation

| Violação | Severity | Ação |
|---------|----------|------|
| **Especialista critical unhealthy** | CRITICAL | Fallback → Rejeita |
| **Divergência > 50%** | HIGH | Fallback → Requer revisão |
| **Confiança agregada < 30%** | HIGH | Fallback → Requer revisão |
| **Risk score > 0.9** | CRITICAL | Fallback → Rejeita |
| **Unanimity required mas não atingida** | MEDIUM | Fallback → Requer revisão |

### 6.4 Lógica de Fallback

```python
if not is_compliant:
    if any(v["severity"] == "critical" for v in violations):
        # Violação crítica → rejeita imediatamente
        final_decision = DecisionType.REJECT
        consensus_method = ConsensusMethod.FALLBACK
        requires_review = True
    else:
        # Violação não-crítica → aplica regras conservadoras
        fallback_decision = self.compliance.apply_fallback_decision(
            cognitive_plan, specialist_opinions, violations
        )
        final_decision = fallback_decision.decision
        requires_review = True
```

---

## 7. Risk Scoring Multi-Domínio

### 7.1 Distribuição de Pesos por Domínio

O risk score é calculado como **média ponderada** de avaliações multi-domínio:

```python
# services/semantic-translation-engine/src/services/orchestrator.py:138-142
risk_score = (
    business_risk × 0.40 +    # 40% peso
    security_risk × 0.35 +    # 35% peso
    operational_risk × 0.25   # 25% peso
)
```

### 7.2 Risk Floors (Pisos Mínimos)

Cada domínio possui um **risco mínimo** que nunca pode ser ignorado:

| Domínio | Risk Floor | Justificativa |
|---------|------------|---------------|
| **SECURITY** | 0.3 | Qualquer operação tem risco de segurança |
| **BUSINESS** | 0.1 | Operações têm baixo risco de negócio inerente |
| **OPERATIONAL** | 0.05 | Operações rotineiras têm risco operacional mínimo |

### 7.3 Risk Bands (Bandas de Risco)

```python
class RiskBand(Enum):
    LOW = "low"           # 0.0 - 0.3
    MEDIUM = "medium"     # 0.3 - 0.5
    HIGH = "high"         # 0.5 - 0.7
    CRITICAL = "critical" # 0.7 - 1.0
```

### 7.4 Detecção de Operações Destrutivas

```python
# services/semantic-translation-engine/src/services/orchestrator.py
DESTRUCTIVE_KEYWORDS = [
    "delete", "drop", "truncate", "remove", "destroy",
    "truncate", "purge", "erase", "wipe", "clean"
]

def is_destructive_operation(cognitive_plan):
    """
    Detecta operações destrutivas pelo nome da ação e parâmetros.
    Operações destrutivas SEMPRE requerem aprovação humana.
    """
    action = cognitive_plan.action.lower()
    params = cognitive_plan.parameters or {}

    # Check nome da ação
    if any(keyword in action for keyword in DESTRUCTIVE_KEYWORDS):
        return True

    # Check parâmetros (ex: force=True, cascade=True)
    if params.get("force") or params.get("cascade"):
        return True

    return False
```

### 7.5 Impacto no Auto-Approve

```python
# Condições para requerer aprovação
requires_approval = (
    risk_score >= 0.7              # Risco alto
    or is_destructive              # Operação destrutiva
    or risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
)
```

---

## 8. ML Predictor no Approval Service

### 8.1 RandomForest Model (v6)

O Approval Service utiliza um **RandomForest classifier** treinado para prever aprovações:

```python
# services/approval-service/src/models/approval_model.py
model_version = "v6"
model_type = "RandomForestClassifier"
n_estimators = 100
max_depth = 10

# Features utilizadas (17 total)
features = [
    "risk_score", "domain", "intent_type",
    "user_seniority", "nlp_features_sentiment",
    "nlp_features_urgency", "nlp_features_complexity",
    "specialist_count", "consensus_confidence",
    "consensus_divergence", "is_destructive",
    "estimated_duration", "resource_usage",
    "business_impact", "security_impact",
    "compliance_score", "historical_success_rate"
]
```

### 8.2 Thresholds de Auto-Decisão

| Confiança do Modelo | Ação | Revisão Humana |
|---------------------|------|----------------|
| **≥ 0.90 (very high)** | APPROVE automático | Não |
| **0.75 - 0.90 (high)** | APPROVE automático | Não |
| **0.60 - 0.75 (medium)** | APPROVE condicional | Sim (assíncrona) |
| **0.40 - 0.60 (low)** | REFER para humano | Sim (síncrona) |
| **< 0.40 (very low)** | REJECT automático | Não |

### 8.3 Override Humano

**Sempre** que um humano aprova/rejeita diferente do modelo, o caso é adicionado ao dataset de treino:

```python
# Feedback loop para retreino
if human_decision != model_prediction:
    await training_dataset.add_case(
        features=extract_features(cognitive_plan),
        label=human_decision,
        metadata={"override_reason": reason}
    )
```

### 8.4 Performance do Modelo

| Métrica | Valor v6 | Valor v5 | Delta |
|---------|----------|---------|-------|
| **Accuracy** | 0.87 | 0.82 | +6% |
| **Precision (approve)** | 0.91 | 0.88 | +3% |
| **Recall (approve)** | 0.85 | 0.79 | +7% |
| **F1-score** | 0.88 | 0.83 | +6% |

---

## 9. Active Learning e Feedback Loop

### 9.1 Cálculo de Information Value

O sistema de **Active Learning** prioriza quais casos requerem feedback humano para maximizar aprendizado:

```python
# services/approval-service/src/services/active_learning.py
def calculate_information_value(case):
    """
    Information Value = combinação de:
    1. Model uncertainty (quanto mais próximo de 0.5, melhor)
    2. Prediction disagreement (se especialistas discordaram)
    3. Feature novelty (quão raro são as features)
    4. Domain coverage (qual domínio está sub-representado)
    """
    model_uncertainty = 1 - abs(case.model_confidence - 0.5) * 2  # Max em 0.5
    disagreement = case.consensus_divergence  # 0.0 - 1.0
    novelty = calculate_feature_novelty(case.features)  # 0.0 - 1.0
    domain_imbalance = get_domain_imbalance(case.domain)  # 0.0 - 1.0

    return (
        model_uncertainty × 0.40 +
        disagreement × 0.30 +
        novelty × 0.20 +
        domain_imbalance × 0.10
    )
```

### 9.2 Enqueue Rate

Apenas **20%** dos casos são enfileirados para active learning (configurável):

```python
# Configuração
ACTIVE_LEARNING_ENQUEUE_RATE = 0.2  # 20%
ACTIVE_LEARNING_MIN_INFORMATION_VALUE = 0.5

# Lógica de enqueue
if information_value >= 0.5 and random() < 0.2:
    await active_learning_queue.enqueue(case)
```

### 9.3 Balanceamento de Dataset

O sistema monitora o balanceamento do dataset de treino:

| Métrica | Alvo | Ação se fora do alvo |
|---------|------|---------------------|
| **Approve/Reject ratio** | 50/50 | Ajustar enqueue rate |
| **Domain distribution** | Uniforme | Priorizar domains minoritários |
| **Feature coverage** | > 80% | Enqueue casos com features raras |

### 9.4 Feedback Humano Prioritário

Casos na fila de active learning são **prioritários** para aprovação humana:

```python
# API endpoint para pegar próximo caso
GET /api/v1/active-learning/queue?priority=high

# Response ordenado por information_value
{
    "cases": [
        {"case_id": "...", "information_value": 0.95, "reason": "high_model_uncertainty"},
        {"case_id": "...", "information_value": 0.87, "reason": "feature_novelty"},
        ...
    ]
}
```

---

## 10. Detecção de Operações Destrutivas

### 10.1 Keywords por Severidade

| Severidade | Keywords | Ação |
|------------|----------|------|
| **CRITICAL** | drop, truncate, destroy, wipe | Sempre requer aprovação |
| **HIGH** | delete, remove, purge, erase | Requer aprovação se em produção |
| **MEDIUM** | alter, modify, update | Requer aprovação se massivo |
| **LOW** | create, insert, add | Auto-aprove se baixo risco |

### 10.2 Parâmetros que Elevam a Severidade

| Parâmetro | Eleva severidade para | Condição |
|-----------|----------------------|----------|
| `force=True` | CRITICAL | Sempre |
| `cascade=True` | HIGH | Sempre |
| `recursive=True` | HIGH | Sempre |
| `dry_run=False` | +1 nível | Se operação destrutiva |
| `batch_size > 100` | +1 nível | Operação em lote |

### 10.3 Exemplo de Detecção

```python
# Exemplo: "Delete all users from database"
action = "delete"
params = {"cascade": True, "batch_size": 10000}

# Análise:
# - keyword "delete" → HIGH severity
# - cascade=True → eleva para CRITICAL
# - batch_size > 100 → eleva para CRITICAL
# Resultado: CRITICAL, sempre requer aprovação humana
```

---

## 11. State Machine Distribuído com Saga Pattern

### 11.1 Transições de Estado

```
[received] → [validating] → [classified] → [translated]
    ↓            ↓             ↓              ↓
   fail         fail          fail           fail
    ↓            ↓             ↓              ↓
  [failed]    [failed]      [failed]       [failed]
    ↓                                          ↓
retry_possible                                    [consensus]
    ↓                                              ↓
...←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
                                                     ↓
                                              [orchestrating]
                                                     ↓
                                      ┌──────────────┴──────────────┐
                                      ↓                             ↓
                                 [completed]                   [failed]
                                      ↓                             ↓
                                  (DLQ if unrecoverable)    (retry or DLQ)
```

### 11.2 Compensação (Saga)

Quando uma fase falha, o sistema executa **compensações** para desfazer mudanças:

```python
# Exemplo de saga compensation
async def execute_workflow_saga(cognitive_plan):
    compensations = []

    try:
        # Phase 1
        result1 = await phase1_execute(cognitive_plan)
        compensations.append(lambda: phase1_compensate(result1))

        # Phase 2
        result2 = await phase2_execute(cognitive_plan)
        compensations.append(lambda: phase2_compensate(result2))

        # Phase 3
        result3 = await phase3_execute(cognitive_plan)
        compensations.append(lambda: phase3_compensate(result3))

    except Exception as e:
        # Executar compensações em ordem reversa
        for compensation in reversed(compensations):
            try:
                await compensation()
            except Exception as comp_error:
                logger.error(f"Compensation failed: {comp_error}")
        raise
```

### 11.3 Dead Letter Queue (DLQ)

Casos que **não podem ser recuperados** são enviados para DLQ:

```python
# Condições para DLQ
DLQ_CONDITIONS = [
    "max_retries_exceeded",      # 3 tentativas falharam
    "compensation_failed",       # Saga compensation falhou
    "poison_pill",              # Mensagem malformada
    "resource_exhausted",       # Sistema sem recursos
    "timeout_hard"              # Timeout excedido
]
```

---

## 12. Observabilidade e Telemetria

### 12.1 Métricas Exportadas

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `nlu_confidence_score` | Histogram | domain, intent_type | Distribuição de confiança NLU |
| `consensus_duration_seconds` | Histogram | method | Tempo de consenso por método |
| `specialist_weight` | Gauge | specialist_id, domain | Peso dinâmico do especialista |
| `pheromone_strength` | Gauge | specialist_id, type, domain | Força do feromônio |
| `risk_score` | Histogram | domain, risk_band | Distribuição de risk score |
| `approval_prediction_confidence` | Histogram | model_version | Confiança do modelo ML |
| `active_learning_queue_size` | Gauge | priority | Tamanho da fila active learning |
| `workflow_compensation_count` | Counter | phase, reason | Número de compensações executadas |

### 12.2 Distributed Tracing

Cada intenção possui um **trace ID** que propaga através de todos os serviços:

```
Gateway [trace_id=abc123] → STE [trace_id=abc123] → Consensus [trace_id=abc123]
    → Orchestrator [trace_id=abc123] → Workers [trace_id=abc123]
```

Isso permite rastrear **exatamente** onde uma intenção falhou ou demorou.

---

## Resumo Executivo de Nuances

### O que o documento original não capturou:

1. **Thresholds não são fixos 0.8** — são 0.5 base com +35% boosters possíveis
2. **Role matching vale +10%** — trust baseado em expertise do usuário
3. **4 métodos de consenso** — não apenas "majority vote"
4. **Pesos dinâmicos** — feromônio × senioridade × domain (variação 5.4× entre extremos)
5. **Aprendizado contínuo** — feromônios com decay temporal de 30 dias
6. **Compliance fallback** — thresholds se ajustam quando sistema degrada
7. **Risk scoring multi-domínio** — 40/35/25 distribuição com floors mínimos
8. **ML RandomForest v6** — 87% accuracy, auto-decisão acima de 75% confiança
9. **Active learning** — prioriza casos com alto information value
10. **Saga compensation** — desfaz mudanças em caso de falha
11. **DLQ para unrecoverable** — mensagens envenenadas não bloqueiam o sistema
12. **Distributed tracing** — rastreabilidade end-to-end com trace IDs

---

## Sobre este Documento

**Versão:** 2.0.0
**Última Atualização:** 2026-04-19
**Autores:** Neural Hive Mind Team

**Changelog:**
- v2.0.0 (2026-04-19): **Expansão Profunda** — Adicionadas 12 seções detalhadas cobrindo todas as nuances da implementação real: NLU thresholds adaptativos, sistema de confiança baseado em roles, 4 métodos de consenso, pesos dinâmicos (feromônios × senioridade × domínio), aprendizado contínuo, compliance fallback, risk scoring multi-domínio, ML RandomForest v6, active learning, detecção de operações destrutivas, Saga pattern, e observabilidade
- v1.0.1 (2026-04-19): Adicionada seção "Documento vs Implementação Real"
- v1.0.0 (2026-04-19): Criação inicial com fluxos completos

**Status:** ✅ Completo e Profundo — Documento agora cobre TODAS as nuances da implementação
