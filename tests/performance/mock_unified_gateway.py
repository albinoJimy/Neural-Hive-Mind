#!/usr/bin/env python3
"""
Mock Unified Gateway para testes de carga
Simula o comportamento do Unified Gateway para validação do script de load test
"""

import asyncio
import random
import time
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Simular latência do Unified Gateway (5-15ms)
MOCK_LATENCY_MIN = 5
MOCK_LATENCY_MAX = 15

# Fluxos possíveis
FLOWS = ["A", "B", "C", "D", "E", "F", "G", "H"]

app = FastAPI(title="Mock Unified Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NHMRequest(BaseModel):
    text: str
    language: str = "pt-BR"
    correlation_id: str | None = None
    context: Dict[str, Any] | None = None


class NHMRequestResponse(BaseModel):
    request_id: str
    status: str
    flow_classification: str
    confidence: float
    nlu_result: Dict[str, Any]
    pii_detected: bool
    timestamp: str


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "unified-gateway",
        "version": "1.0.0-mock",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "nlu_service": "healthy",
            "pii_service": "healthy",
            "redis": "healthy",
            "kafka": "healthy",
        },
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return {
        "mock": "true",
        "help": "Mock metrics for testing",
    }


@app.post("/api/v1/nhm/request", response_model=NHMRequestResponse)
async def nhm_request(request: NHMRequest, http_request: Request) -> NHMRequestResponse:
    """
    Simula o endpoint POST /api/v1/nhm/request do Unified Gateway

    Processa:
    1. Context Builder
    2. Intent Classifier (NLU)
    3. Flow Router
    4. Response Processor
    """

    # Simular latência de processamento
    processing_time = random.uniform(MOCK_LATENCY_MIN, MOCK_LATENCY_MAX)
    await asyncio.sleep(processing_time / 1000)  # Converter ms para segundos

    # Extrair contexto
    tenant_id = "default"
    user_id = "test_user"
    if request.context:
        tenant_id = request.context.get("tenant_id", "default")
        user_id = request.context.get("user_id", "test_user")

    # Simular classificação de fluxo baseado no texto
    text_lower = request.text.lower()
    if any(word in text_lower for word in ["listar", "get", "obter", "buscar"]):
        flow = "G"  # Query/Data Retrieval
    elif any(word in text_lower for word in ["criar", "adicionar", "novo", "inserir"]):
        flow = "A"  # Create/Insert
    elif any(word in text_lower for word in ["deploy", "release", "produção"]):
        flow = "H"  # Deployment
    elif any(word in text_lower for word in ["relatório", "análise", "dados", "métricas"]):
        flow = "F"  # Analysis
    else:
        flow = random.choice(FLOWS)

    # Simular detecção de PII
    pii_detected = any(
        word in text_lower for word in ["senha", "password", "cpf", "email@", "telefone", "ssn"]
    )

    # Gerar request_id
    request_id = f"req-{int(time.time() * 1000000)}"

    # Simular resultado NLU
    nlu_result = {
        "intent": classify_intent(request.text),
        "entities": extract_entities(request.text),
        "confidence": random.uniform(0.85, 0.99),
        "language": request.language,
        "domain": classify_domain(request.text),
    }

    return NHMRequestResponse(
        request_id=request_id,
        status="processing",
        flow_classification=flow,
        confidence=nlu_result["confidence"],
        nlu_result=nlu_result,
        pii_detected=pii_detected,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/api/v1/nhm/status/{request_id}")
async def get_status(request_id: str):
    """
    Simula o endpoint de status (não implementado na spec original)
    """
    return {
        "request_id": request_id,
        "status": "completed",
        "flow_classification": random.choice(FLOWS),
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
    }


# Funções auxiliares para simulação


def classify_intent(text: str) -> str:
    """Classifica a intenção do texto"""
    text_lower = text.lower()

    intents = {
        "user.list": ["listar", "get users", "obter usuários"],
        "user.create": ["criar usuário", "novo usuário", "adicionar usuário"],
        "password.reset": ["resetar senha", "nova senha", "recuperar senha"],
        "report.generate": ["relatório", "análise", "dashboard"],
        "deployment.deploy": ["deploy", "release", "produção"],
    }

    for intent, keywords in intents.items():
        if any(keyword in text_lower for keyword in keywords):
            return intent

    return "unknown"


def extract_entities(text: str) -> list[dict]:
    """Extrai entidades do texto"""
    entities = []
    text_lower = text.lower()

    # Email
    if "@" in text:
        entities.append({"type": "email", "value": "user@example.com", "confidence": 0.95})

    # Data/hora
    if any(word in text_lower for word in ["hoje", "ontem", "último", "trimestre", "mês"]):
        entities.append({"type": "date", "value": "recent", "confidence": 0.9})

    # Versão
    if "2.0" in text or "v2" in text_lower:
        entities.append({"type": "version", "value": "2.0", "confidence": 0.95})

    return entities


def classify_domain(text: str) -> str:
    """Classifica o domínio do texto"""
    text_lower = text.lower()

    if any(word in text_lower for word in ["usuário", "conta", "login", "senha"]):
        return "user_management"
    elif any(word in text_lower for word in ["vendas", "transação", "pagamento"]):
        return "business"
    elif any(word in text_lower for word in ["deploy", "produção", "release"]):
        return "devops"
    elif any(word in text_lower for word in ["relatório", "métrica", "dados"]):
        return "analytics"
    else:
        return "general"


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting Mock Unified Gateway for load testing...")
    print(f"   Simulating latency: {MOCK_LATENCY_MIN}-{MOCK_LATENCY_MAX}ms")
    print("   Endpoints: /health, /api/v1/nhm/request")

    uvicorn.run(app, host="0.0.0.0", port=7999)
