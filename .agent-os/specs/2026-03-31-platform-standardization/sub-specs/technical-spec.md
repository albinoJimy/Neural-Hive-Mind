# Technical Specification

Especificação técnica para implementação da padronização da plataforma Neural-Hive-Mind.

---

## Requisitos Técnicos

### Fase 0: Emergência (48h)

#### SEC-001: Padronizar OpenTelemetry

**Arquivos a modificar:**
- `services/*/requirements.txt` (todos com opentelemetry)
- `services/gateway-intencoes/requirements.txt`
- `services/orchestrator-dynamic/requirements.txt`

**Ação:** Atualizar todos para `opentelemetry-api==1.29.0`

**Validação:**
- [ ] CI/CD passa sem erros de dependência
- [ ] Tracing funciona entre serviços
- [ ] Logs mostram trace_id consistentes

#### SEC-002: Implementar Security Scans

**Arquivo a criar:**
- `.github/workflows/security-scan.yml`

**Conteúdo:**
```yaml
name: Security Scan
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  trivy-scan:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
```

**Validação:**
- [ ] Workflow executa em pull requests
- [ ] Vulnerabilidades são reportadas
- [ ] Build falha se CVE crítico encontrado

#### SEC-004: Remover Secrets Padrão

**Arquivos a modificar:**
- `services/*/.env.example`
- `services/*/src/config/settings.py`

**Ação:** Remover valores padrão de campos sensíveis:
- `redis_password: ""` → remover default
- `mongodb_uri: mongodb://localhost` → remover default
- `api_key: ""` → remover default

#### SEC-005: Habilitar HTTPS

**Arquivos a modificar:**
- `.env.example` dos serviços com endpoints externos
- Configurações de OTEL endpoints

**Ação:** Substituir `http://` por `https://` em produção

---

### Fase 1: Quick Wins (1-2 semanas)

#### PAD-001: Nomenclatura gRPC Consistente

**Arquivos a modificar:**
- `services/optimizer-agents/src/clients/optimizer_grpc_client.py`
- `services/consensus-engine/src/clients/optimizer_grpc_client.py`
- `services/analyst-agents/src/clients/queen_agent_grpc_client.py`
- `services/scout-agents/src/clients/queen_agent_grpc_client.py`

**Mudança:**
```python
# De:
class OptimizerGRPCClient:
class QueenAgentGRPCClient:

# Para:
class OptimizerGrpcClient:
class QueenAgentGrpcClient:
```

**Validação:**
- [ ] Todos os imports atualizados
- [ ] Testes passam
- [ ] CI/CD sem erros

#### PAD-002: Endpoints REST Kebab-case

**Arquivos a modificar:**
- `services/approval-service/src/api/routers/active_learning.py`
- `services/approval-service/src/api/routers/dashboard.py`

**Mudança:**
```python
# De:
@router.get("/activeLearning/metrics")

# Para:
@router.get("/active-learning/metrics")
```

#### PAD-003: Health Check Único

**Arquivo a criar:**
- `libraries/python/neural_hive_api/health.py`

**Conteúdo:**
```python
from pydantic import BaseModel
from typing import Literal, Dict
from datetime import datetime, timezone

class HealthResponse(BaseModel):
    """Schema de resposta de health check padronizado."""

    status: Literal["healthy", "unhealthy", "degraded"]
    timestamp: datetime
    version: str
    service: str
    dependencies: Dict[str, Literal["healthy", "unhealthy"]]

def create_health_response(
    service_name: str,
    version: str,
    dependencies: Dict[str, Literal["healthy", "unhealthy"]]
) -> HealthResponse:
    """Cria resposta de health check padronizada."""
    overall_status = (
        "healthy" if all(v == "healthy" for v in dependencies.values())
        else "degraded" if any(v == "healthy" for v in dependencies.values())
        else "unhealthy"
    )

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version=version,
        service=service_name,
        dependencies=dependencies
    )
```

**Arquivos a modificar:**
- Todos os serviços com health check

**Mudança:**
```python
# De:
@router.get("/health")
async def health():
    return {"status": "ok"}

# Para:
from neural_hive_api.health import create_health_response

@router.get("/health", response_model=HealthResponse)
async def health_check():
    return create_health_response(
        service_name="my-service",
        version="1.0.0",
        dependencies={"mongodb": "healthy", "kafka": "healthy"}
    )
```

#### VER-001: Consolidar Dependências

**Arquivo a criar:**
- `requirements-base.txt` (raiz do projeto)

**Conteúdo:**
```txt
# Dependências base consolidadas para Neural-Hive-Mind
# Atualizado: 2026-03-31

# Web Framework
fastapi==0.115.10
starlette==0.27.0

# Data Validation
pydantic==2.7.0
pydantic-settings==2.0.0

# Observability
opentelemetry-api==1.29.0
opentelemetry-sdk==1.29.0
opentelemetry-instrumentation-fastapi==0.29b0
opentelemetry-instrumentation-kafka==0.29b0
opentelemetry-instrumentation-grpc==0.29b0
structlog==24.1.0
prometheus-client==0.21.1

# Async
asyncio==3.11.0
aiohttp==3.9.0

# Kafka
aiokafka==0.10.0

# Databases
motor==3.5.1
redis==5.0.0

# gRPC
grpcio==1.68.1
grpcio-health-checking==1.68.1
grpcio-tools==1.68.1
protobuf==5.29.2

# Security
python-jose[cryptography]==4.0.0

# Testing
pytest==8.0.0
pytest-asyncio==0.23.0
pytest-cov==4.1.0
```

**Arquivos a modificar:**
- `services/*/requirements.txt`

**Mudança:** Adicionar no topo:
```txt
-r ../../requirements-base.txt

# Dependências específicas do serviço...
```

#### VER-002: Python 3.12 Padronizado

**Arquivos a modificar:**
- Todos os `Dockerfile` com Python 3.11

**Mudança:**
```dockerfile
# De:
FROM python:3.11-slim

# Para:
FROM python:3.12-slim
```

---

### Fase 2: Consolidação (3-4 semanas)

#### BIB-001: Biblioteca de Exceções Centralizada

**Estrutura:**
```
libraries/python/neural_hive_exceptions/
├── __init__.py
├── base.py
├── validation.py
├── configuration.py
└── grpc.py
```

**Conteúdo principal:**
```python
# __init__.py
from .base import NeuralHiveError, error_code
from .validation import ValidationError, ValidationErrorCode
from .configuration import ConfigurationError, ConfigErrorCode
from .grpc import GRPCError, grpc_error_to_status

__all__ = [
    "NeuralHiveError",
    "ValidationError",
    "ConfigurationError",
    "GRPCError",
    "error_code",
    "grpc_error_to_status",
]

# base.py
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

class NeuralHiveError(Exception):
    """Base exception para Neural Hive Mind."""

    def __init__(
        self,
        message: str,
        code: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Converte exceção para dicionário."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details
        }

def error_code(code: str) -> str:
    """Gera código de erro padronizado."""
    return f"NHM_{code}"
```

#### BIB-002: BaseInfrastructureSettings

**Arquivo a criar:**
- `libraries/python/neural_hive_infrastructure/config.py`

**Conteúdo:**
```python
from pydantic import Field
from pydantic_settings import BaseSettings, ConfigDict

class BaseInfrastructureSettings(BaseSettings):
    """Configurações de infraestrutura partilhadas."""

    model_config = ConfigDict(
        env_prefix="NHM_",
        env_file=".env"
    )

    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Endpoints Kafka separados por vírgula"
    )
    kafka_group_id: str = Field(
        default="neural-hive-mind",
        description="Grupo consumidor Kafka padrão"
    )

    # MongoDB
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017",
        description="URI de conexão MongoDB"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="URL de conexão Redis"
    )

    # Temporal
    temporal_host: str = Field(
        default="localhost:7233",
        description="Host do servidor Temporal"
    )

    # Observability
    otel_endpoint: str = Field(
        default="http://localhost:4317",
        description="Endpoint OTEL collector"
    )

    def get_kafka_config(self) -> Dict[str, Any]:
        """Retorna configuração Kafka como dict."""
        return {
            "bootstrap_servers": self.kafka_bootstrap_servers.split(","),
            "group_id": self.kafka_group_id,
        }

# Uso em cada serviço:
class ConsensusSettings(BaseInfrastructureSettings):
    """Configurações específicas do Consensus Engine."""

    model_config = ConfigDict(
        env_prefix="CONSENSUS_"
    )

    consensus_threshold: float = 0.7
```

---

## External Dependencies

Nenhuma nova dependência externa requerida. Todas as bibliotecas já estão em uso.

---

## Task Estimates

| Fase | Tarefas | Estimativa |
|------|---------|------------|
| Fase 0 | 4 tarefas críticas | 40-48 horas |
| Fase 1 | 6 tarefas | 40-60 horas |
| Fase 2 | 6 tarefas | 80-120 horas |
| **TOTAL** | **16 tarefas** | **160-228 horas** (~4-6 semanas) |
