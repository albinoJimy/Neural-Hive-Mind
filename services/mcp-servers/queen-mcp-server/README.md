# Queen MCP Server

Servidor MCP (Model Context Protocol) para o Queen Agent do Neural Hive-Mind.

Expõe ferramentas estratégicas de orquestração e decisão via protocolo MCP Anthropic.

## Visão Geral

O Queen MCP Server permite que outros agentes e serviços interajam com o Queen Agent através do protocolo MCP, fornecendo:

- **Decisões Estratégicas**: Tomada de decisão baseada em contexto multi-fonte
- **Arbitragem de Conflitos**: Resolução de conflitos entre especialistas
- **Replanejamento de Workflows**: Acionamento de replanejamento cognitivo
- **Aprovação de Exceções**: Gestão de exceções a guardrails éticos
- **Ajuste de QoS**: Modificação dinâmica de qualidade de serviço

## Ferramentas MCP

### 1. make_decision

Tomada de decisão estratégica baseada em eventos do sistema.

**Parâmetros:**
- `event_type` (str): Tipo de evento (`consolidated_decision`, `telemetry`, `critical_incident`, `sla_violation`, `resource_saturation`)
- `source_id` (str): ID da fonte do evento
- `trigger_data` (dict): Dados do trigger
- `priority` (str, opcional): Prioridade da decisão (`low`, `normal`, `high`, `critical`)

**Retorno:**
```json
{
  "decision_id": "dec-123",
  "decision_type": "STRATEGIC",
  "action": "proceed",
  "reasoning": "Criterios atendidos",
  "confidence_score": 0.85,
  "risk_assessment": {...}
}
```

### 2. arbitrate_conflict

Arbitragem de conflitos entre decisões de múltiplos especialistas.

**Parâmetros:**
- `decisions` (list[dict]): Lista de decisões em conflito (mínimo 2)
- `conflict_description` (str, opcional): Descrição do conflito

**Retorno:**
```json
{
  "conflict_id": "conf-789",
  "resolution_strategy": "weighted_consensus",
  "final_decision": "approve",
  "rationale": "Business specialist tem maior peso neste contexto",
  "confidence": 0.9
}
```

### 3. replan_workflow

Acionamento de replanejamento de workflow/plano cognitivo.

**Parâmetros:**
- `plan_id` (str): ID do plano a ser replanejado
- `reason` (str): Razão do replanejamento
- `trigger_type` (str, opcional): Tipo de trigger (`STRATEGIC`, `MANUAL`, `ERROR`)
- `preserve_progress` (bool, opcional): Preservar progresso (default: true)
- `priority` (int, opcional): Prioridade do replanejamento (1-10, default: 5)

**Retorno:**
```json
{
  "replanning_id": "replan-456",
  "success": true,
  "new_plan_id": "plan-new-789",
  "preserved_steps": 5
}
```

### 4. approve_exception

Aprovação de exceção à política (ex: bypass de guardrail).

**Parâmetros:**
- `exception_request_id` (str): ID do pedido de exceção
- `justification` (str): Justificativa para a exceção
- `risk_score` (float): Score de risco (0.0 a 1.0)
- `requested_by` (str): Quem solicitou
- `expires_at` (str, opcional): Timestamp de expiração ISO 8601

**Retorno:**
```json
{
  "exception_request_id": "exc-123",
  "approved": true,
  "approved_by": "queen-agent",
  "approved_at": "2026-04-03T12:00:00Z",
  "conditions": ["Monitorar por 24h", "Documentar justificativa"]
}
```

### 5. adjust_qos

Ajuste de QoS (Quality of Service) de um workflow.

**Parâmetros:**
- `workflow_id` (str): ID do workflow
- `adjustment_type` (str): Tipo de ajuste (`increase_priority`, `decrease_priority`, `pause_execution`, `resume_execution`, `allocate_resources`)
- `new_priority` (int, opcional): Nova prioridade (1-10)
- `reason` (str, opcional): Razão do ajuste
- `duration_seconds` (int, opcional): Duração para pausas temporárias

**Retorno:**
```json
{
  "success": true,
  "workflow_id": "wf-123",
  "adjustment_type": "increase_priority",
  "new_priority": 8,
  "previous_priority": 5
}
```

### 6. health_check

Verifica saúde do Queen MCP Server e suas dependências.

**Parâmetros:**
- `include_services` (bool, opcional): Se deve incluir verificação de serviços externos

**Retorno:**
```json
{
  "server": "queen-mcp-server",
  "status": "healthy",
  "timestamp": "2026-04-03T12:00:00Z",
  "version": "1.0.0",
  "components": {
    "mcp_server": "healthy",
    "queen_agent": "healthy"
  },
  "queen_agent_connection": "queen-agent:8006"
}
```

## Instalação

### Requisitos

- Python 3.12+
- Queen Agent em execução (porta 8006)
- Acesso às redes internas do Neural Hive-Mind

### Dependências

```bash
pip install -r requirements.txt
```

## Configuração

Variáveis de ambiente (prefixo `QUEEN_MCP_`):

| Variável | Default | Descrição |
|----------|---------|-----------|
| `service_name` | `queen-mcp-server` | Nome do serviço |
| `service_version` | `1.0.0` | Versão do serviço |
| `port` | `3012` | Porta HTTP |
| `log_level` | `INFO` | Nível de log |
| `decision_timeout` | `30` | Timeout para decisões (segundos) |
| `queen_agent_host` | `queen-agent` | Host do Queen Agent |
| `queen_agent_port` | `8006` | Porta do Queen Agent |
| `cache_ttl_seconds` | `300` | TTL do cache (segundos) |
| `opa_url` | `http://opa:8181` | URL do OPA |
| `mongodb_uri` | `mongodb://mongodb:27017` | URI do MongoDB |
| `neo4j_uri` | `bolt://neo4j:7687` | URI do Neo4j |
| `redis_uri` | `redis://redis:6379` | URI do Redis |

## Execução

### Local

```bash
python -m src.main
```

### Docker

```bash
docker build -t queen-mcp-server:latest -f Dockerfile ..
docker run -p 3012:3012 queen-mcp-server:latest
```

### Kubernetes (Helm)

```bash
helm install queen-mcp-server ./helm
```

## Endpoints

### HTTP

- `POST /` - Endpoint JSON-RPC 2.0 para protocolo MCP
- `GET /health` - Health check
- `GET /ready` - Readiness probe
- `GET /metrics` - Métricas Prometheus

### MCP

O servidor segue o protocolo Anthropic MCP e pode ser usado por:

- Claude Desktop (configuração `mcpServers`)
- Outros serviços do Neural Hive-Mind via MCP Client SDK

## Desenvolvimento

### Testes

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=queen_mcp_server --cov-report=html

# Testes específicos
pytest tests/test_queen_tools.py::TestMakeDecisionTool
```

### Linting

```bash
# Formatação
black queen_mcp_server/

# Lint
ruff check queen_mcp_server/
```

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    Queen MCP Server                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │  FastMCP    │  │  FastAPI     │  │  BaseMCPServer      │ │
│  │  Protocol   │  │  HTTP Server │  │  (Health/Metrics)   │ │
│  └──────┬──────┘  └──────┬───────┘  └─────────────────────┘ │
│         │                │                                      │
│         └────────────────┴──────────────────┐                  │
│                                            │                  │
│              ┌──────────────────────────────┴──────┐          │
│              │      Queen MCP Tools               │          │
│              ├─────────────────────────────────────┤          │
│              │ • make_decision                    │          │
│              │ • arbitrate_conflict               │          │
│              │ • replan_workflow                  │          │
│              │ • approve_exception                │          │
│              │ • adjust_qos                       │          │
│              └──────────────────┬──────────────────┘          │
│                                 │ HTTP                          │
└─────────────────────────────────┼──────────────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │      Queen Agent          │
                    │  (gRPC/HTTP API)         │
                    │  • StrategicDecisionEngine│
                    │  • ConflictArbitrator    │
                    │  • ReplanningCoordinator  │
                    │  • ExceptionApprovalSvc  │
                    └──────────────────────────┘
```

## Integrações

### Queen Agent

O servidor se comunica com o Queen Agent via HTTP REST:

- `/api/v1/decisions` - Tomada de decisão
- `/api/v1/conflicts/arbitrate` - Arbitragem de conflitos
- `/api/v1/replanning/trigger` - Replanejamento
- `/api/v1/exceptions/approve` - Aprovação de exceções
- `/api/v1/qos/adjust` - Ajuste de QoS

### Monitoramento

- **Prometheus**: Métricas em `/metrics`
- **Structured Logging**: Logs JSON via `structlog`
- **Health Checks**: `/health` e `/ready`

## Troubleshooting

### Servidor não inicia

- Verificar se a porta 3012 está disponível
- Verificar conectividade com Queen Agent (porta 8006)
- Verificar variáveis de ambiente

### Erro de timeout na decisão

- Aumentar `QUEEN_MCP_DECISION_TIMEOUT`
- Verificar carga do Queen Agent
- Verificar latência de rede

### Testes falhando

- Garantir que todas as dependências estão instaladas
- Executar com `pytest -v` para ver detalhes
- Verificar mocks HTTP estão funcionando

## Licença

MIT - Neural Hive-Mind Project

## Contato

Para questões sobre o Queen MCP Server, consulte:
- Documentação do Neural Hive-Mind: `/docs/`
- Canal `#queen-agent` no Slack interno
