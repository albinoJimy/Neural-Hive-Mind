# Analyst MCP Server

Servidor MCP (Model Context Protocol) para análise de dados e insights no Neural Hive Mind.

## Descrição

O Analyst MCP Server fornece ferramentas para:

- **analyze_insights**: Analisar insights de dados com agregações variadas
- **detect_anomalies**: Detectar anomalias em time-series usando ML
- **query_timeseries**: Consultar métricas com paginação e filtros
- **generate_dashboard**: Gerar dados para dashboards de visualização
- **export_data**: Exportar dados em JSON, CSV, XLSX ou Parquet

## Tecnologias

- **FastMCP**: Framework oficial MCP
- **pandas/numpy**: Manipulação de dados
- **scikit-learn**: Algoritmos de detecção de anomalias
- **MongoDB**: Armazenamento de insights
- **Redis**: Cache de métricas

## Instalação

```bash
pip install -e .
```

## Desenvolvimento

```bash
# Instalar dependências de desenvolvimento
pip install -e ".[dev]"

# Rodar testes
pytest tests/

# Formatar código
black src/ tests/

# Linting
ruff check src/ tests/
```

## Configuração

Variáveis de ambiente (prefixo `ANALYST_MCP_`):

- `MONGODB_URI`: URI do MongoDB (padrão: mongodb://localhost:27017)
- `MONGODB_DATABASE`: Nome do database (padrão: neural_hive_analyst)
- `REDIS_URL`: URL do Redis (padrão: redis://localhost:6379/0)
- `FEATURE_STORE_URL`: URL da Feature Store (padrão: http://localhost:8006)

## Docker

```bash
docker build -t analyst-mcp-server .
docker run -p 8000:8000 analyst-mcp-server
```

## Testes TDD

Este servidor segue TDD rigoroso:

1. **RED**: Testes escritos antes da implementação
2. **GREEN**: Código mínimo para passar nos testes
3. **REFACTOR**: Melhoria contínua da qualidade

```bash
# 45 testes cobrindo todas as ferramentas
pytest tests/test_analyst_tools_tdd.py -v
```

## Licença

MIT
