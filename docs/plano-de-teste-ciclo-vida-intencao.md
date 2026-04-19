# Plano de Teste - Ciclo de Vida Completo de uma Intenção

**Versão:** 1.0.0
**Data:** 2026-04-19
**Status:** Planejamento
**Autor:** Neural Hive Mind QA Team
**Documento Base:** `docs/ciclo-de-vida-completo-intencao.md`

---

## Índice

1. [Visão Geral](#visão-geral)
2. [Pré-condições](#pré-condições)
3. [Suite 1: Intenção Simples](#suite-1-intenção-simples)
4. [Suite 2: Intenção Greenfield](#suite-2-intenção-greenfield)
5. [Suite 3: Intenção de Refatoração](#suite-3-intenção-de-refatoração)
6. [Suite 4: Matriz de Decisão](#suite-4-matriz-de-decisão)
7. [Suite 5: State Machine](#suite-5-state-machine)
8. [Suite 6: Casos de Borda e Negativos](#suite-6-casos-de-borda-e-negativos)
9. [Critérios de Aceitação](#critérios-de-aceitação)
10. [Execução e Relatórios](#execução-e-relatórios)

---

## Visão Geral

### Objetivo
Validar end-to-end todos os fluxos do ciclo de vida de intenções no Neural-Hive-Mind.

### Escopo
| Suite | Fluxo | Casos de Teste | Prioridade |
|-------|-------|----------------|------------|
| 1 | Intenção Simples | 8 | P0 |
| 2 | Intenção Greenfield | 12 | P0 |
| 3 | Intenção de Refatoração | 15 | P0 |
| 4 | Matriz de Decisão | 6 | P1 |
| 5 | State Machine | 8 | P1 |
| 6 | Casos de Borda | 10 | P2 |
| **TOTAL** | | **59** | |

### Serviços Envolvidos

| Serviço | Porta | Responsabilidade |
|---------|-------|------------------|
| gateway-intencoes | 8000 | Intent Envelope, NLU |
| semantic-translation-engine | 8001 | CognitivePlan |
| consensus-engine | 8002 | Hierarchical Consensus |
| orchestrator-dynamic | 8003 | Temporal Workflows |
| approval-service | 8004 | Human Approval |
| worker-agents | 8005 | Query/Transform/Validate |
| requirements-engineering | 8015 | Geração de Requisitos |
| documentation-generation | 8016 | OpenAPI, Diagramas |
| code-forge | 8019 | Geração de Código |

---

## Pré-condições

### 1. Infraestrutura

```bash
# Verificar todos os serviços estão UP
curl -f http://localhost:8000/health  # Gateway
curl -f http://localhost:8001/health  # STE
curl -f http://localhost:8002/health  # Consensus
curl -f http://localhost:8003/health  # Orchestrator
curl -f http://localhost:8004/health  # Approval
curl -f http://localhost:8005/health  # Workers
curl -f http://localhost:8015/health  # Requirements
curl -f http://localhost:8016/health  # Documentation
```

### 2. Dados de Teste

```bash
# MongoDB - Coleções necessárias
db.users.insertMany([
  { _id: "u1", name: "Alice", email: "alice@test.com", status: "active", created_at: new Date() },
  { _id: "u2", name: "Bob", email: "bob@test.com", status: "active", created_at: new Date() }
])

# Redis - Limpar chaves de teste
redis-cli FLUSHDB
```

### 3. Variáveis de Ambiente

```bash
export TEST_MODE="true"
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
export MONGODB_URL="mongodb://localhost:27017/test"
export REDIS_URL="redis://localhost:6379"
export TEMPORAL_HOST="localhost:7233"
export NEO4J_URI="bolt://localhost:7687"
```

---

## Suite 1: Intenção Simples

### TC-001: Query Simples - Listar Usuários Ativos

**Objetivo:** Validar fluxo completo de intenção simples com auto-aprovação.

**Pré-condições:**
- MongoDB com usuários ativos
- Todos os serviços UP

**Passos:**

```bash
# 1. Enviar intenção
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Listar usuários cadastrados na última semana",
    "language": "pt-BR",
    "actor": {
      "id": "test-user-001",
      "actor_type": "human",
      "name": "Test User"
    }
  }' | jq '.intent_id' > /tmp/intent_id.txt

INTENT_ID=$(cat /tmp/intent_id.txt | tr -d '"')
echo "Intent ID: $INTENT_ID"

# 2. Verificar status da intenção (poll até completed)
for i in {1..10}; do
  STATUS=$(curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID | jq -r '.status')
  if [ "$STATUS" = "completed" ]; then
    echo "✅ Intenção completada"
    break
  fi
  echo "Aguardando... ($i/10)"
  sleep 1
done

# 3. Validar resposta
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID | jq '{
  status,
  confidence,
  confidence_status,
  auto_approved,
  result: .result.users | length
}'
```

**Resultado Esperado:**

```json
{
  "status": "completed",
  "confidence": 0.92,
  "confidence_status": "high",
  "auto_approved": true,
  "result": 2
}
```

**Critérios:**
- [ ] confidence > 0.8
- [ ] confidence_status = "high"
- [ ] auto_approved = true
- [ ] Tempo total < 1 segundo
- [ ] Resultado contém usuários esperados

---

### TC-002: Query com Filtro de Tempo

**Objetivo:** Validar extração de entidade timeframe.

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Buscar pedidos dos últimos 3 dias",
    "language": "pt-BR",
    "actor": {"id": "test-user-002", "actor_type": "human"}
  }' | jq '{
  intent_id,
  entities: .intent.entities,
  confidence
}'
```

**Resultado Esperado:**

```json
{
  "intent_id": "int-uuid",
  "entities": [
    {"type": "resource", "value": "pedidos"},
    {"type": "timeframe", "value": "últimos 3 dias"}
  ],
  "confidence": 0.89
}
```

---

### TC-003: Query por ID Específico

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Buscar usuário com ID u1",
    "language": "pt-BR",
    "actor": {"id": "test-user-003", "actor_type": "human"}
  }' | jq '{
  intent_id,
  entities: [.intent.entities[] | select(.type == "user_id")]
}'
```

**Critérios:**
- [ ] Entidade user_id extraída corretamente
- [ ] Query executada com sucesso
- [ ] Retorna exatamente o usuário u1

---

### TC-004: Query com Múltiplos Filtros

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Listar usuários ativos criados na última semana que começam com A",
    "language": "pt-BR",
    "actor": {"id": "test-user-004", "actor_type": "human"}
  }'
```

**Critérios:**
- [ ] 3 entidades extraídas: status, timeframe, padrão de nome
- [ ] Filtros aplicados corretamente

---

### TC-005: Query em Outro Idioma (Inglês)

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "List active users created in the last week",
    "language": "en-US",
    "actor": {"id": "test-user-005", "actor_type": "human"}
  }'
```

**Critérios:**
- [ ] NLU processa inglês corretamente
- [ ] original_language detectado como "en"

---

### TC-006: Query com Baixa Confiança (Caso de Borda)

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "trazer coisas do banco de dados",
    "language": "pt-BR",
    "actor": {"id": "test-user-006", "actor_type": "human"}
  }'
```

**Resultado Esperado:** NÃO deve auto-executar (confiança < 0.8)

```json
{
  "confidence": 0.65,
  "confidence_status": "medium",
  "auto_approved": false,
  "requires_approval": true
}
```

---

### TC-007: Query com Texto Vazio (Validação)

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "   ",
    "language": "pt-BR",
    "actor": {"id": "test-user-007", "actor_type": "human"}
  }'
```

**Resultado Esperado:** HTTP 400

```json
{
  "detail": "Texto da intenção não pode ser vazio ou apenas whitespace"
}
```

---

### TC-008: Query com SQL Injection Tentativa

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Listar usuários; DROP TABLE users--",
    "language": "pt-BR",
    "actor": {"id": "test-user-008", "actor_type": "human"}
  }'
```

**Resultado Esperado:** HTTP 400 ou sanitized

```json
{
  "detail": "Texto contém padrão potencialmente perigoso"
}
```

---

## Suite 2: Intenção Greenfield

### TC-201: Greenfield - Sistema de Autenticação Completo

**Objetivo:** Validar fluxo completo de greenfield com aprovação.

**Passos:**

```bash
# 1. Enviar intenção greenfield
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Criar sistema completo de autenticação com JWT",
    "language": "pt-BR",
    "context": {
      "requirements": [
        "Login com email e senha",
        "Recuperação de senha",
        "Refresh token",
        "Logout em todos os dispositivos"
      ]
    },
    "actor": {"id": "test-user-201", "actor_type": "human"}
  }')

INTENT_ID=$(echo $RESPONSE | jq -r '.id')
echo "Intent ID: $INTENT_ID"

# 2. Verificar CognitivePlan
sleep 2
curl -s http://localhost:8001/api/v1/cognitive-plans/intent/$INTENT_ID | jq '{
  plan_id,
  complexity,
  estimated_effort,
  requires_approval,
  execution_strategy: .execution_strategy.type
}'

# 3. Verificar Consenso (esperar especialistas)
sleep 5
curl -s http://localhost:8002/api/v1/consensus/intent/$INTENT_ID | jq '{
  consensus_type,
  approval_percentage,
  decision,
  specialists_count: (.specialist_votes | length)
}'

# 4. Verificar Approval Request
APPROVAL_ID=$(curl -s http://localhost:8004/api/v1/approvals/intent/$INTENT_ID | jq -r '.approval_id')
echo "Approval ID: $APPROVAL_ID"

curl -s http://localhost:8004/api/v1/approvals/$APPROVAL_ID | jq '{
  type,
  priority,
  risk_level,
  estimated_effort,
  phases_count: (.consolidated_plan.phases | length)
}'
```

**Resultado Esperado:**

```json
{
  "plan_id": "plan-xxx",
  "complexity": "HIGH",
  "estimated_effort": "XL",
  "requires_approval": true,
  "execution_strategy": "full_development"
}
```

```json
{
  "consensus_type": "hierarchical",
  "approval_percentage": 0.87,
  "decision": "PROCEED_WITH_APPROVAL",
  "specialists_count": 5
}
```

---

### TC-202: Aprovar Greenfield e Gerar Artefatos

**Objetivo:** Validar geração de requirements, user stories e documentação.

**Passos:**

```bash
# 1. Aprovar solicitação
APPROVAL_ID="apr-xxx"
curl -X PATCH http://localhost:8004/api/v1/approvals/$APPROVAL_ID \
  -H "Content-Type: application/json" \
  -d '{
    "action": "approve",
    "comments": "OK, prosseguir com fase 1",
    "approved_by": "tech_lead"
  }'

# 2. Aguardar geração de requirements
sleep 5
REQUIREMENTS_ID=$(curl -s http://localhost:8015/api/v1/requirements/approval/$APPROVAL_ID | jq -r '.requirements_set_id')

echo "Requirements ID: $REQUIREMENTS_ID"

# 3. Validar Requirements gerados
curl -s http://localhost:8015/api/v1/requirements/$REQUIREMENTS_ID | jq '{
  requirements_set_id,
  total_requirements: (.requirements | length),
  functional: [.requirements[] | select(.type == "functional")] | length,
  non_functional: [.requirements[] | select(.type == "non_functional")] | length
}'

# 4. Validar User Stories
STORIES_ID=$(curl -s http://localhost:8015/api/v1/user-stories/requirements/$REQUIREMENTS_ID | jq -r '.user_story_set_id')

curl -s http://localhost:8015/api/v1/user-stories/$STORIES_ID | jq '{
  user_story_set_id,
  total_stories: (.stories | length),
  total_points: ([.stories[].points] | add)
}'

# 5. Validar OpenAPI Spec
sleep 3
curl -s http://localhost:8016/api/v1/documentation/approval/$APPROVAL_ID/openapi | jq '{
  openapi,
  info: .info.title,
  endpoints_count: (.paths | length)
}'
```

**Critérios:**
- [ ] Requirements gerados com >= 5 funcionais
- [ ] User stories com >= 4 histórias
- [ ] Total story points > 0
- [ ] OpenAPI spec com 5+ endpoints

---

### TC-203: Greenfield - API de Pagamentos Stripe

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Implementar API de pagamentos com Stripe",
    "language": "pt-BR",
    "context": {
      "requirements": [
        "Criar charge",
        "Webhook para eventos",
        "Refund",
        "Listar transações"
      ]
    },
    "actor": {"id": "test-user-203", "actor_type": "human"}
  }'
```

**Critérios:**
- [ ] Domain = TECHNICAL
- [ ] Confiança < 0.7
- [ ] Specialist "security" incluído
- [ ] Requisitos de compliance gerados

---

### TC-204: Greenfield - Módulo de Notificações

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Construir módulo de notificações push e email",
    "language": "pt-BR",
    "actor": {"id": "test-user-204", "actor_type": "human"}
  }'
```

**Critérios:**
- [ ] Plataformas múltiplas detectadas
- [ ] Services identificados: FCM, SES/SNS

---

### TC-205: Greenfield com Rejeição

**Objetivo:** Validar fluxo de rejeição por especialista.

**Passos:**

```bash
# 1. Enviar intenção
INTENT_ID="int-rejected-xxx"

# 2. Simular rejeição do Security Specialist
curl -X POST http://localhost:8002/api/v1/consensus/$INTENT_ID/vote \
  -H "Content-Type: application/json" \
  -d '{
    "specialist_type": "security",
    "decision": "reject",
    "reason": "Risco de segurança muito alto - não aprovado",
    "seniority_level": "expert"
  }'

# 3. Verificar status final
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID | jq '{
  status,
  consensus_result: .decision,
  rejection_reason
}'
```

**Resultado Esperado:** status = "rejected"

---

### TC-206: Greenfield - Verificar Especialistas Convocados

**Passos:**

```bash
INTENT_ID="int-xxx"

curl -s http://localhost:8002/api/v1/consensus/intent/$INTENT_ID/specialists | jq '{
  specialists: [.specialist_votes[].specialist_type] | sort,
  total: (.specialist_votes | length),
  seniorities: [.specialist_votes[].seniority_level] | sort
}'
```

**Resultado Esperado:**

```json
{
  "specialists": ["architecture", "behavior", "business", "security", "technical"],
  "total": 5,
  "seniorities": ["expert", "mid_level", "mid_level", "senior", "senior"]
}
```

---

### TC-207: Geração de Diagramas de Sequência

**Passos:**

```bash
APPROVAL_ID="apr-xxx"

curl -s http://localhost:8016/api/v1/documentation/approval/$APPROVAL_ID/diagrams | jq '{
  sequence_diagrams,
  total_diagrams: (.sequence_diagrams | length),
  first_diagram: .sequence_diagrams[0].name
}'
```

**Critérios:**
- [ ] 3+ diagramas gerados
- [ ] Diagramas incluem: Login, Refresh, Logout

---

### TC-208: Validação de Requirements

**Passos:**

```bash
REQUIREMENTS_ID="req-xxx"

curl -s http://localhost:8015/api/v1/requirements/$REQUIREMENTS_ID | jq '.requirements[] | select(.type == "functional") | {
  id,
  title,
  priority,
  acceptance_criteria_count: (.acceptance_criteria | length)
}'
```

**Critérios:**
- [ ] Cada requirement tem acceptance criteria
- [ ] Prioridades definidas

---

### TC-209: Verificação de Rollback Plan

**Passos:**

```bash
curl -s http://localhost:8004/api/v1/approvals/$APPROVAL_ID | jq '{
  has_rollback_plan: (.rollback_plan != null),
  rollback_strategy: .rollback_plan.strategy,
  can_rollback_in: .rollback_plan.max_rollback_time_minutes
}'
```

**Critérios:**
- [ ] Rollback plan presente
- [ ] Max rollback time definido

---

### TC-210: Feature Flag no Greenfield

**Passos:**

```bash
curl -s http://localhost:8004/api/v1/approvals/$APPROVAL_ID | jq '{
  requires_feature_flag: .consolidated_plan.requires_feature_flag,
  feature_flag_name: .consolidated_plan.feature_flag_name
}'
```

---

### TC-211: Tempo de Execução Greenfield

**Passos:**

```bash
# Medir tempo end-to-end
START_TIME=$(date +%s)

# Enviar intenção até aprovação
# ... código de teste ...

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "Tempo total: $ELAPSED segundos"
```

**Critério:** [ ] Tempo < 6 horas (simulado) ou < 1 hora (automated test)

---

### TC-212: Greenfield Multi-Domínio

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Criar dashboard de analytics em tempo real com WebSocket e gráficos interativos",
    "language": "pt-BR",
    "actor": {"id": "test-user-212", "actor_type": "human"}
  }'
```

**Critérios:**
- [ ] Domínio detectado: TECHNICAL
- [ ] Sub-domínios: websocket, ui, analytics

---

## Suite 3: Intenção de Refatoração

### TC-301: Refatoração - Repository Pattern

**Objetivo:** Validar fluxo completo de refatoração com Guard review.

**Passos:**

```bash
# 1. Enviar intenção de refatoração
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Refatorar UserService para usar Repository Pattern",
    "language": "pt-BR",
    "context": {
      "target_service": "user-service",
      "current_implementation": "Active Record direto no MongoDB",
      "reason": "Dificuldade de testar e baixa coesão"
    },
    "actor": {"id": "test-user-301", "actor_type": "human"}
  }')

INTENT_ID=$(echo $RESPONSE | jq -r '.id')
echo "Intent ID: $INTENT_ID"

# 2. Verificar classificação
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID | jq '{
  classification,
  refactoring_type,
  requires_guard_review,
  requires_rollback_plan
}'

# 3. Verificar Impact Analysis (quando implementado)
# curl -s http://localhost:8008/api/v1/impact/$INTENT_ID | jq '.'

# 4. Verificar Consenso com Guard
sleep 5
curl -s http://localhost:8002/api/v1/consensus/intent/$INTENT_ID | jq '{
  consensus_type,
  guard_approval,
  guard_specialist: .specialist_votes[] | select(.specialist_type == "guard")
}'
```

**Resultado Esperado:**

```json
{
  "classification": "REFACTORING",
  "refactoring_type": "structural",
  "requires_guard_review": true,
  "requires_rollback_plan": true
}
```

---

### TC-302: Refatoração com Guard Approval

**Objetivo:** Validar aprovação do Guard Specialist.

**Passos:**

```bash
curl -s http://localhost:8002/api/v1/consensus/intent/$INTENT_ID | jq '{
  guard_decision: .specialist_votes[] | select(.specialist_type == "guard") | .decision,
  security_risk: .specialist_votes[] | select(.specialist_type == "guard") | .security_risk,
  guard_requirements: .specialist_votes[] | select(.specialist_type == "guard") | .requirements
}'
```

**Critérios:**
- [ ] Guard revisou métodos sensíveis
- [ ] Security risk identificado
- [ ] Requisitos adicionais definidos

---

### TC-303: Refatoração - Análise de Dependentes

**Passos:**

```bash
# Simular análise de impacto
curl -s http://localhost:8008/api/v1/impact/analyze/UserService | jq '{
  impact_level,
  direct_dependents,
  indirect_dependents,
  tests_to_update,
  apis_affected
}'
```

**Resultado Esperado:**

```json
{
  "impact_level": "MEDIUM",
  "direct_dependents": 3,
  "indirect_dependents": 7,
  "tests_to_update": 57,
  "apis_affected": 5
}
```

---

### TC-304: Refatoração com Rejeição do Guard

**Passos:**

```bash
# Simular rejeição por risco de segurança
curl -X POST http://localhost:8002/api/v1/consensus/$INTENT_ID/guard-veto \
  -H "Content-Type: application/json" \
  -d '{
    "specialist_type": "guard",
    "decision": "veto",
    "reason": "Refatoração altera comportamento de autorização - RISCO CRÍTICO",
    "blocking": true
  }'

# Verificar status
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID | jq '.status'
```

**Resultado Esperado:** "rejected"

---

### TC-305: Refatoração - Migração Async/Await

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Migrar UserService de callbacks para async/await",
    "language": "pt-BR",
    "context": {
      "target_service": "user-service",
      "current_implementation": "Callbacks estilo Node.js",
      "reason": "Callback hell e dificuldade de manutenção"
    },
    "actor": {"id": "test-user-305", "actor_type": "human"}
  }'
```

**Critérios:**
- [ ] Refactoring type = "async_migration"
- [ ] Breaking changes detectados

---

### TC-306: Refatoração com Feature Flag

**Passos:**

```bash
APPROVAL_ID="apr-refactor-xxx"

curl -s http://localhost:8004/api/v1/approvals/$APPROVAL_ID | jq '{
  requires_feature_flag,
  feature_flag_config: {
    name: .feature_flag_name,
    type: .feature_flag_type,
    environments: [.feature_flag_environments[]]
  }
}'
```

**Critérios:**
- [ ] Feature flag obrigatória
- [ ] Ambientes: dev, staging, production

---

### TC-307: Refatoração - Fase de Preparação

**Passos:**

```bash
TICKET_ID="tick-xxx-phase1"

curl -s http://localhost:8003/api/v1/tickets/$TICKET_ID | jq '{
  phase,
  type,
  tasks: [.tasks[] | {
    executor,
    action,
    description
  }]
}'
```

**Resultado Esperado:**

```json
{
  "phase": 1,
  "type": "preparation",
  "tasks": [
    {"executor": "transform_executor", "action": "create_interface"},
    {"executor": "transform_executor", "action": "implement_repository"},
    {"executor": "validate_executor", "action": "check_coverage"}
  ]
}
```

---

### TC-308: Refatoração - Geração de Interface

**Passos:**

```bash
# Verificar código gerado
curl -s http://localhost:8005/api/v1/workers/result/$TICKET_ID | jq '{
  generated_interface: .result.code,
  has_abstract_methods: (.result.code | contains("abstractmethod")),
  methods_count: (.result.code | scan("async def") | length)
}'
```

---

### TC-309: Refatoração - Verificação de Coverage

**Passos:**

```bash
curl -s http://localhost:8005/api/v1/validate/coverage/UserService | jq '{
  current_coverage,
  threshold_required,
  meets_threshold: (.current_coverage >= .threshold_required),
  tests_needed
}'
```

**Critérios:**
- [ ] Threshold > 85%
- [ ] Bloqueia se não atinge threshold

---

### TC-310: Refatoração - Facade Pattern

**Passos:**

```bash
curl -s http://localhost:8005/api/v1/workers/result/ticket-facade | jq '{
  facade_code: .result.code,
  has_feature_flag: (.result.code | contains("USE_NEW")),
  has_legacy_branch: (.result.code | contains("_legacy")),
  has_new_branch: (.result.code | contains("_new"))
}'
```

---

### TC-311: Refatoração - Migração Gradual

**Passos:**

```bash
# Verificar ordem de migração dos métodos
curl -s http://localhost:8003/api/v1/tickets/ticket-migration | jq '{
  migration_order: .tasks[].method_name,
  total_methods,
  batch_size
}'
```

**Critérios:**
- [ ] Métodos migrados em batches de 5
- [ ] Ordem baseada em dependências

---

### TC-312: Refatoração - Rollback Plan

**Passos:**

```bash
curl -s http://localhost:8004/api/v1/approvals/$APPROVAL_ID/rollback | jq '{
  strategy,
  rollback_time_seconds,
  steps: [.rollback_steps[] | .description]
}'
```

**Resultado Esperado:**

```json
{
  "strategy": "feature_flag",
  "rollback_time_seconds": 300,
  "steps": [
    "Desativar feature flag",
    "Verificar sistema usando implementação antiga",
    "Monitorar métricas por 5 minutos"
  ]
}
```

---

### TC-313: Refactoração - ADR Gerado

**Passos:**

```bash
curl -s http://localhost:8016/api/v1/documentation/approval/$APPROVAL_ID/adr | jq '{
  adr_id,
  title,
  context,
  decision,
  consequences
}'
```

---

### TC-314: Refatoração - Security Review

**Passos:**

```bash
curl -s http://localhost:8006/api/v1/guard/review/$INTENT_ID | jq '{
  security_risk_level,
  sensitive_methods_found,
  recommendations,
  approved_with_conditions
}'
```

---

### TC-315: Refatoração - Tempo de Execução

**Passos:**

```bash
# Medir tempo total da refatoração
START_TIME=$(date +%s)

# ... execução completa ...

END_TIME=$(date +%s)
echo "Tempo de refatoração: $((END_TIME - START_TIME)) segundos"
```

---

## Suite 4: Matriz de Decisão

### TC-401: Decisão - Intenção Simples

**Passos:**

```bash
# Verificar matriz de decisão
curl -s http://localhost:8000/api/v1/intentions/classify \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Listar usuários ativos",
    "language": "pt-BR"
  }' | jq '{
  classified_type,
  confidence,
  route: .route_to,
  requires_approval,
  estimated_duration_ms
}'
```

**Resultado Esperado:**

```json
{
  "classified_type": "SIMPLE",
  "confidence": 0.92,
  "route_to": "direct_execution",
  "requires_approval": false,
  "estimated_duration_ms": 500
}
```

---

### TC-402: Decisão - Intenção Greenfield

**Passos:**

```bash
curl -s http://localhost:8000/api/v1/intentions/classify \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Criar sistema de autenticação",
    "language": "pt-BR"
  }' | jq '{
  classified_type,
  confidence,
  specialists_count,
  requires_human_approval
}'
```

---

### TC-403: Decisão - Intenção Refatoração

**Passos:**

```bash
curl -s http://localhost:8000/api/v1/intentions/classify \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Refatorar para Repository Pattern",
    "language": "pt-BR"
  }' | jq '{
  classified_type,
  requires_guard_review,
  requires_rollback_plan
}'
```

---

### TC-404: Threshold de Confiança (0.8)

**Passos:**

```bash
# Testar confiança = 0.79 (deve requerer aprovação)
curl -s http://localhost:8000/api/v1/intentions/classify \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Buscar dados do usuário",
    "language": "pt-BR"
  }' | jq '{
  confidence,
  auto_approved: (.confidence > 0.8)
}'
```

---

### TC-405: Especialistas por Tipo

**Passos:**

```bash
for TYPE in "simple" "greenfield" "refactoring"; do
  echo "=== $TYPE ==="
  curl -s http://localhost:8000/api/v1/intentions/specialists?type=$TYPE | jq '{
    specialists,
    count
  }'
done
```

**Resultado Esperado:**

```json
// simple
{"specialists": ["business"], "count": 1}

// greenfield
{"specialists": ["security", "technical", "architecture", "business", "behavior"], "count": 5}

// refactoring
{"specialists": ["technical", "architecture", "guard", "analyst"], "count": 4}
```

---

### TC-406: Complexidade e Esforço

**Passos:**

```bash
curl -s http://localhost:8000/api/v1/intentions/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Criar sistema de autenticação completo",
    "language": "pt-BR"
  }' | jq '{
  complexity,
  estimated_effort,
  estimated_weeks
}'
```

---

## Suite 5: State Machine

### TC-501: Transição received → classified

**Passos:**

```bash
# Criar intenção e verificar transição
INTENT_ID=$(curl -s -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{"text": "Teste", "language": "pt-BR", "actor": {"id": "test"}}' | jq -r '.id')

# Verificar estado inicial
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID/state | jq '{
  current_state,
  previous_state,
  transition_from
}'
```

---

### TC-502: Transição classified → auto_approve

**Passos:**

```bash
# Intenção com alta confiança
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID/state | jq '{
  state_history: [.history[] | select(.from == "classified" and .to == "auto_approve")]
}'
```

---

### TC-503: Transição classified → consensus_start

**Passos:**

```bash
# Intenção com baixa confiança
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID/state | jq '{
  current_state,
  reason_for_consensus: .history[] | select(.to == "consensus_start") | .reason
}'
```

---

### TC-504: Transição consensus_start → guard_review

**Passos:**

```bash
# Intenção de refatoração
curl -s http://localhost:8002/api/v1/consensus/intent/$INTENT_ID | jq '{
  trigger_guard_review: (.classification == "REFACTORING")
}'
```

---

### TC-505: Transição guard_review → approval_requested

**Passos:**

```bash
# Guard aprovou
curl -s http://localhost:8002/api/v1/consensus/intent/$INTENT_ID/votes/guard | jq '{
  decision,
  next_state: "approval_requested"
}'
```

---

### TC-506: Transição approval_requested → orchestrating

**Passos:**

```bash
# Humano aprovou
curl -X PATCH http://localhost:8004/api/v1/approvals/$APPROVAL_ID \
  -H "Content-Type: application/json" \
  -d '{"action": "approve"}'

# Verificar transição
curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID/state | jq '{
  current_state
}'
```

---

### TC-507: Transição orchestrating → completed

**Passos:**

```bash
# Aguardar execução completa
sleep 30

curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID/state | jq '{
  current_state,
  final_state: "completed",
  execution_time_ms
}'
```

---

### TC-508: Transição para rejected

**Passos:**

```bash
# Simular rejeição
curl -X PATCH http://localhost:8004/api/v1/approvals/$APPROVAL_ID \
  -H "Content-Type: application/json" \
  -d '{"action": "reject", "reason": "Não aprovado"}'

curl -s http://localhost:8000/api/v1/intentions/$INTENT_ID/state | jq '{
  current_state,
  rejected_reason
}'
```

---

## Suite 6: Casos de Borda e Negativos

### TC-601: Texto Vazio

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{"text": "", "language": "pt-BR", "actor": {"id": "test"}}'
```

**Esperado:** HTTP 400

---

### TC-602: Texto Muito Longo (>10000 chars)

**Passos:**

```bash
LONG_TEXT=$(python3 -c "print('A' * 10001)")

curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$LONG_TEXT\", \"language\": \"pt-BR\", \"actor\": {\"id\": \"test\"}}"
```

**Esperado:** HTTP 400

---

### TC-603: Idioma Inválido

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{"text": "Teste", "language": "xx-XX", "actor": {"id": "test"}}'
```

**Esperado:** HTTP 400

---

### TC-604: Actor Type Inválido

**Passos:**

```bash
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{"text": "Teste", "language": "pt-BR", "actor": {"id": "test", "actor_type": "alien"}}'
```

**Esperado:** HTTP 422

---

### TC-605: SQL Injection Detection

**Passos:**

```bash
MALICIOUS_INPUTS=(
  "'; DROP TABLE users; --"
  "' OR '1'='1"
  "'; EXEC xp_cmdshell('dir'); --"
  "${HOME}/.ssh/id_rsa"
  "<script>alert('xss')</script>"
)

for INPUT in "${MALICIOUS_INPUTS[@]}"; do
  echo "Testing: $INPUT"
  curl -s -X POST http://localhost:8000/api/v1/intentions \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$INPUT\", \"language\": \"pt-BR\", \"actor\": {\"id\": \"test\"}}" | jq '.error'
done
```

---

### TC-606: Timeout na Execução

**Passos:**

```bash
# Intenção que demora muito
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Processar milhões de registros",
    "language": "pt-BR",
    "constraints": {"timeout_ms": 1000}
  }'
```

**Esperado:** Timeout após 1s

---

### TC-607: Serviço Indisponível

**Passos:**

```bash
# Parar um serviço
docker stop consensus-engine

# Tentar enviar intenção
curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -d '{"text": "Teste", "language": "pt-BR", "actor": {"id": "test"}}'

# Restaurar
docker start consensus-engine
```

**Esperado:** HTTP 503 ou fallback

---

### TC-608: Intenção Duplicada (Idempotência)

**Passos:**

```bash
# Enviar mesma intenção 2x
PAYLOAD='{"text": "Listar usuários", "language": "pt-BR", "actor": {"id": "test"}}'

ID1=$(curl -s -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" -d "$PAYLOAD" | jq -r '.id')

ID2=$(curl -s -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" -d "$PAYLOAD" | jq -r '.id')

# Deve ser mesma intenção (idempotência)
echo "ID1: $ID1"
echo "ID2: $ID2"
```

---

### TC-609: Rate Limiting

**Passos:**

```bash
# Enviar 100 requisições rápidas
for i in {1..100}; do
  curl -s -X POST http://localhost:8000/api/v1/intentions \
    -H "Content-Type: application/json" \
    -d '{"text": "Test", "language": "pt-BR", "actor": {"id": "test"}}' &
done
wait
```

**Esperado:** HTTP 429 após limite

---

### TC-610: Correlation ID Tracking

**Passos:**

```bash
CORRELATION_ID="test-correlation-123"

curl -X POST http://localhost:8000/api/v1/intentions \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: $CORRELATION_ID" \
  -d '{"text": "Teste", "language": "pt-BR", "actor": {"id": "test"}}' | jq '{
  correlation_id,
  trace_id
}'
```

---

## Critérios de Aceitação

### Por Suite

| Suite | Taxa de Sucesso | Critério |
|-------|-----------------|----------|
| 1 - Intenção Simples | 100% | 8/8 passam |
| 2 - Intenção Greenfield | 95% | 11/12 passam |
| 3 - Intenção Refatoração | 93% | 14/15 passam |
| 4 - Matriz de Decisão | 100% | 6/6 passam |
| 5 - State Machine | 100% | 8/8 passam |
| 6 - Casos de Borda | 90% | 9/10 passam |
| **TOTAL** | **96%** | **56/59** |

### Não-Funcionais

| Métrica | Meta |
|---------|------|
| Tempo resposta intenção simples | < 500ms |
| Tempo resposta greenfield (sem aprovação) | < 5min |
| Tempo resposta refatoração (sem aprovação) | < 10min |
| Taxa de erro HTTP 5xx | < 0.1% |
| Disponibilidade dos serviços | > 99.9% |

---

## Execução e Relatórios

### Ordem de Execução

1. **Setup:** Pré-condições (15 min)
2. **Suite 1:** Intenção Simples (30 min)
3. **Suite 4:** Matriz de Decisão (20 min)
4. **Suite 5:** State Machine (25 min)
5. **Suite 2:** Intenção Greenfield (60 min)
6. **Suite 3:** Intenção Refatoração (90 min)
7. **Suite 6:** Casos de Borda (45 min)

**Tempo Total Estimado:** ~4.5 horas

### Relatório de Execução

```bash
# Executar todos os testes
./scripts/run-intention-tests.sh > test-results.log 2>&1

# Gerar relatório
./scripts/generate-test-report.sh test-results.log > test-report.md
```

### Template de Relatório

```markdown
# Relatório de Teste - Ciclo de Vida de Intenções

**Data:** YYYY-MM-DD
**Executado por:** QA Team
**Ambiente:** Staging

## Resumo Executivo

| Suite | Planejados | Passaram | Falharam | % Sucesso |
|-------|-----------|----------|----------|-----------|
| 1 - Simples | 8 | 8 | 0 | 100% |
| 2 - Greenfield | 12 | 11 | 1 | 92% |
| 3 - Refatoração | 15 | 14 | 1 | 93% |
| 4 - Matriz | 6 | 6 | 0 | 100% |
| 5 - State Machine | 8 | 8 | 0 | 100% |
| 6 - Borda | 10 | 9 | 1 | 90% |
| **TOTAL** | **59** | **56** | **3** | **95%** |

## Falhas

### TC-XXX: Nome do Teste
**Status:** FAILED
**Erro:```
Mensagem de erro
```
**Causa Raiz:** Análise
**Ação Corretiva:** Plano

## Métricas

- Tempo total execução: X horas
- Tempo médio por teste: Y min
- Pico de requisições: Z req/s
```

---

**Fim do Plano de Teste**
