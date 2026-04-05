# Development Guide - ML Inference API

Guia para desenvolvedores trabalhando no ML Inference API.

## Índice

- [Setup do Ambiente](#setup-do-ambiente)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Executar Testes](#executar-testes)
- [Adicionar Novos Endpoints](#adicionar-novos-endpoints)
- [Padrões de Código](#padrões-de-código)
- [Debugging](#debugging)
- [Workflow de Contribuição](#workflow-de-contribuição)

---

## Setup do Ambiente

### Pré-requisitos

- Python 3.10+
- Git
- Make (opcional)
- Docker (opcional)

### 1. Clone o Repositório

```bash
git clone https://github.com/albinojimy/Neural-Hive-Mind.git
cd Neural-Hive-Mind/services/ml-inference-api
```

### 2. Criar Ambiente Virtual

```bash
python3.10 -m venv venv
source venv/bin/activate
```

### 3. Instalar Dependências

```bash
# Dependências de produção
pip install -r requirements.txt

# Dependências de desenvolvimento
pip install -e ".[dev]"

# Ou instalar tudo
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov pytest-mock ruff black mypy
```

### 4. Configurar Ambiente

```bash
cp .env.example .env
# Editar .env conforme necessário
```

### 5. Preparar Diretório de Modelos

```bash
mkdir -p ml_models
# Copiar modelo de desenvolvimento se disponível
```

### 6. Verificar Instalação

```bash
# Executar serviço
python -m src.main

# Em outro terminal, testar
curl http://localhost:8010/health
```

---

## Estrutura do Projeto

```
ml-inference-api/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point FastAPI
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py         # Configurações Pydantic
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Schemas Pydantic
│   ├── services/
│   │   ├── __init__.py
│   │   ├── predictor_service.py    # Wrapper do modelo
│   │   ├── batch_engine.py         # Processamento batch
│   │   └── circuit_breaker.py      # Circuit breaker
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py               # Health endpoints
│   │   └── inference.py            # Inference endpoints
│   ├── observability/
│   │   ├── __init__.py
│   │   └── metrics.py              # Métricas Prometheus
│   └── utils/
│       ├── __init__.py
│       └── gpu_wrapper.py          # GPU utilities
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Fixtures pytest
│   ├── unit/
│   │   ├── test_predictor_service.py
│   │   ├── test_batch_engine.py
│   │   └── test_circuit_breaker.py
│   └── integration/
│       └── test_api.py
├── docs/
│   ├── API.md
│   ├── DEPLOYMENT.md
│   ├── DEVELOPMENT.md
│   └── METRICS.md
├── .env.example
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── Makefile
└── README.md
```

### Arquitetura em Camadas

```
┌─────────────────────────────────────┐
│         API Layer (FastAPI)         │
├─────────────────────────────────────┤
│         Services Layer              │
│  ┌─────────┐  ┌────────┐  ┌──────┐ │
│  │Predictor│  │ Batch  │  │Circuit│ │
│  │ Service │  │ Engine │  │Breaker│ │
│  └─────────┘  └────────┘  └──────┘ │
├─────────────────────────────────────┤
│         ML Model Layer              │
│  (ApprovalPredictor / MLflow)       │
├─────────────────────────────────────┤
│    Observability (Metrics/Logs)     │
└─────────────────────────────────────┘
```

---

## Executar Testes

### Estrutura de Testes

- **Unitários:** Testam funções/métodos isolados
- **Integração:** Testam endpoints da API
- **Fixtures:** Compartilhadas em `tests/conftest.py`

### Comandos de Teste

```bash
# Todos os testes
pytest

# Com cobertura
pytest --cov=src --cov-report=term-missing

# Com relatório HTML
pytest --cov=src --cov-report=html

# Apenas testes unitários
pytest tests/unit/

# Apenas testes de integração
pytest tests/integration/

# Teste específico
pytest tests/unit/test_predictor_service.py::test_predict_success

# Teste com verbose
pytest -v

# Teste com output de print
pytest -s
```

### Escrever Testes

#### Teste Unitário

```python
import pytest
from unittest.mock import Mock, patch

from src.services.predictor_service import PredictorService
from src.models.schemas import PredictRequest

@pytest.mark.asyncio
async def test_predict_success(mock_predictor_service):
    """Testa predição bem-sucedida."""
    # Arrange
    request = PredictRequest(
        intent_text="Create user account",
        specialist_confidence=0.75
    )

    # Act
    result = await mock_predictor_service.predict(
        intent_text=request.intent_text,
        specialist_confidence=request.specialist_confidence
    )

    # Assert
    assert result["decision"] in ["approve", "reject", "review_required"]
    assert 0.0 <= result["confidence"] <= 1.0
```

#### Teste de Integração

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_predict_endpoint(client: AsyncClient):
    """Testa endpoint de predição."""
    response = await client.post(
        "/api/v1/inference/predict",
        json={
            "intent_text": "Create user account",
            "specialist_confidence": 0.75
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "decision" in data
    assert "confidence" in data
```

### Fixtures

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from src.main import app

@pytest.fixture
async def client():
    """Cliente HTTP assíncrono para testes."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_predictor_service():
    """Mock do PredictorService."""
    service = Mock()
    service.predict.return_value = {
        "decision": "approve",
        "confidence": 0.8,
        "probabilities": {"approve": 0.8, "reject": 0.2}
    }
    return service
```

---

## Adicionar Novos Endpoints

### Passo 1: Definir Schemas

```python
# src/models/schemas.py
from pydantic import BaseModel, Field

class NewFeatureRequest(BaseModel):
    """Request para nova feature."""
    param1: str = Field(..., description="Parâmetro 1")
    param2: float = Field(default=0.5, ge=0.0, le=1.0)

class NewFeatureResponse(BaseModel):
    """Response para nova feature."""
    result: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)
```

### Passo 2: Implementar Lógica

```python
# src/services/new_feature_service.py
import structlog

logger = structlog.get_logger()

class NewFeatureService:
    """Serviço para nova feature."""

    async def process(self, param1: str, param2: float) -> dict:
        """Processa requisição."""
        logger.info("processing_new_feature", param1=param1, param2=param2)

        # Lógica aqui
        result = f"Processed: {param1} with {param2}"

        return {"result": result}
```

### Passo 3: Criar Endpoint

```python
# src/api/new_feature.py
from fastapi import APIRouter, Depends
from ..models.schemas import NewFeatureRequest, NewFeatureResponse
from ..services.new_feature_service import NewFeatureService

router = APIRouter()

@router.post(
    "/api/v1/new-feature",
    response_model=NewFeatureResponse,
    summary="Nova feature",
    description="Descrição da nova feature"
)
async def new_feature(
    request: NewFeatureRequest,
    service: NewFeatureService = Depends()
) -> NewFeatureResponse:
    """Endpoint para nova feature."""
    result = await service.process(request.param1, request.param2)
    return NewFeatureResponse(**result)
```

### Passo 4: Registrar Router

```python
# src/api/__init__.py
from . import health, inference, new_feature

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(inference.router, tags=["Inference"])
api_router.include_router(new_feature.router, tags=["New Feature"])
```

### Passo 5: Adicionar Testes

```python
# tests/integration/test_new_feature.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_new_feature_endpoint(client: AsyncClient):
    """Testa nova feature."""
    response = await client.post(
        "/api/v1/new-feature",
        json={"param1": "test", "param2": 0.75}
    )
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
```

---

## Padrões de Código

### Convenções

- **snake_case** para funções, variáveis, ficheiros
- **PascalCase** para classes
- **UPPER_SNAKE_CASE** para constantes
- **Type hints** obrigatório em funções públicas

### Docstrings

```python
def process_prediction(
    intent_text: str,
    specialist_confidence: float
) -> dict[str, Any]:
    """
    Processa predição ML.

    Args:
        intent_text: Texto da intenção do usuário
        specialist_confidence: Confiança do especialista (0.0-1.0)

    Returns:
        Dicionário com decision, confidence, probabilities

    Raises:
        ValueError: Se parâmetros são inválidos
        RuntimeError: Se modelo não está carregado

    Examples:
        >>> process_prediction("Create user", 0.8)
        {"decision": "approve", "confidence": 0.85}
    """
    pass
```

### Logging

```python
import structlog

logger = structlog.get_logger()

# Com contexto estruturado
logger.info(
    "prediction_started",
    intent_length=len(intent_text),
    specialist_type=specialist_type
)

# Em caso de erro
logger.error(
    "prediction_failed",
    error=str(e),
    error_type=type(e).__name__,
    intent_id=intent_id
)
```

### Error Handling

```python
from fastapi import HTTPException, status

try:
    result = await service.process(data)
except ValueError as e:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(e)
    )
except Exception as e:
    logger.error("unexpected_error", error=str(e))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error"
    )
```

### Async/Await

```python
# Sempre usar async para I/O
async def predict(data: str) -> dict:
    # Chamar outro serviço async
    result = await external_service.call(data)

    # Executar CPU-bound em executor
    loop = asyncio.get_event_loop()
    processed = await loop.run_in_executor(None, cpu_intensive_func, result)

    return processed
```

---

## Debugging

### Debug Local

```bash
# Executar com debugger
python -m pdb src/main.py

# Ou com VS Code (launch.json)
{
    "name": "Python: FastAPI",
    "type": "debugpy",
    "request": "launch",
    "module": "uvicorn",
    "args": ["src.main:app", "--reload"],
    "jinja": true
}
```

### Logs Detalhados

```bash
# Habilitar debug logs
export LOG_LEVEL=DEBUG

# Ver logs em tempo real
python -m src.main 2>&1 | jq '.'
```

### Tracing Distribuído

```bash
# Habilitar tracing com Jaeger
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export JAEGER_SAMPLING_RATE=1.0

# Visualizar em Jaeger UI
# http://localhost:16686
```

### Testar com Postman/Insomnia

Importar coleção ou configurar:

```json
{
  "name": "ML Inference API",
  "request": {
    "url": "http://localhost:8010/api/v1/inference/predict",
    "method": "POST",
    "header": [{"key": "Content-Type", "value": "application/json"}],
    "body": {
      "mode": "raw",
      "raw": "{\"intent_text\": \"Create user\", \"specialist_confidence\": 0.7}"
    }
  }
}
```

---

## Workflow de Contribuição

### 1. Criar Branch

```bash
git checkout -b feat/minha-nova-feature
# ou
git checkout -b fix/bug-correcao
```

### 2. Desenvolver

```bash
# Fazer alterações
# Adicionar testes
# Executar testes
pytest --cov=src
```

### 3. Linting e Formatação

```bash
# Verificar linting
ruff check .

# Auto-corrigir
ruff check . --fix

# Format código
black .

# Verificar tipos
mypy src/
```

### 4. Commits

```bash
git add .
git commit -m "feat: add new feature for X"
```

Padrão de commits:

- `feat:` nova funcionalidade
- `fix:` correção de bug
- `docs:` documentação
- `refactor:` refatoração
- `test:` testes
- `chore:` manutenção

### 5. Pull Request

Antes de abrir PR:

- [ ] Todos os testes passando
- [ ] Cobertura de testes mantida ou aumentada
- [ ] Linting sem erros
- [ ] Documentação atualizada
- [ ] Commits com mensagens claras

---

## Makefile

O projeto inclui um Makefile para tarefas comuns:

```bash
make help           # Lista comandos disponíveis
make install        # Instala dependências
make lint           # Executa ruff
make format         # Executa black
make test           # Executa testes
make test-cov       # Testes com cobertura
make run            # Executa serviço
make docker-build   # Build Docker image
make docker-run     # Executa container
```

---

## Boas Práticas

### Performance

- Usar conexões persistentes (HTTP keep-alive)
- Implementar cache para predições repetidas
- Usar batch processing para múltiplas predições
- Limitar tamanho de payloads
- Usar async/await para I/O

### Segurança

- Validar todos os inputs
- Sanitizar mensagens de erro em produção
- Usar HTTPS em produção
- Implementar rate limiting
- Proteger endpoints admin
- Nunca logar dados sensíveis

### Testabilidade

- Injetar dependências
- Usar factories/fixtures
- Mockar serviços externos
- Testar casos de erro
- Testar limites e boundary conditions

---

## Links Relacionados

- [API Documentation](./API.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Metrics Documentation](./METRICS.md)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [pytest Docs](https://docs.pytest.org/)
