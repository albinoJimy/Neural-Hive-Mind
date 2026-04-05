# Architect MCP Server

Servidor MCP (Model Context Protocol) para análise arquitetural do Neural Hive Mind.

## Funcionalidades

- **plan_architecture**: Planejar arquitetura de novas features
- **validate_design**: Validar designs contra padrões e best practices
- **track_evolution**: Rastrear evolução arquitetural do sistema
- **analyze_patterns**: Analisar padrões e anti-patterns no código
- **generate_documentation**: Gerar documentação arquitetural automática

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
pytest tests/ --cov=src/architect_mcp_server --cov-report=html
```

## Configuração

Variáveis de ambiente (prefixo `ARCHITECT_MCP_`):

- `ARCHITECT_MCP_PORT`: Porta do servidor (default: 3017)
- `ARCHITECT_MCP_LOG_LEVEL`: Nível de log (default: INFO)
- `ARCHITECT_MCP_ARCHITECT_AGENT_HOST`: Host do Architect Agent (default: architect-agent)
- `ARCHITECT_MCP_ARCHITECT_AGENT_PORT`: Porta do Architect Agent (default: 8009)

## Deploy

```bash
docker build -t architect-mcp-server:latest .
docker run -p 3014:3017 architect-mcp-server:latest
```
