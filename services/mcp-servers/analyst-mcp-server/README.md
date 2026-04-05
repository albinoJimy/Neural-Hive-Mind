# Analyst MCP Server

Servidor MCP (Model Context Protocol) para analise de dados e insights no Neural Hive Mind.

## Descrição

O Analyst MCP Server fornece ferramentas especializadas para analise de dados, deteccao de anomalias e geracao de dashboards. Ele integra-se com o ecossistema Neural Hive Mind atraves do protocolo Anthropic MCP, permitindo que agentes de IA consumam capacidades avancadas de analise de forma padronizada.

Este servidor e utilizado por:
- **Analyst Agents**: Analise profunda de dados multi-fonte
- **Scout Agents**: Exploracao e deteccao de padroes anomalias
- **Dashboards**: Geracao de dados para visualizacao

## Funcionalidades

### 1. `analyze_insights` - Analise de Insights
Analisa dados com agregacoes estatisticas e filtros temporais.

**Parametros:**
- `plan_id` (str): ID do plano cognitivo
- `metrics` (list[str]): Lista de metricas para analisar
- `aggregation` (str): Tipo de agregacao (avg, min, max, sum, count, stddev, p50, p95, p99)
- `start_time` (str): Timestamp inicial (ISO format)
- `end_time` (str): Timestamp final (ISO format)
- `group_by` (str): Campo para agrupar resultados

### 2. `detect_anomalies` - Deteccao de Anomalias
Detecta anomalias em time-series usando algoritmos de ML.

**Algoritmos suportados:**
- `isolation_forest`: Isolation Forest do scikit-learn
- `zscore`: Z-Score estatistico
- `iqr`: Interquartile Range
- `moving_average`: Media movel
- `prophet`: Prophet Facebook

**Parametros:**
- `metric` (str): Nome da metrica
- `algorithm` (str): Algoritmo de deteccao (padrao: isolation_forest)
- `threshold` (float): Threshold para deteccao (padrao: 3.0)
- `sensitivity` (float): Sensibilidade 0.0-1.0 (padrao: 0.8)
- `window_size` (int): Tamanho da janela para algoritmos baseados em janela
- `time_window` (str): Janela de tempo (ex: 1h, 24h, 7d)

### 3. `query_timeseries` - Consulta de Time-Series
Consulta metricas com paginacao e filtros avancados.

**Parametros:**
- `metric` (str): Nome da metrica
- `start_time` (str): Timestamp inicial (ISO format)
- `end_time` (str): Timestamp final (ISO format)
- `page` (int): Numero da pagina (1-based, padrao: 1)
- `page_size` (int): Tamanho da pagina (padrao: 50, max: 1000)
- `filters` (dict): Filtros adicionais (ex: hostname, region)
- `aggregation` (str): Agregacao temporal (1m, 5m, 15m, 1h, 1d)

### 4. `generate_dashboard` - Geracao de Dashboards
Gera dados estruturados para dashboards de visualizacao.

**Tipos de widgets suportados:**
- `line`: Grafico de linha
- `bar`: Grafico de barras
- `pie`: Grafico de pizza
- `gauge`: Medidor analogico
- `table`: Tabela de dados
- `heatmap`: Mapa de calor
- `stat`: Stat card

**Parametros:**
- `dashboard_name` (str): Nome do dashboard
- `widgets` (list[dict]): Lista de widgets (cada um com type e metric)
- `time_range` (str): Janela de tempo padrao (ex: 1h, 24h, 7d)
- `refresh_interval` (int): Intervalo de refresh em segundos

### 5. `export_data` - Exportacao de Dados
Exporta dados em multiplos formatos para analise externa.

**Formatos suportados:**
- `json`: JSON estruturado
- `csv`: CSV com cabecalhos
- `xlsx`: Excel com multiplas sheets
- `parquet`: Apache Parquet para big data

**Parametros:**
- `metric` (str): Nome da metrica
- `format` (str): Formato de exportacao (padrao: json)
- `start_time` (str): Timestamp inicial (ISO format)
- `end_time` (str): Timestamp final (ISO format)
- `limit` (int): Limite de registros (padrao: 1000)
- `filters` (dict): Filtros adicionais

## Instalacao

### Requisitos
- Python 3.10+
- MongoDB 4.4+
- Redis 6.0+

### Instalacao via pip

```bash
# Clonar o repositorio
git clone https://github.com/albinoJimy/Neural-Hive-Mind.git
cd Neural-Hive-Mind/services/mcp-servers/analyst-mcp-server

# Instalar dependencias
pip install -e .

# Ou com dependencias de desenvolvimento
pip install -e ".[dev]"
```

## Configuracao

### Variaveis de Ambiente

Todas as variaveis usam o prefixo `ANALYST_MCP_`:

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| `SERVICE_NAME` | Nome do servico | analyst-mcp-server |
| `SERVICE_VERSION` | Versao do servico | 1.0.0 |
| `ENVIRONMENT` | Ambiente (development/staging/production) | development |
| `PORT` | Porta do servico | 3016 |
| `MONGODB_URI` | URI do MongoDB | mongodb://localhost:27017 |
| `MONGODB_DATABASE` | Nome do database | neural_hive_analyst |
| `REDIS_URL` | URL do Redis | redis://localhost:6379/0 |
| `FEATURE_STORE_URL` | URL da Feature Store | http://localhost:8006 |
| `QUERY_TIMEOUT_MS` | Timeout para consultas | 30000 |
| `ANALYSIS_TIMEOUT_MS` | Timeout para analises | 60000 |
| `DEFAULT_PAGE_SIZE` | Tamanho padrao de pagina | 50 |
| `MAX_PAGE_SIZE` | Tamanho maximo de pagina | 1000 |

### Arquivo .env

```bash
# Copiar o arquivo de exemplo
cp .env.test .env

# Editar conforme necessario
vim .env
```

## Integracoes

### MongoDB

Utilizado para armazenamento de insights e resultados de analises:

```python
# Colecao: insights
{
  "plan_id": "uuid",
  "metric": "cpu_usage",
  "value": 75.5,
  "timestamp": "2026-04-04T12:00:00Z",
  "trend": "stable"
}
```

### Redis

Utilizado como cache de metricas frequentemente acessadas:

```python
# Key pattern: metric:{name}:{window}
# TTL: Configuravel (default: 3600s)
```

### Feature Store

API externa para consulta de time-series:

```
GET /api/v1/metrics/{metric}/query
GET /api/v1/metrics/{metric}/export
```

### Prometheus (Exportacao de Metricas)

O servidor expoe metricas no formato Prometheus para monitorizacao:

```python
# Metricas disponiveis:
- analyst_mcp_requests_total
- analyst_mcp_errors_total
- analyst_mcp_latency_seconds
```

### OpenTelemetry (Tracing)

Suporte a tracing distribuido via OpenTelemetry:

```python
# Instalar opencensus
pip install opencensus[opencensus-ext-ot]

# Configurar exportador
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

## Uso

### Executar Localmente

```bash
# Modo desenvolvimento
python -m analyst_mcp_server

# Com uvicorn (para debug)
uvicorn analyst_mcp_server.server:mcp --host 0.0.0.0 --port 3016 --reload
```

### Docker

```bash
# Build da imagem
docker build -t analyst-mcp-server:1.0.0 .

# Run local
docker run -p 3016:3016 \
  -e ANALYST_MCP_MONGODB_URI=mongodb://host.docker.internal:27017 \
  -e ANALYST_MCP_REDIS_URL=redis://host.docker.internal:6379/0 \
  analyst-mcp-server:1.0.0

# Run com docker-compose
docker-compose up -d analyst-mcp-server
```

### Kubernetes (Helm)

```bash
# Adicionar repositorio (se aplicavel)
helm repo add neural-hive-mind https://charts.neural-hive-mind.com

# Instalar
helm install analyst-mcp-server ./helm/analyst-mcp-server \
  --namespace neural-hive-mind \
  --create-namespace \
  --set image.tag=1.0.0 \
  --set mongodb.uri=mongodb://mongodb-service:27017 \
  --set redis.url=redis://redis-service:6379/0

# Upgrade
helm upgrade analyst-mcp-server ./helm/analyst-mcp-server

# Uninstall
helm uninstall analyst-mcp-server -n neural-hive-mind
```

## Exemplos de Uso

### Analisar Insights

```python
from anthropic import Anthropic

client = Anthropic()

response = client.messages.create(
    model="claude-3-opus-20240229",
    tools=[
        {
            "name": "analyze_insights",
            "description": "Analisar insights de dados",
            "input_schema": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "aggregation": {"type": "string", "enum": ["avg", "min", "max", "sum"]}
                },
                "required": ["plan_id", "metrics"]
            }
        }
    ],
    messages=[{
        "role": "user",
        "content": "Analise as metricas cpu_usage e memory_usage do plano abc-123"
    }]
)
```

### Detectar Anomalias

```python
response = client.messages.create(
    model="claude-3-opus-20240229",
    tools=[...],
    messages=[{
        "role": "user",
        "content": "Detecte anomalias na metrica response_time usando isolation forest com sensibilidade 0.9"
    }]
)
```

### Gerar Dashboard

```python
response = client.messages.create(
    model="claude-3-opus-20240229",
    tools=[...],
    messages=[{
        "role": "user",
        "content": "Crie um dashboard de monitoramento com widgets line para cpu e bar para memoria"
    }]
)
```

## Desenvolvimento

### Setup do Ambiente

```bash
# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate  # Windows

# Instalar dependencias de desenvolvimento
pip install -e ".[dev]"

# Pre-commit hooks (opcional)
pip install pre-commit
pre-commit install
```

### Executar Testes

```bash
# Todos os testes
pytest tests/ -v

# Testes especificos
pytest tests/test_analyst_tools_tdd.py -v

# Com cobertura
pytest tests/ --cov=analyst_mcp_server --cov-report=html

# Testes TDD (RED-GREEN-REFACTOR)
pytest tests/test_analyst_tools_tdd.py -v --tb=short
```

### Linting e Formatacao

```bash
# Linting com ruff
ruff check src/ tests/

# Auto-correcao
ruff check --fix src/ tests/

# Formatacao com black
black src/ tests/

# Type checking com mypy
mypy src/
```

### Qualidade de Codigo

O projeto segue padroes rigidos de qualidade:

- **TDD**: Testes escritos antes da implementacao
- **Cobertura**: >80% de cobertura de testes
- **Type Hints**: Obrigatorio em funcoes publicas
- **Docstrings**: Google style para classes/metodos importantes

## API Reference

### Resource: `analyst://info`

Retorna informacoes sobre o servidor e suas capacidades.

```python
{
  "name": "Analyst MCP Server",
  "version": "1.0.0",
  "tools": [
    "analyze_insights",
    "detect_anomalies",
    "query_timeseries",
    "generate_dashboard",
    "export_data"
  ]
}
```

## Arquitetura

```
analyst-mcp-server/
├── src/
│   └── analyst_mcp_server/
│       ├── __init__.py
│       ├── __main__.py
│       ├── server.py          # Servidor MCP FastMCP
│       ├── config/
│       │   └── __init__.py    # Configuracoes (Pydantic Settings)
│       └── tools/
│           ├── __init__.py
│           └── analyst_tools.py  # 5 ferramentas de analise
├── tests/
│   ├── conftest.py            # Fixtures pytest
│   └── test_analyst_tools_tdd.py  # 45 testes TDD
├── helm/
│   └── analyst-mcp-server/    # Helm chart para Kubernetes
├── Dockerfile
├── pyproject.toml             # Configuracao Python
├── pytest.ini
└── README.md
```

## Troubleshooting

### Erro de conexao MongoDB

```bash
# Verificar se MongoDB esta rodando
mongosh --eval "db.adminCommand('ping')"

# Verificar URI
echo $ANALYST_MCP_MONGODB_URI
```

### Erro de conexao Redis

```bash
# Verificar se Redis esta rodando
redis-cli ping

# Verificar URL
echo $ANALYST_MCP_REDIS_URL
```

### Testes falhando

```bash
# Limpar cache
rm -rf .pytest_cache __pycache__

# Reinstalar dependencias
pip install -e ".[dev]" --force-reinstall

# Executar em modo verboso
pytest tests/ -vv --tb=long
```

## Licença

MIT

## Contribuicao

Este projeto faz parte do Neural Hive Mind. Por favor, consulte as diretrizes de contribuicao no repositorio principal.

## Suporte

- **Issues**: https://github.com/albinoJimy/Neural-Hive-Mind/issues
- **Documentacao**: https://github.com/albinoJimy/Neural-Hive-Mind/tree/main/docs
- **Epic INFRA-001**: https://github.com/albinoJimy/Neural-Hive-Mind/projects/1
