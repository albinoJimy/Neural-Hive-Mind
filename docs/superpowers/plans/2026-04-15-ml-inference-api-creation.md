# ML Inference API - Service Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar um serviço FastAPI para expor o ApprovalPredictor como API REST com endpoints para predição de aprovação de planos cognitivos.

**Architecture:** Serviço FastAPI com endpoints `/api/v1/predict`, `/api/v1/predict/batch`, e `/api/v1/model/info`. O serviço carrega o modelo ML existente e expõe predições via HTTP.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, Prometheus, pickle (modelo), MongoDB (opcional para cache)

---

## Task 1: Criar estrutura do diretório do serviço

**Files:**
- Create: `services/ml-inference-api/`
- Create: `services/ml-inference-api/src/`
- Create: `services/ml-inference-api/src/api/`
- Create: `services/ml-inference-api/src/services/`
- Create: `services/ml-inference-api/src/config/`
- Create: `services/ml-inference-api/tests/`
- Create: `services/ml-inference-api/requirements.txt`

- [ ] **Step 1: Criar estrutura de diretórios**

```bash
mkdir -p services/ml-inference-api/{src/{api,services,config},tests/{unit,integration}}
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/
git commit -m "feat(ml-inference): create service directory structure"
```

---

## Task 2: Criar requirements.txt

**Files:**
- Create: `services/ml-inference-api/requirements.txt`

- [ ] **Step 1: Criar requirements**

```txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
structlog==24.1.0
prometheus-client==0.19.0
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-exporter-otlp==1.22.0
motor==3.3.2
python-multipart==0.0.6
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/requirements.txt
git commit -m "feat(ml-inference): add dependencies"
```

---

## Task 3: Criar configurações

**Files:**
- Create: `services/ml-inference-api/src/config/settings.py`

- [ ] **Step 1: Criar settings**

```python
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações do ML Inference API."""

    app_name: str = Field(default="ml-inference-api")
    app_version: str = Field(default="1.0.0")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8010)

    # Model
    model_path: str = Field(default="ml_models/nhm_approval_model.pkl")

    # CORS
    cors_origins: list[str] = Field(default=["*"])

    # Observability
    otel_endpoint: str = Field(default="http://otel-collector:4317")
    log_level: str = Field(default="INFO")

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Retorna instância singleton de Settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/src/config/settings.py
git commit -m "feat(ml-inference): add configuration settings"
```

---

## Task 4: Criar PredictionService

**Files:**
- Create: `services/ml-inference-api/src/services/prediction_service.py`

- [ ] **Step 1: Criar prediction service**

```python
"""Prediction Service para ML Inference API."""

import pickle
from pathlib import Path
from typing import Any, Dict

import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class PredictionService:
    """Service para fazer predições usando modelo ML."""

    def __init__(self):
        """Inicializa service carregando o modelo."""
        settings = get_settings()
        self.model_path = Path(settings.model_path)
        self.model_data = None
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """Carrega o modelo do arquivo pickle."""
        if not self.model_path.exists():
            logger.warning("model_not_found", path=str(self.model_path))
            return

        with open(self.model_path, "rb") as f:
            self.model_data = pickle.load(f)
            self.model = self.model_data.get("model")

        logger.info("model_loaded", version=self.model_data.get("version", "unknown"))

    def predict(
        self,
        text: str,
        specialist_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """Faz predição a partir do texto da intenção.

        Args:
            text: Texto da intenção
            specialist_confidence: Confiança do especialista (0.0-1.0)

        Returns:
            Dicionário com decision, confidence, probabilities
        """
        if not self.model:
            return {
                "decision": "review_required",
                "confidence": 0.0,
                "error": "Model not loaded"
            }

        # Extrair features NLP básicas
        features = self._extract_features(text, specialist_confidence)

        # Predizer
        decision = self.model.predict([list(features.values())])[0]

        # Obter probabilidades
        probabilities = {}
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba([list(features.values())])[0]
            for cls, prob in zip(self.model.classes_, probs):
                probabilities[cls] = float(prob)
            confidence = max(probs)
        else:
            confidence = 0.5

        return {
            "decision": decision,
            "confidence": float(confidence),
            "probabilities": probabilities,
            "model_version": self.model_data.get("version", "unknown")
        }

    def _extract_features(self, text: str, specialist_confidence: float) -> Dict[str, float]:
        """Extrai features básicas do texto."""
        import re

        # Domínios
        domain_keywords = {
            "security": r"\b(security|ssl|tls|authentication)\b",
            "performance": r"\b(performance|optimize|cache|speed)\b",
            "database": r"\b(database|db|sql|mongo|query)\b",
            "devops": r"\b(deploy|container|docker|kubernetes|ci/cd)\b",
            "testing": r"\b(test|testing|unit|integration|e2e)\b",
        }

        domains = {}
        for domain, pattern in domain_keywords.items():
            domains[f"domain_{domain}"] = 1.0 if re.search(pattern, text, re.I) else 0.0

        # Ações
        action_keywords = {
            "create": r"\b(create|add|insert|new)\b",
            "update": r"\b(update|modify|change|edit)\b",
            "delete": r"\b(delete|drop|remove|destroy)\b",
            "read": r"\b(get|fetch|select|read|query)\b",
            "deploy": r"\b(deploy|release|publish)\b",
        }

        actions = {}
        for action, pattern in action_keywords.items():
            actions[f"action_{action}"] = 1.0 if re.search(pattern, text, re.I) else 0.0

        # Outras features
        features = {
            "specialist_confidence": specialist_confidence,
            "has_backup": 1.0 if re.search(r"\bbackup|save\b", text, re.I) else 0.0,
            "has_verification": 1.0 if re.search(r"\bverify|validation|check\b", text, re.I) else 0.0,
            "has_all": 1.0 if re.search(r"\ball\b", text, re.I) else 0.0,
            "text_length_chars": len(text),
            "text_length_words": len(text.split()),
            "risk_high": 1.0 if re.search(r"\b(delete|drop|destroy)\b", text, re.I) else 0.0,
            "risk_medium": 1.0 if re.search(r"\b(update|change|modify)\b", text, re.I) else 0.0,
            "risk_low": 1.0 if re.search(r"\b(create|add|verify|check)\b", text, re.I) else 0.0,
            "simple_risk_score": min(1.0, text.lower().count("delete") * 0.3),
        }

        # Primary domain
        domain_scores = {k.replace("domain_", ""): v for k, v in domains.items()}
        primary_domain = max(domain_scores, key=domain_scores.get) if domain_scores else ""
        for domain in ["security", "performance", "database", "devops", "testing"]:
            features[f"primary_domain_{domain}"] = 1.0 if primary_domain == domain else 0.0

        # Primary action
        action_scores = {k.replace("action_", ""): v for k, v in actions.items()}
        primary_action = max(action_scores, key=action_scores.get) if action_scores else ""
        for action in ["create", "update", "delete", "read", "deploy"]:
            features[f"primary_action_{action}"] = 1.0 if primary_action == action else 0.0

        return {**domains, **actions, **features}

    def get_model_info(self) -> Dict[str, Any]:
        """Retorna informações sobre o modelo."""
        if not self.model_data:
            return {"error": "Model not loaded"}

        return {
            "version": self.model_data.get("version"),
            "trained_at": self.model_data.get("trained_at"),
            "features": self.model_data.get("features", []),
            "metrics": self.model_data.get("metrics", {}),
            "training_samples": self.model_data.get("training_samples"),
        }
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/src/services/prediction_service.py
git commit -m "feat(ml-inference): implement prediction service"
```

---

## Task 5: Criar API routes

**Files:**
- Create: `services/ml-inference-api/src/api/__init__.py`
- Create: `services/ml-inference-api/src/api/routes/predictions.py`

- [ ] **Step 1: Criar routes**

Criar `src/api/__init__.py`:
```python
from fastapi import APIRouter
from src.api.routes.predictions import router as predictions_router

api_router = APIRouter()
api_router.include_router(predictions_router, prefix="/predictions", tags=["predictions"])
```

Criar `src/api/routes/predictions.py`:
```python
"""API Routes para predições ML."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.services.prediction_service import PredictionService

router = APIRouter()
prediction_service = PredictionService()


class PredictRequest(BaseModel):
    """Request para predição."""

    text: str = Field(..., description="Texto da intenção/código")
    specialist_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiança do especialista (0.0-1.0)"
    )


class PredictResponse(BaseModel):
    """Response de predição."""

    decision: str = Field(..., description="Decisão: approve, reject, review_required")
    confidence: float = Field(..., description="Confiança da predição (0.0-1.0)")
    probabilities: dict = Field(default_factory=dict, description="Probabilidades por classe")
    model_version: str = Field(..., description="Versão do modelo usado")


class BatchPredictRequest(BaseModel):
    """Request para predição em lote."""

    predictions: list[PredictRequest] = Field(..., description="Lista de predições")


class BatchPredictResponse(BaseModel):
    """Response de predição em lote."""

    results: list[PredictResponse] = Field(..., description="Resultados das predições")


@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    """Faz predição de aprovação para uma intenção."""
    result = prediction_service.predict(
        text=request.text,
        specialist_confidence=request.specialist_confidence
    )

    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])

    return PredictResponse(**result)


@router.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch(request: BatchPredictRequest) -> BatchPredictResponse:
    """Faz predições em lote."""
    results = []

    for pred_request in request.predictions:
        result = prediction_service.predict(
            text=pred_request.text,
            specialist_confidence=pred_request.specialist_confidence
        )
        results.append(PredictResponse(**result))

    return BatchPredictResponse(results=results)


@router.get("/model/info")
async def get_model_info() -> dict:
    """Retorna informações sobre o modelo carregado."""
    return prediction_service.get_model_info()


@router.get("/health")
async def health_check() -> dict:
    """Health check."""
    return {"status": "healthy", "service": "ml-inference-api"}
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/src/api/
git commit -m "feat(ml-inference): implement API routes"
```

---

## Task 6: Criar main.py

**Files:**
- Create: `services/ml-inference-api/main.py`

- [ ] **Step 1: Criar main application**

```python
"""ML Inference API - Main application."""

import asyncio
import signal
import sys

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from src.api import api_router
from src.config.settings import get_settings
from src.observability.metrics import init_metrics

logger = structlog.get_logger()


def configure_logging():
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def create_app() -> FastAPI:
    """Cria e configura aplicação FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="ML Inference API for Neural Hive Mind",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(api_router, prefix="/api/v1")

    # Prometheus metrics
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


async def main():
    """Main entry point."""
    settings = get_settings()

    configure_logging()

    app = create_app()
    init_metrics(app)

    shutdown_event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info(
        "starting_ml_inference_api",
        service=settings.app_name,
        version=settings.app_version,
        port=settings.api_port,
    )

    config = uvicorn.Config(
        app=app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        access_log=True,
    )

    server = uvicorn.Server(config)

    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        logger.info("ml_inference_api_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/main.py
git commit -m "feat(ml-inference): implement main application"
```

---

## Task 7: Criar observability

**Files:**
- Create: `services/ml-inference-api/src/observability/__init__.py`
- Create: `services/ml-inference-api/src/observability/metrics.py`

- [ ] **Step 1: Criar métricas**

Criar `src/observability/metrics.py`:
```python
"""Métricas Prometheus para ML Inference API."""

from prometheus_client import Counter, Histogram
from fastapi import FastAPI

# Prediction Metrics
prediction_requests_total = Counter(
    "ml_inference_prediction_requests_total",
    "Total de predições realizadas",
    ["decision"]
)

prediction_duration_seconds = Histogram(
    "ml_inference_prediction_duration_seconds",
    "Duração das predições"
)

model_errors_total = Counter(
    "ml_inference_model_errors_total",
    "Total de erros do modelo",
    ["error_type"]
)


def init_metrics(app: FastAPI) -> None:
    """Inicializa métricas no contexto da aplicação."""
    app.state.prediction_requests_total = prediction_requests_total
    app.state.prediction_duration_seconds = prediction_duration_seconds
    app.state.model_errors_total = model_errors_total
```

- [ ] **Step 2: Atualizar routes para usar métricas**

No `src/api/routes/predictions.py`, adicionar:

```python
import time
from src.observability.metrics import prediction_requests_total, prediction_duration_seconds

@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    start_time = time.time()

    try:
        result = prediction_service.predict(
            text=request.text,
            specialist_confidence=request.specialist_confidence
        )

        if "error" not in result:
            prediction_requests_total.labels(decision=result["decision"]).inc()

        return PredictResponse(**result)
    finally:
        prediction_duration_seconds.observe(time.time() - start_time)
```

- [ ] **Step 3: Commit**

```bash
git add services/ml-inference-api/src/observability/
git add services/ml-inference-api/src/api/routes/predictions.py
git commit -m "feat(ml-inference): add prometheus metrics"
```

---

## Task 8: Criar testes

**Files:**
- Create: `services/ml-inference-api/tests/unit/test_prediction_service.py`
- Create: `services/ml-inference-api/tests/unit/test_api_routes.py`

- [ ] **Step 1: Criar testes**

Criar `tests/unit/test_prediction_service.py`:
```python
import pytest
from src.services.prediction_service import PredictionService

@pytest.fixture
def service():
    return PredictionService()

def test_predict_with_text(service):
    result = service.predict("Create new user with authentication")
    assert "decision" in result
    assert "confidence" in result

def test_predict_with_high_risk(service):
    result = service.predict("Delete all users without backup")
    assert result["decision"] in ["reject", "review_required"]
```

Criar `tests/unit/test_api_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient
from src.main import create_app

@pytest.fixture
def client():
    return TestClient(create_app())

def test_predict_endpoint(client, mocker):
    mocker.patch("src.api.routes.predictions.prediction_service")
    response = client.post("/api/v1/predictions/predict", json={"text": "test"})
    assert response.status_code == 200

def test_health_check(client):
    response = client.get("/api/v1/predictions/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/tests/
git commit -m "test(ml-inference): add unit tests"
```

---

## Task 9: Criar documentação

**Files:**
- Create: `services/ml-inference-api/README.md`

- [ ] **Step 1: Criar README**

```markdown
# ML Inference API

API de inferência ML para predição de aprovação de planos cognitivos.

## Endpoints

- `POST /api/v1/predictions/predict` - Predição única
- `POST /api/v1/predictions/predict/batch` - Predição em lote
- `GET /api/v1/predictions/model/info` - Informações do modelo
- `GET /metrics` - Métricas Prometheus

## Deploy

```bash
# Build
docker build -t ml-inference-api .

# Run
docker run -p 8010:8010 ml-inference-api
```
```

- [ ] **Step 2: Commit**

```bash
git add services/ml-inference-api/README.md
git commit -m "docs(ml-inference): add README"
```

---

## Task 10: Executar testes

**Files:**
- All test files

- [ ] **Step 1: Run tests**

Run: `cd services/ml-inference-api && pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Run linting**

Run: `cd services/ml-inference-api && ruff check src/`
Expected: No errors

- [ ] **Step 3: Commit final**

```bash
git add .
git commit -m "feat(ml-inference): complete service implementation - all tests passing"
```

---

## Self-Review Checklist

- [x] FastAPI application criada
- [x] PredictionService implementado
- [x] API routes criadas
- [x] Métricas Prometheus
- [x] Testes unitários
- [x] Documentação README
- [x] Health check endpoint
