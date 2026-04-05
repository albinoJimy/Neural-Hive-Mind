# Spec: MCP Servers Implementation

> **Epic:** INFRA-001 - MCP Servers Infrastructure
> **Prioridade:** 🔴 CRÍTICA (Bloqueia Orquestração)
> **Esforço Estimado:** 26-32 dias (7-8 dias com 4 devs)
> **Data:** 2026-04-03

---

## Resumo Executivo

Implementar **8 MCP Servers** que estão faltando no Neural-Hive-Mind. Atualmente apenas 2 existem (scout, optimizer). Os MCP Servers são essenciais para a orquestração distribuída do sistema.

---

## Contexto

### Status Atual
- ✅ **Implementados:** scout-mcp-server, optimizer-mcp-server
- ❌ **Faltam:** 8 servidores críticos
- **Padrão:** BaseMCPServer já existe como template reutilizável

### Arquitetura de Referência
```
services/mcp-servers/{nome}-mcp-server/
├── src/
│   ├── {nome}_mcp_server/
│   │   ├── main.py          # Entry point
│   │   ├── server.py        # Servidor MCP
│   │   ├── tools/           # Ferramentas
│   │   │   └── {nome}_tools.py
│   │   └── config/          # Configuração
│   │       └── settings.py
│   └── shared/
│       └── mcp_base.py      # BaseMCPServer (reutilizável)
├── tests/
├── Dockerfile
├── requirements.txt
└── helm/
```

---

## User Stories

### US-001: Como Queen Agent, quero expor minhas capacidades estratégicas via MCP
Para que outros agentes possam solicitar decisões estratégicas, arbitragem de conflitos e replanejamento de workflows.

### US-002: Como Worker Agent, quero receber tarefas via MCP
Para que o orquestrador possa distribuir trabalho de forma padronizada.

### US-003: Como Execution Ticket Service, quero gerir tickets via MCP
Para que todos os serviços possam criar, atualizar e consultar tickets de execução.

### US-004: Como Guard Agent, quero expor capacidades de segurança via MCP
Para que possam ser validadas políticas de segurança e executadas remediações.

### US-005: Como Analyst Agent, quero disponibilizar insights via MCP
Para que dashboards e alertas possam consumir dados analíticos.

---

## Escopo

### IN CLUDE

#### 1. Queen MCP Server (Prioridade 1)
- **Path:** `services/mcp-servers/queen-mcp-server/`
- **Ferramentas:**
  - `make_decision`: Tomar decisões estratégicas
  - `arbitrate_conflict`: Resolver conflitos entre agentes
  - `replan_workflow`: Replanejar workflows falhados
  - `approve_exception`: Aprovar exceções à política
  - `adjust_qos`: Ajustar QoS de serviços
- **Dependências:** MongoDB, Neo4j, Redis, OPA
- **Porta:** 3012

#### 2. Worker MCP Server (Prioridade 1)
- **Path:** `services/mcp-servers/worker-mcp-server/`
- **Ferramentas:**
  - `execute_task`: Executar tarefas específicas
  - `check_dependencies`: Verificar dependências
  - `monitor_progress`: Monitorar progresso de execução
  - `handle_compensation`: Executar compensações (saga)
  - `report_status`: Reportar status de execução
- **Dependências:** Kafka, Service Registry, PostgreSQL
- **Porta:** 3013

#### 3. Execution MCP Server (Prioridade 1)
- **Path:** `services/mcp-servers/execution-mcp-server/`
- **Ferramentas:**
  - `create_ticket`: Criar execution ticket
  - `update_status`: Atualizar status do ticket
  - `query_ticket`: Consultar ticket por ID
  - `generate_token`: Gerar token JWT para tickets
  - `dispatch_webhook`: Disparar webhooks de notificação
- **Dependências:** PostgreSQL, MongoDB, Kafka
- **Porta:** 3014

#### 4. Guard MCP Server (Prioridade 2)
- **Path:** `services/mcp-servers/guard-mcp-server/`
- **Ferramentas:**
  - `validate_security`: Validar políticas de segurança
  - `scan_vulnerabilities`: Scan de vulnerabilidades
  - `detect_threats`: Detectar ameaças em tempo real
  - `check_compliance`: Verificar compliance regulatório
  - `remediate_issue`: Executar ações de remediação
- **Dependências:** OPA, Trivy, Kubernetes API
- **Porta:** 3015

#### 5. Analyst MCP Server (Prioridade 2)
- **Path:** `services/mcp-servers/analyst-mcp-server/`
- **Ferramentas:**
  - `analyze_insights`: Analisar insights de dados
  - `detect_anomalies`: Detectar anomalias em time-series
  - `query_timeseries`: Consultar dados de métricas
  - `generate_dashboard`: Gerar dados para dashboards
  - `export_data`: Exportar dados em múltiplos formatos
- **Dependências:** MongoDB, Prometheus, OpenTelemetry
- **Porta:** 3016

#### 6. Architect MCP Server (Prioridade 3)
- **Path:** `services/mcp-servers/architect-mcp-server/`
- **Ferramentas:**
  - `plan_architecture`: Planejar arquitetura de features
  - `validate_design`: Validar designs contra padrões
  - `track_evolution`: Rastrear evolução arquitetural
  - `analyze_patterns`: Analisar padrões arquiteturais
  - `generate_documentation`: Gerar documentação automática
- **Dependências:** Neo4j, MongoDB, OPA
- **Porta:** 3017

#### 7. Code Forge MCP Server (Prioridade 3)
- **Path:** `services/mcp-servers/code-forge-mcp-server/`
- **Ferramentas:**
  - `generate_artifact`: Gerar artefatos de código/IaC
  - `validate_template`: Validar templates de código
  - `optimize_generation`: Otimizar geração com caching
  - `select_template`: Selecionar templates baseado em contexto
  - `pipeline_execute`: Executar pipelines de geração
- **Dependências:** LLM providers (OpenAI/Anthropic)
- **Porta:** 3018

#### 8. Healer MCP Server (Prioridade 3)
- **Path:** `services/mcp-servers/healer-mcp-server/`
- **Ferramentas:**
  - `detect_incident`: Detectar incidentes automaticamente
  - `execute_playbook`: Executar playbooks de recuperação
  - `validate_recovery`: Validar sucesso da recuperação
  - `monitor_health`: Monitorar saúde dos serviços
  - `escalate_issue`: Escalar incidentes não resolvidos
- **Dependências:** Kafka, OPA, Chaos Mesh
- **Porta:** 3019

### OUT OF SCOPE
- Refatoração dos MCP servers existentes (scout, optimizer)
- Implementação de políticas OPA (coberto por outro spec)
- UI para gerenciamento de MCP servers

---

## Especificação Técnica

### Requisitos Funcionais

#### RQ-001: Compatibilidade MCP
- Todos os servers devem seguir o padrão FastMCP
- Implementar stdio protocol
- Suportar JSON-RPC 2.0

#### RQ-002: Observabilidade
- Health check endpoint: `/health`
- Prometheus metrics em `/metrics`
- Structured logging com context
- Distributed tracing (OpenTelemetry)

#### RQ-003: Segurança
- TLS obrigatório em produção
- Autenticação via mTLS ou JWT
- Rate limiting configurável
- Input validation com Pydantic

#### RQ-004: Resiliência
- Circuit breaker para chamadas externas
- Retry com exponential backoff
- Graceful shutdown
- Connection pooling

### Requisitos Não-Funcionais

| Métrica | Target |
|---------|--------|
| Latência (p50) | < 50ms |
| Latência (p99) | < 200ms |
| Throughput | > 1000 req/s |
| Disponibilidade | > 99.9% |
| Uptime | 24/7 |

---

## Dependencies Externas

### Serviços
- **MongoDB:** Para persistência (queen, analyst, architect)
- **PostgreSQL:** Para dados relacionais (worker, execution)
- **Redis:** Para cache e rate limiting
- **Neo4j:** Para grafos de conhecimento (queen, architect)
- **Kafka:** Para eventos assíncronos
- **OPA:** Para validação de políticas

### Bibliotecas Python
```txt
fastmcp>=0.5.0
fastapi>=0.104.0
pydantic>=2.5.0
structlog>=24.1.0
prometheus-client>=0.19.0
httpx>=0.25.0
```

---

## Testes

### Unit Tests
- Testes para cada ferramenta MCP
- Mock de dependências externas
- Cobertura mínima: 80%

### Integration Tests
- Testes com serviços reais (via docker-compose)
- Testes de comunicação MCP
- Testes de resiliência

### E2E Tests
- Fluxos completos orquestração → execução
- Cenários de falha e recuperação

---

## Deliverables

### Por MCP Server
1. [ ] Código fonte em `services/mcp-servers/{nome}-mcp-server/`
2. [ ] Testes (unit + integration)
3. [ ] Dockerfile otimizado
4. [ ] Helm chart para K8s deployment
5. [ ] Documentação README.md

### Documentação
1. [ ] API Documentation (ferramentas disponíveis)
2. [ ] Deployment Guide
3. [ ] Troubleshooting Guide

---

## Rollout Plan

### Fase 1: Prioridade Crítica (2 semanas)
1. Queen MCP Server
2. Worker MCP Server
3. Execution MCP Server

### Fase 2: Alta Prioridade (1 semana)
4. Guard MCP Server
5. Analyst MCP Server

### Fase 3: Complementar (1 semana)
6. Architect MCP Server
7. Code Forge MCP Server
8. Healer MCP Server

---

## Critérios de Aceite

### Comum a Todos
- [ ] MCP server inicia sem erros
- [ ] Health check retorna 200
- [ ] Todas as ferramentas estão registradas
- [ ] Logs estruturados com tracing ID
- [ ] Metrics em Prometheus
- [ ] Testes com >80% cobertura
- [ ] Docker image builds com sucesso
- [ ] Helm chart deploy em K8s

### Específico por Server
- [ ] Queen: Tomada de decisão funcional
- [ ] Worker: Execução de tarefas funcional
- [ ] Execution: CRUD de tickets funcional
- [ ] Guard: Validação de segurança funcional
- [ ] Analyst: Queries de timeseries funcional
- [ ] Architect: Planejamento arquitetural funcional
- [ ] Code Forge: Geração de artefatos funcional
- [ ] Healer: Detecção de incidentes funcional

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Dependência OPA não disponível | Média | Alto | Implementar fallback |
| Performance insuficiente | Baixa | Alto | Load testing antes de prod |
| Complexidade de tools Queen | Alta | Médio | Iterar com queen-agent team |

---

## Referências
- MCP Pattern existente: `services/mcp-servers/scout-mcp-server/`
- BaseMCPServer: `services/mcp-servers/shared/mcp_base.py`
- MCP Protocol: https://modelcontextprotocol.io/
