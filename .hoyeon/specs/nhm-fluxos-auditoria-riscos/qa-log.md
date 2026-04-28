---
spec: "nhm-fluxos-auditoria-riscos"
phase: interview
status: complete
where:
  goal: "Auditoria crítica dos fluxos principais do NHM identificando top-10 riscos arquitecturais com mitigações priorizadas por impacto/esforço"
  non_goals:
    - "Implementação das mitigações (apenas identificação e priorização)"
    - "Refactor de código (análise arquitectural, não de implementação)"
    - "Revisão de styling/convenções (riscos estruturais apenas)"
  project_type: "dev-tool"
  situation: "hybrid"
  ambition: "product"
  risk_modifiers:
    - "sensitive-data"
    - "external-exposure"
    - "high-scale"
depth_calibration:
  business:
    WHO: "light"
    WHY: "standard"
    WHAT: "standard"
    SUCCESS: "standard"
    SCOPE: "standard"
    RISK: "deep"
  interaction:
    JOURNEY: "standard"
    HAPPY: "standard"
    EDGE: "standard"
    STATE: "standard"
    FEEDBACK: "standard"
    ACCESS: "deep"
  tech:
    ARCH: "deep"
    DATA: "deep"
    INFRA: "deep"
    DEPEND: "standard"
    COMPAT: "deep"
    SECURITY: "deep"
coverage:
  business: 1.0
  interaction: 1.0
  tech: 1.0
research_done: true
---

# Q&A Log

## Research

### Existing Architecture Summary

**Cognitive Pipeline (Gateway → STE → Consensus → Orchestrator → Workers):**
- 8 serviços principais com ports 8000-8007
- Mensageria Kafka (aiokafka) para comunicação async
- gRPC para chamadas síncronas especialistas
- Temporal para orquestração de workflows
- MongoDB (motor), Redis, Neo4j para persistência

**8 Serviços Core:**
1. `gateway-intencoes` (8000) - API Gateway, NLU, roteamento
2. `semantic-translation-engine` (8001) - Tradução intenções → Cognitive Plans
3. `consensus-engine` (8002) - Consenso entre especialistas (hierárquico)
4. `orchestrator-dynamic` (8003) - Orquestração via Temporal (Saga pattern)
5. `approval-service` (8004) - Aprovação humana
6. `worker-agents` (8005) - Execução tarefas
7. `queen-agent` (8006) - Supervisor
8. `service-registry` (8007) - Descoberta serviços

### Relevant Files & Modules

**Cognitive Pipeline:**
- `services/gateway-intencoes/src/main.py` - Entry point
- `services/semantic-translation-engine/src/orchestrator.py` - DAGGenerator
- `services/consensus-engine/src/services/consensus_orchestrator.py` - Consenso hierárquico
- `services/orchestrator-dynamic/src/main.py` - Saga orchestration

**Message Flows:**
- `services/gateway-intencoes/src/producer/kafka_intent_producer.py`
- `services/semantic-translation-engine/src/consumers/`
- `services/consensus-engine/src/producers/`

**Error Handling:**
- `services/self-healing-engine/src/services/circuit_breaker.py`
- `libraries/python/neural_hive_resilience/`

**State Management:**
- `services/gateway-intencoes/src/cache/redis_client.py`
- `services/scout-agents/src/coordination/redis_state_store.py`
- `services/orchestrator-dynamic/src/saga/saga_state.py`

### Toolchain

**Python:** 3.12+ com FastAPI, asyncio
**Build/Test:** `make test`, `ruff check`, `black .`, `mypy`
**Dependencies:** `requirements-base.txt` + `pyproject.toml`
**Deployment:** Docker Compose (local), Kubernetes (prod)

### Constraints & Conventions Discovered

**Exactly-Once Kafka:** `enable.idempotence=true`, `acks=all`, `min.insync.replicas=2`
**Service Mesh:** Istio com mTLS obrigatório
**Policy Enforcement:** OPA para validação planos cognitivos
**MongoDB Fail-Closed:** execution_tickets bloqueiam workflow se falhar
**Correlation ID:** Inconsistente entre serviços (risco identificado)

### Known Issues (from docs/ analysis)

**Críticos:**
- Single point of failure no Gateway
- Falta DLQ handling para mensagens Kafka falhadas
- Condição de corrida no Consensus Engine
- Duplicação estado Redis/MongoDB

**Moderados:**
- Timeout globais não configurados individualmente
- Circuit breakers não configurados globalmente
- grpc version mismatch (requirements conflict)

**GAPS Pendentes:** GAP-01 (STE-Consensus), GAP-02 (Execution Results)

## Mirror Confirmation

#### Q: Mirror — Does this match your intent?
> **Status:** resolved
> **Answer:** Aprovar
>
> Understanding confirmed: Auditoria sistemática dos fluxos arquitectónicos do NHM para identificar riscos estruturais que possam comprometer operabilidade, segurança ou escalabilidade, com output priorizado (top-10 riscos com mitigação e matriz impacto×esforço).

#### WHERE Grounding

#### Q: Project type, Situation, Ambition
> **Status:** resolved
> **Answer:**
> - **Project type:** Dev tool / Library (análise que gera relatório)
> - **Situation:** Hybrid
> - **Ambition:** Product

#### Q: Risk factors
> **Status:** resolved
> **Answer:** Sensitive data, External exposure, High scale

## Axis: Business

### WHO

#### Q: Quem é o consumidor principal do relatório de auditoria?
> **Status:** resolved
> **Answer:** Dev team/Engenharia
>
> O relatório deve ser acção-oriented para dev team implementar mitigações.

### WHY

#### Q: Por que esta auditoria é necessária agora?
> **Status:** resolved
> **Answer:** Review periódica + Débito técnico acumulado + performance bottlenecks + compliance/segurança pendentes
>
> Trigger: Technical debt review periódica (não incidente específico).
> A research revelou riscos críticos conhecidos (SPOF Gateway, falta DLQ, race condition consensus) que precisam de priorização.

##### Drill Q: Qual é o trigger específico para esta auditoria agora?
> **Status:** resolved
> **Answer:** Review periódica

### WHAT

#### Q: Quais fluxos devem ser incluídos na auditoria?
> **Status:** resolved
> **Answer:** Cognitive Pipeline + Message flows + Service communication + Orchestration layer
>
> **Fluxos IN scope:**
> - Cognitive Pipeline (Gateway→STE→Consensus→Orchestrator)
> - Message flows (Kafka, DLQ, exactly-once)
> - Service communication (gRPC, timeouts, circuit breakers)
> - Orchestration layer (Temporal, Saga, state)
>
> **Fluxos OUT scope:**
> - Frontend/Web interfaces

### SUCCESS

#### Q: Como definimos que a auditoria foi um sucesso?
> **Status:** resolved
> **Answer:** Baseline estabelecido
>
> Sucesso = gap analysis completo vs arquitectura desejada, com top-10 riscos priorizados.

### SCOPE

#### Q: Qual é o deliverable final?
> **Status:** resolved
> **Answer:** Relatório Deep dive com top-10 riscos + mitigações priorizadas (multi-factor)
>
> Formato: documento markdown com análise detalhada por risco (full detalhe: conceito + passos implementação).

##### Drill Q: Qual deve ser o formato da matriz de priorização?
> **Status:** resolved
> **Answer:** Deep dive — documento com análise profunda por risco

##### Drill Q: Qual será o critério principal para priorizar os top-10 riscos?
> **Status:** resolved
> **Answer:** Multi-factor (risco × custo/benefício × urgência)

##### Drill Q: Qual nível de detalhe para as mitigações propostas?
> **Status:** resolved
> **Answer:** Full detalhe (conceito + passos implementação)

### RISK

#### Q: Que contexto de riscos já conhecidos devemos considerar?
> **Status:** resolved
> **Answer:** Débito técnico + Performance bottlenecks + PII/Privacy compliance
>
> Contexto: research identificou riscos críticos (SPOF Gateway, falta DLQ, race condition, state duplication) que devem ser incluídos na análise.

##### Drill Q: Que requisitos de compliance se aplicam?
> **Status:** resolved
> **Answer:** PII/Privacy (GDPR/LGPD) — dados pessoais regulados

##### Drill Q: Que tipos de dados sensíveis processa o sistema?
> **Status:** resolved
> **Answer:** PII básico (nomes, emails, identificadores) + Business confidential (segredos comerciais, propriedade intelectual)

##### Drill Q: Qual é o volume aproximado de operações por dia?
> **Status:** resolved
> **Answer:** Médio volume (1000-10000 operações/dia)

##### Drill Q: Qual é o número exacto de operações por dia?
> **Status:** assumption
> **Answer:** Não sei — usar assumption de ~5000 ops/dia como baseline média do range "médio volume"
>
> Justificativa: Valor central do range permite análise de risco adequada. Se o valor real for significativamente diferente, ajustar na fase de execução.

**Assumptions sobre Riscos Conhecidos (baseado na research):**
- SPOF Gateway: probabilidade ALTA, impacto ALTO (perda completa serviço)
- Falta DLQ: probabilidade MÉDIA, impacto ALTO (perda dados)
- Race condition consensus: probabilidade BAIXA, impacto MÉDIO (inconsistência decisões)
- State duplication: probabilidade ALTA, impacto MÉDIO (manutenibilidade)
- Volume: ~5000 ops/dia (assumption), escala é preocupação moderada

## Axis: Interaction

### JOURNEY

#### Q: Como é que a equipa de engenharia vai consumir o relatório de auditoria?
> **Status:** resolved
> **Answer:** Ticket system
>
> Cada risco/mitigação deve criar ticket no sistema de tracking.

### HAPPY

#### Q: Qual é o fluxo ideal (happy path) após entrega do relatório?
> **Status:** resolved
> **Answer:** Lead-driven
>
> Tech lead analisa relatório → cria planos → delega tasks para dev team.

### EDGE

#### Q: Quais edge cases devem ser considerados no relatório?
> **Status:** resolved
> **Answer:** Nenhum selecionado (não aplicável ou coberto por análise standard)
>
> Casos edge standard (riscos insuficientes, mitigações vagas) são tratados na própria análise.

### STATE

#### Q: Como o relatório deve ser versionado/atualizado?
> **Status:** resolved
> **Answer:** Versionado (living document)
>
- Versão única no momento da entrega (v1.0)
- Atualizado à medida que mitigações são implementadas
- Mudanças de estado tracked em git

### FEEDBACK

#### Q: Como a equipa dá feedback ou contesta a análise?
> **Status:** resolved
> **Answer:** Nenhum
>
> Relatório é deliverable final; disputas são tratadas via novo ciclo de auditoria se necessário.

### ACCESS

#### Q: Quem tem acesso ao relatório?
> **Status:** resolved
> **Answer:** Interno (dev team apenas)
>
- Access control: dev team
- Não público — contém info sensível sobre arquitectura/riscos

## Axis: Tech

### ARCH

#### Q: Que aspectos arquitecturais priorizar na análise?
> **Status:** resolved
> **Answer:** Estrutura código + Performance + Disponibilidade + Escalabilidade
>
- Estrutura: componentes, dependências, acoplamento
- Performance: latência, throughput, bottlenecks
- Disponibilidade: SPOFs, fallbacks, redundância
- Escalabilidade: rate limiting, throttling, autoscaling

##### Drill Q: Quais SLAs/performance targets estão formalmente definidos?
> **Status:** resolved
> **Answer:** Best practices (não há SLAs formais)
>
> **Assumptions (best practices para médio volume ~5000 ops/dia):**
> - Latência: p50 < 100ms, p95 < 500ms, p99 < 2s (endpoints internos)
> - Throughput: >100 ops/sec sustained capability
> - RTO: <5 min para serviços críticos, <30 min para não-críticos
> - RPO: <1 min para execution tickets, <5 min para outros dados
> - Disponibilidade: 99.5% target (~3.65h downtime/mês)

### DATA

#### Q: Que aspectos de data/estado priorizar?
> **Status:** resolved
> **Answer:** State management + Data privacy + Message reliability
>
- State: consistência, duplicação, sincronização
- Privacy: PII encryption, masking, retention
- Reliability: Kafka exactly-once, DLQ, ordering

##### Drill Q: Que framework de compliance é aplicável?
> **Status:** resolved
> **Answer:** GDPR/LGPD compliance obrigatório
>
> **Assumptions (GDPR/LGPD best practices):**
> - PII: right to erasure, data minimization, purpose limitation
> - Retention: PII máx 2 anos após fim relação (salvo obrigação legal)
> - Residência: dados dentro UE/BR conforme aplicável
> - Consistência: strong para execution tickets (fail-closed), eventual para outros
> - Encryption: at-rest e in-transit para PII

### INFRA

#### Q: Que aspectos de infraestrutura priorizar?
> **Status:** resolved
> **Answer:** Kubernetes config + Container orchestration + Datastores clusters + Deploy automation
>
- K8s: resources, limits, HPA
- Containers: Docker, networking, service mesh
- Datastores: Kafka, MongoDB, Redis clusters
- Deploy: CI/CD pipelines

**Assumptions (infra escala médio):**
- Pods: ~50-100 pods total para 8 serviços
- Resources: limits 512Mi-2Gi RAM por pod, 0.5-2 CPU
- HPA: target 70% CPU, scale 2-10 replicas
- Storage: ~100GB total para datastores
- DR: single-region (não multi-region)

### DEPEND

#### Q: Que ferramentas usar para análise arquitectural?
> **Status:** resolved
> **Answer:** Manual analysis
>
- Código review manual + documentação existente
- Scripts auxiliares se necessário
- Sem ferramentas especializadas (SonarQube, etc)

##### Drill Q: Qual é a metodologia concreta para análise manual?
> **Status:** resolved
> **Answer:** Checklist estruturado + código review
>
> Checklist base: SPOFs, DLQ handling, state duplication, timeout configs, circuit breakers, correlation ID propagation, PII masking, encryption, error handling, retry logic, observability coverage

### COMPAT

#### Q: Que aspectos de compatibilidade priorizar?
> **Status:** resolved
> **Answer:** Library versions + Interface contracts + Evolution strategy
>
- Versions: Python, FastAPI, Kafka drivers
- Contracts: Protocol buffers, API contracts
- Evolution: breaking changes, migration paths

**Assumptions (compat):**
- Version pinning: usar requirements-base.txt como verdade
- Transitive conflicts: resolver via downgrade mínimo
- gRPC: alinhar todos para versão 1.71.2 (conforme K8S_ISSUES analysis)
- Backward compat: manter para 2 versões minor
- Breaking changes: incrementar major version

### SECURITY

#### Q: Que aspectos de segurança priorizar (PII/privacy context)?
> **Status:** resolved
> **Answer:** Identity/Access + Data protection + Network security + Secrets
>
- Identity: AuthN, AuthZ, mTLS
- Protection: PII masking, encryption, audit logging
- Network: security, ingress, egress
- Secrets: management, vault

**Assumptions (segurança GDPR/LGPD):**
- PII classification: básico (nome, email) + business confidential
- Encryption: AES-256 at-rest, TLS 1.3 in-transit
- mTLS: obrigatório entre serviços (Istio)
- Key rotation: trimestral para encryption keys, mensal para secrets
- Audit logging: 7 anos para operações com PII
- Cert rotation: anual para mTLS certificates

## Open Items
