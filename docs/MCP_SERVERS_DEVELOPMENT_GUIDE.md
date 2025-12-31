# Guia de Desenvolvimento de MCP Servers

## Introdução

Este guia descreve como criar novos MCP Servers para o Neural Hive-Mind usando o framework FastMCP.

## Estrutura do Projeto

```
services/mcp-servers/
├── {nome}-mcp-server/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py           # Entry point
│   │   ├── server.py         # Configuração FastMCP
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   └── {nome}_tools.py
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   └── settings.py
│   │   └── clients/          # (opcional)
│   │       └── {api}_client.py
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
└── shared/
    ├── __init__.py
    └── mcp_base.py           # Classe base compartilhada
```

## Criando um Novo MCP Server

### 1. Configuração (settings.py)

```python
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações via environment variables."""

    # Informações do serviço
    service_name: str = "meu-mcp-server"
    service_version: str = "1.0.0"

    # Servidor HTTP
    http_host: str = "0.0.0.0"
    http_port: int = 3000

    # Configurações específicas da ferramenta
    tool_api_url: str = "http://ferramenta:8080"
    tool_api_token: str = ""
    tool_timeout: int = 60

    # Observability
    otel_endpoint: str = "http://otel-collector:4317"
    log_level: str = "INFO"

    # CORS
    cors_origins: str = "*"

    class Config:
        env_prefix = ""
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### 2. Implementar Ferramentas (tools/{nome}_tools.py)

```python
from typing import Any
from fastmcp import FastMCP


def register_minha_tools(mcp: FastMCP) -> None:
    """Registra ferramentas no servidor MCP."""

    @mcp.tool()
    async def minha_ferramenta(
        parametro1: str,
        parametro2: int = 10
    ) -> dict[str, Any]:
        """
        Descrição da ferramenta.

        Args:
            parametro1: Descrição do parâmetro 1
            parametro2: Descrição do parâmetro 2

        Returns:
            Resultado da execução
        """
        # Implementação
        resultado = await executar_operacao(parametro1, parametro2)

        return {
            "success": True,
            "data": resultado
        }
```

### 3. Configurar Servidor (server.py)

```python
import structlog
from fastmcp import FastMCP

from .config import get_settings
from .tools import register_minha_tools

logger = structlog.get_logger(__name__)

settings = get_settings()
mcp = FastMCP(
    name="Meu MCP Server",
    version=settings.service_version,
    description="Descrição do servidor"
)


@mcp.resource("meu-server://info")
def get_info() -> str:
    """Informações sobre o servidor."""
    return """
    Meu MCP Server
    ==============

    Ferramentas disponíveis:
    - minha_ferramenta: Descrição
    """


# Registrar ferramentas
register_minha_tools(mcp)

logger.info(
    "mcp_server_initialized",
    name=mcp.name,
    version=settings.service_version
)
```

### 4. Entry Point (main.py)

```python
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI

from .config import get_settings
from .server import mcp

sys.path.insert(0, "/app")
from shared.mcp_base import BaseMCPServer

logger = structlog.get_logger(__name__)
settings = get_settings()


class MeuMCPServer(BaseMCPServer):
    """Servidor MCP customizado."""

    async def initialize(self) -> None:
        """Inicializa recursos."""
        logger.info("server_resources_initialized")

    async def cleanup(self) -> None:
        """Libera recursos."""
        logger.info("server_cleanup_complete")


server = MeuMCPServer(
    name=settings.service_name,
    version=settings.service_version,
    allowed_origins=settings.cors_origins.split(",")
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await server.initialize()
    server.set_ready(True)
    yield
    server.set_ready(False)
    await server.cleanup()


app = FastAPI(
    title="Meu MCP Server",
    version=settings.service_version,
    lifespan=lifespan
)

server.setup_cors(app)
server.setup_health_checks(app)
app.mount("/mcp", mcp.get_app())


@app.post("/")
async def jsonrpc_endpoint(request: dict) -> dict:
    return await mcp.handle_jsonrpc(request)


def main() -> None:
    uvicorn.run(
        "src.main:app",
        host=settings.http_host,
        port=settings.http_port,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()
```

### 5. Dockerfile

```dockerfile
FROM python:3.11-slim as builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash mcp-user

WORKDIR /app
COPY --chown=mcp-user:mcp-user . .
COPY --chown=mcp-user:mcp-user ../shared /app/shared

USER mcp-user

EXPOSE 3000 9091

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

CMD ["python", "-m", "src.main"]
```

### 6. Requirements

```text
fastmcp>=0.2.0
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
structlog>=24.1.0
prometheus-client>=0.19.0
aiohttp>=3.9.0
```

## Testes

### Teste Unitário

```python
import pytest
from fastmcp import FastMCP
from src.tools.minha_tools import register_minha_tools


@pytest.fixture
def mcp():
    server = FastMCP(name="Test", version="1.0.0")
    register_minha_tools(server)
    return server


@pytest.mark.asyncio
async def test_minha_ferramenta(mcp):
    tools = await mcp.list_tools()
    assert any(t.name == "minha_ferramenta" for t in tools)
```

### Teste de Integração

```python
import pytest
import httpx


@pytest.mark.asyncio
async def test_health_check():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:3000/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_jsonrpc_call():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:3000",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "minha_ferramenta",
                    "arguments": {"parametro1": "valor"}
                }
            }
        )
        assert response.status_code == 200
        result = response.json()
        assert "result" in result
```

## Helm Chart

Criar estrutura em `helm-charts/mcp-servers/{nome}-mcp-server/`:

```
{nome}-mcp-server/
├── Chart.yaml
├── values.yaml
├── values-local.yaml
└── templates/
    ├── _helpers.tpl
    ├── deployment.yaml
    ├── service.yaml
    ├── servicemonitor.yaml
    ├── hpa.yaml
    └── networkpolicy.yaml
```

## Registro no MCP Tool Catalog

Adicionar entrada em `helm-charts/mcp-tool-catalog/values.yaml`:

```yaml
mcpServers:
  minha-ferramenta-001: "http://meu-mcp-server.neural-hive-mcp.svc.cluster.local:3000"
```

## Boas Práticas

1. **Docstrings**: Sempre documentar ferramentas com docstrings claras
2. **Validação**: Validar parâmetros de entrada antes de processar
3. **Timeouts**: Configurar timeouts apropriados para operações externas
4. **Logging**: Usar logging estruturado com contexto
5. **Métricas**: Registrar métricas de execução
6. **Erros**: Retornar erros descritivos com códigos apropriados
7. **Testes**: Cobrir casos de sucesso e erro
