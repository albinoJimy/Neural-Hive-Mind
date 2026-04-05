# Code Forge MCP Server

Servidor MCP (Model Context Protocol) para geração de código e Infraestrutura como Código (IaC) no Neural Hive Mind.

## Descrição

O Code Forge MCP Server fornece ferramentas para geração inteligente de artefatos de código, validação de templates, otimização com caching e execução de pipelines de geração.

## Funcionalidades

### 1. `generate_artifact`
Gerar artefatos de código/IaC usando LLMs.

**Parâmetros:**
- `artifact_type`: Tipo do artefato (function, class, module, iac, etc.)
- `description`: Descrição do que deve ser gerado
- `language`: Linguagem de programação
- `requirements`: Lista de requisitos específicos (opcional)
- `context`: Contexto adicional (opcional)
- `run_quality_check`: Executar verificação de qualidade (opcional)

**Linguagens suportadas:**
python, javascript, typescript, go, rust, java, yaml, json, terraform, kubernetes, dockerfile, bash, sql, html, css

### 2. `validate_template`
Validar templates de código antes do uso.

**Parâmetros:**
- `template`: Template string para validar
- `template_type`: Tipo do template (jinja2, fstring, yaml, json)
- `variables`: Variáveis para renderizar o template
- `schema`: Schema JSON para validação adicional (opcional)

### 3. `optimize_generation`
Otimizar geração com caching inteligente.

**Parâmetros:**
- `cache_key`: Chave única para cache
- `description`: Descrição do artefato
- `language`: Linguagem de programação
- `ttl_seconds`: TTL customizado para cache (opcional)
- `invalidate`: Invalidar cache existente (opcional)
- `use_semantic_search`: Buscar semanticamente artefatos similares (opcional)
- `compress`: Usar compressão no cache (opcional)
- `include_stats`: Incluir estatísticas de cache (opcional)

### 4. `select_template`
Selecionar templates baseado em contexto.

**Parâmetros:**
- `language`: Linguagem de programação
- `category`: Categoria do template (opcional)
- `design_pattern`: Padrão de design (opcional)
- `tags`: Tags para filtrar (opcional)
- `complexity`: Nível de complexidade (opcional)
- `template_name`: Nome específico do template (opcional)
- `version`: Versão do template (opcional)
- `context`: Contexto adicional para recomendação (opcional)

### 5. `pipeline_execute`
Executar pipelines de geração com múltiplos estágios.

**Parâmetros:**
- `stages`: Lista de estágios do pipeline
- `parallel`: Executar estágios independentes em paralelo (opcional)
- `timeout_seconds`: Timeout para execução completa (opcional)

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Criar ficheiro `.env`:

```bash
CODE_FORGE_MCP_SERVICE_NAME=code-forge-mcp-server
CODE_FORGE_MCP_SERVICE_VERSION=1.0.0
CODE_FORGE_MCP_PORT=3018

# MongoDB
CODE_FORGE_MCP_MONGODB_URI=mongodb://localhost:27017
CODE_FORGE_MCP_MONGODB_DATABASE=neural_hive_code_forge

# Redis
CODE_FORGE_MCP_REDIS_URL=redis://localhost:6379/2

# Template Store
CODE_FORGE_MCP_TEMPLATE_STORE_URL=http://localhost:8009

# LLM Providers
CODE_FORGE_MCP_ANTHROPIC_API_KEY=your-key-here

# Caching
CODE_FORGE_MCP_CACHE_TTL_SECONDS=3600
CODE_FORGE_MCP_ENABLE_CACHE=true
```

## Execução

### Local
```bash
python -m code_forge_mcp_server
```

### Docker
```bash
docker build -t code-forge-mcp-server .
docker run -p 3018:3018 --env-file .env code-forge-mcp-server
```

## Testes

```bash
# Executar todos os testes
pytest

# Com coverage
pytest --cov=code_forge_mcp_server --cov-report=html
```

## Arquitetura

```
code-forge-mcp-server/
├── src/
│   └── code_forge_mcp_server/
│       ├── __init__.py
│       ├── __main__.py
│       ├── server.py          # Servidor FastMCP
│       ├── config/            # Configurações Pydantic
│       └── tools/             # Implementação das ferramentas
│           └── code_forge_tools.py
├── tests/
│   └── test_code_forge_tools_tdd.py  # Testes TDD
├── requirements.txt
├── pyproject.toml
├── Dockerfile
└── README.md
```

## Integração com Neural Hive Mind

O Code Forge MCP Server integra-se com:

- **Architect Agent**: Recebe especificações arquiteturais
- **Template Store**: Busca templates validados
- **Consensus Engine**: Valida decisões de geração
- **Approval Service**: Solicita aprovação para artefatos críticos

## Fluxo TDD

Este servidor segue rigorosamente o ciclo TDD:

1. **RED**: Testes escritos primeiro em `tests/test_code_forge_tools_tdd.py`
2. **GREEN**: Implementação mínima em `src/code_forge_mcp_server/tools/code_forge_tools.py`
3. **REFACTOR**: Melhoria contínua do design

## License

MIT
