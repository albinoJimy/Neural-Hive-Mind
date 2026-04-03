# Guard MCP Server

Servidor MCP (Model Context Protocol) para validações de segurança do Neural Hive Mind.

## Funcionalidades

- **validate_security**: Validar políticas de segurança OPA, RBAC e secrets
- **scan_vulnerabilities**: Scan de vulnerabilidades via Trivy
- **detect_threats**: Detectar ameaças em tempo real
- **check_compliance**: Verificar compliance regulatório (GDPR, SOC2, ISO27001)
- **remediate_issue**: Executar ações de remediação automática ou manual

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
pytest tests/ --cov=src/guard_mcp_server --cov-report=html
```

## Configuração

Variáveis de ambiente (prefixo `GUARD_MCP_`):

- `GUARD_MCP_PORT`: Porta do servidor (default: 3014)
- `GUARD_MCP_LOG_LEVEL`: Nível de log (default: INFO)
- `GUARD_MCP_GUARD_AGENT_HOST`: Host do Guard Agent (default: guard-agents)
- `GUARD_MCP_GUARD_AGENT_PORT`: Porta do Guard Agent (default: 8008)
- `GUARD_MCP_TRIVY_HOST`: Host do Trivy (default: trivy)
- `GUARD_MCP_TRIVY_PORT`: Porta do Trivy (default: 8080)

## Deploy

```bash
docker build -t guard-mcp-server:latest .
docker run -p 3014:3014 guard-mcp-server:latest
```
