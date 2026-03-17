# CLAUDE.md — Contexto Neural-Hive-Mind

Este ficheiro contém as regras e contexto para todos os agentes de IA que trabalham neste projecto.

---

## Sobre o Projecto

**Nome:** Neural-Hive-Mind (NHM)
**Descrição:** Sistema de IA distribuído multi-agente com cognitive pipeline, orquestração via Kafka/Temporal, e consenso especializado.
**Stack:** Python 3.12+, FastAPI, Kafka, MongoDB, Redis, Neo4j, Temporal, Kubernetes
**Repository:** https://github.com/albinoJimy/Neural-Hive-Mind.git

---

## Regras do Agente (OBRIGATÓRIAS)

### Idioma
1. Documentar sempre em **português**.

### Âmbito de Trabalho
2. Fazer **exatamente** o que foi solicitado; nada mais, nada menos.

### Gestão de Ficheiros
3. NUNCA criar ficheiros a menos que sejam **absolutamente necessários**.
4. SEMPRE preferir **editar um ficheiro existente** a criar um novo.
5. NUNCA criar proactivamente ficheiros de documentação (`*.md`) ou README.

### Evitar Duplicações
6. Antes de criar um novo componente, **SEMPRE validar** se já existe um componente com a mesma capacidade.

### Testes
7. **Nunca modificar ficheiros** em `tests/` — são o contrato de implementação.
8. Cada função nova tem **teste unitário** correspondente.
9. Cada ticket tem **teste de integração** correspondente (E2E com Docker compose).

### Qualidade Antes do Commit
10. Correr **linting** (ruff) e **formatação** (black) antes de qualquer commit.
11. Verificar que nenhum **segredo** está presente nos ficheiros modificados.
12. Commits apenas **após todos os testes estarem verdes**.
13. Nenhuma feature sem **spec correspondente** em `docs/specs/`.

### Branching
14. **Nunca fazer push directo** para main/master.
15. Cada ticket é desenvolvido numa branch própria: `feat/TICKET-[ID]-[descricao]`
16. Antes do commit final, **sincronizar**: `git pull --rebase origin main`

### Deploy e CI/CD
17. Para fazer deploy, basta **commit + push** — CI/CD é automático.
18. Após o push, **verificar o status do pipeline**.

---

## Arquitectura do Sistema

### Fluxo Principal (Cognitive Pipeline)
```
User Intent → Gateway → STE → Consensus → Orchestrator → Workers → Result
              ↓           ↓         ↓           ↓          ↓
           (NLU)    (Translate) (Merge)   (Tickets)  (Exec)
```

### Serviços Core (8 principais)

| Serviço | Propósito | Porta |
|---------|-----------|-------|
| `gateway-intencoes` | API Gateway, NLU, roteamento | 8000 |
| `semantic-translation-engine` | Tradução de intenções para formato interno | 8001 |
| `consensus-engine` | Consenso entre especialistas | 8002 |
| `orchestrator-dynamic` | Orquestração de workflows via Temporal | 8003 |
| `approval-service` | Aprovação humana de decisões | 8004 |
| `worker-agents` | Execução de tarefas (query, transform, validate) | 8005 |
| `queen-agent` | Supervisor e coordenação de agentes | 8006 |
| `service-registry` | Descoberta e registo de serviços | 8007 |

### Agentes Especializados (8)

| Serviço | Propósito |
|---------|-----------|
| `analyst-agents` | Análise profunda de dados |
| `scout-agents` | Exploração e descoberta |
| `guard-agents` | Validação e segurança |
| `optimizer-agents` | Otimização de processos |
| `self-healing-engine` | Auto-recuperação |
| `execution-ticket-service` | Gestão de tickets de execução |
| `sla-management-system` | Monitorização de SLA |
| `code-forge` | Geração de código/IaC |

### Bibliotecas Python (8)

| Biblioteca | Propósito |
|-----------|-----------|
| `neural_hive_domain` | Domínio e modelos partilhados |
| `neural_hive_specialists` | Framework de especialistas |
| `neural_hive_agent_sdk` | SDK para criar agentes |
| `neural_hive_observability` | Logging, métricas, tracing |
| `neural_hive_ml` | Modelos ML e feature engineering |
| `neural_hive_resilience` | Circuit breakers, retries |
| `neural_hive_risk_scoring` | Avaliação de risco |

### Infraestrutura e Ferramentas

| Componente | Propósito |
|------------|-----------|
| `mcp-servers` | MCP (Model Context Protocol) Servers |
| `mcp-tool-catalog` | Catálogo de ferramentas MCP |
| `opa` | Open Policy Agent para autorização |
| `memory-layer-api` | Persistência de memória |
| `explainability-api` | Explicabilidade de decisões |

### ML Pipelines

| Componente | Propósito |
|------------|-----------|
| `training/` | Scripts de treino de modelos |
| `inference/` | Serviços de inferência |
| `feature_store/` | Armazenamento de features |
| `online_learning/` | Aprendizado online |

---

## Stack Técnica Detalhada

### Backend
- **Python:** 3.12+
- **Framework:** FastAPI
- **Async:** asyncio + motor (MongoDB async)
- **Mensageria:** Kafka (aiokafka)
- **Orquestração:** Temporal
- **API:** REST + gRPC

### Base de Dados
- **MongoDB:** Dados de especialistas, feedbacks, planos cognitivos
- **Redis:** Cache, rate limiting, state temporal
- **Neo4j:** Grafos de conhecimento (connections API)

### Testing
- **Unit:** pytest + pytest-asyncio
- **Integração:** Docker Compose
- **Contracts:** Protobuf (gRPC)

### DevOps
- **Container:** Docker + Docker Compose
- **Orquestração:** Kubernetes (Helm)
- **CI/CD:** GitHub Actions
- **Observabilidade:** Prometheus + Grafana + OpenTelemetry

---

## Convenções de Código

### Python
- **snake_case** para funções, variáveis, ficheiros
- **PascalCase** para classes
- **UPPER_SNAKE_CASE** para constantes
- **Type hints** obrigatório em funções públicas
- **Docstrings** Google style para classes/métodos importantes

### Async/Await
- Sempre usar `async def` para I/O
- Usar `asyncio.gather()` para paralelismo
- Timeout em todas as chamadas externas

### Logging
- Usar `structlog` (já configurado em `neural_hive_observability`)
- Logs estruturados com contexto
- Níveis: debug, info, warning, error, critical

### Erro Handling
- Sempre usar `try/except` em código async
- Retries via `tenacity` ou resiliency patterns
- Circuit breaker para chamadas externas

---

## Scripts Disponíveis

| Comando | Descrição |
|---------|-----------|
| `pytest` | Correr unit tests |
| `ruff check .` | Linter |
| `black .` | Formatador |
| `docker-compose up -d` | Subir serviços locais |
| `make proto` | Compilar protos (gRPC) |

---

## Variáveis de Ambiente Necessárias

Ver `.env.test` para a lista completa. Principais:

- `KAFKA_BOOTSTRAP_SERVERS`
- `MONGODB_URL`
- `REDIS_URL`
- `TEMPORAL_HOST`
- `NEO4J_URI`
- `OTEL_EXPORTER_OTLP_ENDPOINT`

---

## Estado Actual (Fase 3)

- **Fase Actual:** Fase 3 — Aprendizado e Evolução
- **Completude:** ~75%
- **Epic Activo:** Enriquecimento de Feedback com Semantic Features
- **Último Deploy:** v7 do Approval Model (2026-03-16)

### Especialistas Activos
- Text Analysis Specialist
- Code Analysis Specialist
- Data Analysis Specialist
- Security Specialist

Ver `/docs/feature-map.md` e MEMORY.md para detalhes.
