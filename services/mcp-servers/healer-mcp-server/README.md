# Healer MCP Server

Servidor MCP (Model Context Protocol) para auto-recuperação do Neural Hive Mind.

## Funcionalidades

- **detect_incident**: Detectar incidentes automaticamente baseado em métricas
- **execute_playbook**: Executar playbooks de recuperação automatizada
- **validate_recovery**: Validar sucesso da recuperação executada
- **monitor_health**: Monitorar saúde dos serviços continuamente
- **escalate_issue**: Escalar incidentes não resolvidos para times apropriados

## Desenvolvimento

### Instalar dependências

```bash
pip install -r requirements.txt
```

### Executar testes

```bash
pytest tests/ -v
```

### Executar com cobertura

```bash
pytest tests/ --cov=src/healer_mcp_server --cov-report=html
```

## Configuração

Variáveis de ambiente (prefixo `HEALER_MCP_`):

- `HEALER_MCP_PORT`: Porta do servidor (default: 3019)
- `HEALER_MCP_LOG_LEVEL`: Nível de log (default: INFO)
- `HEALER_MCP_HEALER_AGENT_HOST`: Host do Self-Healing Engine (default: self-healing-engine)
- `HEALER_MCP_HEALER_AGENT_PORT`: Porta do Self-Healing Engine (default: 8009)
- `HEALER_MCP_TIMEOUT`: Timeout para operações (default: 300)

## Deploy

```bash
docker build -t healer-mcp-server:latest .
docker run -p 3019:3019 healer-mcp-server:latest
```

## Ferramentas Detalhadas

### detect_incident

Detecta incidentes automaticamente baseado em métricas dos serviços.

**Parâmetros:**
- `service`: Nome do serviço afetado (obrigatório)
- `incident_type`: Tipo do incidente (pod_crash_loop, high_memory_usage, etc.)
- `metrics`: Métricas relevantes para detecção

**Retorna:**
- `incident_id`: ID único do incidente
- `severity`: Severidade (LOW, MEDIUM, HIGH, CRITICAL)
- `suggested_playbook`: Playbook sugerido para recuperação
- `auto_recoverable`: Se o incidente é recuperável automaticamente

### execute_playbook

Executa playbook de recuperação para um incidente.

**Parâmetros:**
- `incident_id`: ID do incidente (obrigatório)
- `playbook_id`: ID do playbook a executar
- `parameters`: Parâmetros específicos do playbook

**Retorna:**
- `execution_id`: ID único da execução
- `execution_status`: Status da execução (completed, failed, rollback_completed)
- `recovery_achieved`: Se a recuperação foi bem-sucedida
- `steps_executed`: Lista de passos executados

### validate_recovery

Valida sucesso da recuperação executada.

**Parâmetros:**
- `incident_id`: ID do incidente (obrigatório)
- `playbook_id`: ID do playbook executado

**Retorna:**
- `recovery_status`: Status da recuperação (SUCCESS, PARTIAL, FAILED)
- `all_checks_passed`: Se todos os checks passaram
- `can_close_incident`: Se o incidente pode ser fechado
- `validation_checks`: Lista de validações executadas

### monitor_health

Monitora saúde de um serviço.

**Parâmetros:**
- `service`: Nome do serviço a monitorizar (obrigatório)
- `checks`: Lista de checks (liveness, readiness, startup)

**Retorna:**
- `overall_status`: Status geral (healthy, degraded, unhealthy)
- `endpoints`: Lista de endpoints verificados
- `metrics`: Métricas atuais do serviço
- `issues`: Lista de problemas detectados

### escalate_issue

Escala incidente não resolvido para time apropriado.

**Parâmetros:**
- `incident_id`: ID do incidente (obrigatório)
- `target_team`: Time alvo (sre_team, platform_team, etc.)
- `urgency`: Urgência (low, medium, high, critical)
- `reason`: Razão do escalamento
- `context`: Contexto adicional sobre o incidente

**Retorna:**
- `escalation_id`: ID único do escalamento
- `status`: Status do escalamento (pending, acknowledged, resolved)
- `ticket_url`: URL do ticket criado
- `notification_sent`: Se notificações foram enviadas

## Desenvolvimento TDD

Este servidor segue TDD rigoroso:

1. **RED**: Testes escritos primeiro em `tests/test_healer_tools_tdd.py`
2. **GREEN**: Implementação mínima em `src/healer_mcp_server/tools/healer_tools.py`
3. **REFACTOR**: Melhorias de design com testes passando

Todos os testes usam mocks para isolar a unidade sendo testada.
