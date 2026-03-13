# Template Selector - CodeForge

## Visão Geral

O **Template Selector** é o componente do `DockerfileGenerator` que seleciona e gera templates de Dockerfile otimizados baseado na linguagem e tipo de artefato.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    TEMPLATE SELECTOR                             │
├─────────────────────────────────────────────────────────────────┤
│  Entradas:                                                       │
│  ├── language      (Python, Node.js, Go, Java, TS, C#)         │
│  ├── artifact_type (MICROSERVICE, LAMBDA_FUNCTION, CLI, LIBRARY)│
│  └── framework     (fastapi, express, gin, spring, etc.)        │
├─────────────────────────────────────────────────────────────────┤
│  Saída: Dockerfile otimizado multi-stage                        │
└─────────────────────────────────────────────────────────────────┘
```

## Tipos de Artefatos

| # | Template | Descrição | Uso Típico |
|---|----------|-----------|------------|
| **1** | **microservice** | Serviço HTTP com HEALTHCHECK | APIs REST, serviços web |
| **2** | **lambda_function** | Função serverless compacta | AWS Lambda, Azure Functions |
| **3** | **cli_tool** | Ferramenta de linha de comando | Utilitários, scripts executáveis |
| **4** | **library** | Pacote/biblioteca para importação | SDKs, módulos compartilhados |
| **5** | **script** | Script executável | Automação, utilitários |

> **Nota:** Os tipos acima correspondem ao enum `ArtifactSubtype` em `src/types/artifact_types.py`.

## 1. MICROSERVICE (Default - ArtifactSubtype.microservice)

**Características:**
- Multi-stage build (builder → runtime)
- Imagem base mínima (alpine/slim)
- HEALTHCHECK configurado
- Porta exposta padrão
- Usuário não-root

**Exemplo Python FastAPI:**
```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
USER nobody
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 2. LAMBDA_FUNCTION (ArtifactSubtype.lambda_function)

**Características:**
- Single-stage (compacto)
- Sem porta exposta
- Handler específico por runtime
- Dependências mínimas
- Focado em cold-start rápido

**Exemplo Python Lambda:**
```dockerfile
FROM python:3.11-slim
WORKDIR /var/task
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lambda_handler.py .
CMD ["lambda_handler.lambda_handler"]
```

## 3. CLI_TOOL (ArtifactSubtype.cli_tool)

**Características:**
- Single-stage ou multi-stage
- ENTRYPOINT para comando principal
- Sem expor portas
- Focado em executabilidade

**Exemplo Python CLI:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cli.py .
ENTRYPOINT ["python", "cli.py"]
```

## 4. LIBRARY (ArtifactSubtype.library)

**Características:**
- Build stage apenas
- Sem runtime (não executável)
- Focado em distribuição
- Pode gerar wheel/sdist

**Exemplo Python Library:**
```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /src
COPY . .
RUN pip install build && python -m build
# Output: dist/*.whl
```

## Matriz de Suporte

| Linguagem | MICROSERVICE | LAMBDA | CLI_TOOL | LIBRARY |
|-----------|:------------:|:------:|:--------:|:-------:|
| Python | ✅ | ✅ | ✅ | ✅ |
| Node.js | ✅ | ✅ | ✅ | ✅ |
| Go | ✅ | ✅ | ✅ | ✅ |
| Java | ✅ | ✅ | ✅ | ✅ |
| TypeScript | ✅ | ✅ | ✅ | ✅ |
| C# | ✅ | ✅ | ✅ | ✅ |

## Uso

```python
from src.services.dockerfile_generator import DockerfileGenerator
from src.types.artifact_types import CodeLanguage, ArtifactSubtype

generator = DockerfileGenerator()

# Microservice Python FastAPI
dockerfile = generator.generate_dockerfile(
    language=CodeLanguage.PYTHON,
    framework="fastapi",
    artifact_type=ArtifactSubtype.MICROSERVICE
)

# Lambda Function Python
dockerfile = generator.generate_dockerfile(
    language=CodeLanguage.PYTHON,
    artifact_type=ArtifactSubtype.LAMBDA_FUNCTION
)

# CLI Tool Node.js
dockerfile = generator.generate_dockerfile(
    language=CodeLanguage.NODEJS,
    artifact_type=ArtifactSubtype.CLI_TOOL
)

# Library Go
dockerfile = generator.generate_dockerfile(
    language=CodeLanguage.GOLANG,
    artifact_type=ArtifactSubtype.LIBRARY
)
```

## Integração com MCP Tool Catalog

O Template Selector integra com o MCP Tool Catalog para seleção de ferramentas especializadas:

```python
from src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

mcp_client = MCPToolCatalogClient("http://mcp-tool-catalog:8080")

# Request ferramentas para geração de código Python
response = await mcp_client.request_tool_selection(
    ticket_id="ticket-123",
    artifact_type="CODE",  # ArtifactCategory
    language="python",      # CodeLanguage
    complexity_score=0.6,
    required_categories=["GENERATION", "VALIDATION"]
)

# Usar ferramentas selecionadas para enriquecer template
for tool in response.selected_tools:
    print(f"{tool.tool_name} - fitness: {tool.fitness_score}")
```

## Versões das Imagens Base

| Linguagem | Versão |
|-----------|--------|
| Python | 3.11-slim |
| Node.js | 20-alpine |
| Go | 1.21-alpine |
| Java | 21-slim |
| TypeScript | 20-alpine |
| C# | 8.0 |
