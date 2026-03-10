"""
API para geração de código (CodeForge Generation API).

Esta API expõe endpoints para geração de código assíncrona,
utilizando TemplateSelector e CodeComposer existentes.

Endpoints:
    POST /api/v1/generate - Cria requisição de geração assíncrona
    GET /api/v1/generate/{id} - Status da requisição
    GET /api/v1/generate - Lista requisições (debug)
"""

import uuid
import asyncio
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import structlog

from opentelemetry import trace
from prometheus_client import Counter, Histogram

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)
router = APIRouter(prefix="/api/v1/generate", tags=["generation"])

# Armazenamento em memória para requisições de geração
# Em produção, isso seria persistido em Redis ou PostgreSQL
GENERATION_REQUESTS: Dict[str, Dict[str, Any]] = {}

# Métricas Prometheus
generation_requests_total = Counter(
    "neural_hive_code_forge_generation_requests_total",
    "Total generation requests",
    ["status"]
)
generation_duration_seconds = Histogram(
    "neural_hive_code_forge_generation_duration_seconds",
    "Generation request duration",
    ["method"]
)


# Models para resposta (não confundir com request do CodeForgeClient)
class GenerationResponse(BaseModel):
    """Resposta de criação de requisição de geração."""
    request_id: str
    status: str
    message: str


class GenerationStatusResponse(BaseModel):
    """Resposta de status de geração."""
    request_id: str
    status: str
    artifacts: List[Dict[str, Any]] = []
    pipeline_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    code_preview: Optional[str] = None  # Primeiras 500 chars do código (debug)


class ListGenerationResponse(BaseModel):
    """Resposta de listagem de requisições."""
    total: int
    requests: List[Dict[str, Any]]
    status_counts: Dict[str, int]


async def _process_generation_task(
    request_id: str,
    ticket_id: str,
    template_id: str,
    parameters: Dict[str, Any]
):
    """
    Processa geração de código em background.

    Esta função executa de forma assíncrona a geração de código usando:
    1. Heurística simples (método determinístico)
    2. Serviços CodeComposer existentes (quando disponíveis)

    Args:
        request_id: ID da requisição de geração
        ticket_id: ID do ticket de execução
        template_id: ID do template a usar
        parameters: Parâmetros para geração
    """
    start_time = datetime.utcnow()

    try:
        with tracer.start_as_current_span("generation.process") as span:
            span.set_attribute("request_id", request_id)
            span.set_attribute("ticket_id", ticket_id)
            span.set_attribute("template_id", template_id)

            logger.info(
                "generation_task_started",
                request_id=request_id,
                ticket_id=ticket_id,
                template_id=template_id
            )

            # Atualizar status para PROCESSING
            GENERATION_REQUESTS[request_id]["status"] = "processing"
            GENERATION_REQUESTS[request_id]["updated_at"] = datetime.utcnow().isoformat()

            # Extração de parâmetros
            service_name = parameters.get("service_name", "generated-service")
            language = parameters.get("language", "python")
            description = parameters.get("description", "")
            requirements = parameters.get("requirements", [])

            # Simular processamento com CodeComposer (usando heurística)
            # Em produção, importaria e usaria CodeComposer real
            await asyncio.sleep(1)  # Simular tempo de processamento

            # Gerar código usando heurística (similar a CodeComposer._generate_python_microservice)
            code_content = _generate_code_heuristic(
                service_name=service_name,
                language=language.lower(),
                description=description,
                requirements=requirements
            )

            # Calcular hash do conteúdo
            content_hash = hashlib.sha256(code_content.encode()).hexdigest()

            # Criar artifact info
            artifact = {
                "type": "code",
                "language": language,
                "content_hash": content_hash,
                "size_bytes": len(code_content.encode()),
                "generated_at": datetime.utcnow().isoformat(),
                "template_id": template_id
            }

            # Atualizar status para COMPLETED
            GENERATION_REQUESTS[request_id]["status"] = "completed"
            GENERATION_REQUESTS[request_id]["updated_at"] = datetime.utcnow().isoformat()
            GENERATION_REQUESTS[request_id]["artifacts"] = [artifact]
            GENERATION_REQUESTS[request_id]["code_content"] = code_content  # Para preview

            duration = (datetime.utcnow() - start_time).total_seconds()
            generation_duration_seconds.labels(method="heuristic").observe(duration)
            generation_requests_total.labels(status="completed").inc()

            logger.info(
                "generation_task_completed",
                request_id=request_id,
                artifacts_count=1,
                code_size=len(code_content),
                duration_seconds=duration
            )

    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        generation_requests_total.labels(status="failed").inc()

        logger.error(
            "generation_task_failed",
            request_id=request_id,
            error=str(e),
            exc_info=True
        )

        # Atualizar status para FAILED
        GENERATION_REQUESTS[request_id]["status"] = "failed"
        GENERATION_REQUESTS[request_id]["error"] = str(e)
        GENERATION_REQUESTS[request_id]["updated_at"] = datetime.utcnow().isoformat()


def _generate_code_heuristic(
    service_name: str,
    language: str,
    description: str,
    requirements: List[str]
) -> str:
    """
    Gera código baseado em heurística (regras determinísticas).

    Esta função implementa a mesma lógica do CodeComposer._generate_python_microservice
    mas de forma standalone para evitar dependências circulares.

    Args:
        service_name: Nome do serviço
        language: Linguagem de programação
        description: Descrição do serviço
        requirements: Lista de requisitos

    Returns:
        Código gerado como string
    """
    timestamp = datetime.utcnow().isoformat()

    if language == "python":
        return f'''# {service_name} - Generated by Neural Code Forge
# Generated at: {timestamp}
# Template-based generation (heuristic)

from fastapi import FastAPI, HTTPException
import structlog

logger = structlog.get_logger(__name__)
app = FastAPI(
    title="{service_name}",
    description="{description or "Generated service"}"
)

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {{
        "status": "healthy",
        "service": "{service_name}",
        "timestamp": "{timestamp}"
    }}

@app.get("/")
async def root():
    """Root endpoint."""
    return {{
        "message": "Generated by Neural Code Forge",
        "service": "{service_name}"
    }}

@app.get("/info")
async def info():
    """Service information."""
    return {{
        "service": "{service_name}",
        "description": "{description}",
        "requirements": {requirements},
        "generated_at": "{timestamp}"
    }}

# Add your business logic here
'''

    elif language == "javascript" or language == "typescript":
        return '''// Generated by Neural Code Forge
// Express.js service

const express = require('express');
const app = express();

app.get('/health', (req, res) => {
  res.json({ status: 'healthy', service: 'SERVICE_NAME' });
});

app.get('/', (req, res) => {
  res.json({ message: 'Generated by Neural Code Forge' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
'''

    else:
        # Fallback para Python
        return _generate_code_heuristic(service_name, "python", description, requirements)


@router.post("", response_model=GenerationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_generation_request(payload: Dict[str, Any]) -> GenerationResponse:
    """
    Cria uma nova requisição de geração de código.

    O processamento é assíncrono - retorna imediatamente com request_id.
    Use GET /api/v1/generate/{request_id} para verificar o status.

    Args:
        payload: Dict com ticket_id, template_id, parameters

    Returns:
        GenerationResponse com request_id e status inicial

    Raises:
        HTTPException 400: Se ticket_id ou template_id não fornecidos
    """
    with tracer.start_as_current_span("generation.create_request") as span:
        # Extrair parâmetros
        ticket_id = payload.get("ticket_id")
        template_id = payload.get("template_id")
        parameters = payload.get("parameters", {})
        target_repo = payload.get("target_repo", "")
        branch = payload.get("branch", "main")

        span.set_attribute("ticket_id", ticket_id)
        span.set_attribute("template_id", template_id)

        # Validações básicas
        if not ticket_id:
            raise HTTPException(
                status_code=400,
                detail="ticket_id is required"
            )
        if not template_id:
            raise HTTPException(
                status_code=400,
                detail="template_id is required"
            )

        # Criar request_id
        request_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # Armazenar requisição
        GENERATION_REQUESTS[request_id] = {
            "request_id": request_id,
            "status": "queued",
            "ticket_id": ticket_id,
            "template_id": template_id,
            "parameters": parameters,
            "target_repo": target_repo,
            "branch": branch,
            "artifacts": [],
            "error": None,
            "pipeline_id": None,
            "created_at": now,
            "updated_at": now,
            "code_content": None
        }

        # Disparar processamento em background
        asyncio.create_task(
            _process_generation_task(
                request_id=request_id,
                ticket_id=ticket_id,
                template_id=template_id,
                parameters=parameters
            )
        )

        generation_requests_total.labels(status="created").inc()

        logger.info(
            "generation_request_created",
            request_id=request_id,
            ticket_id=ticket_id,
            template_id=template_id
        )

        return GenerationResponse(
            request_id=request_id,
            status="queued",
            message="Generation request accepted and processing"
        )


@router.get("/{request_id}", response_model=GenerationStatusResponse)
async def get_generation_status(request_id: str) -> GenerationStatusResponse:
    """
    Obtém status de uma requisição de geração.

    Args:
        request_id: ID da requisição de geração

    Returns:
        GenerationStatusResponse com status atual e artefatos (se completado)

    Raises:
        HTTPException 404: Se request_id não encontrado
    """
    request_data = GENERATION_REQUESTS.get(request_id)

    if not request_data:
        raise HTTPException(
            status_code=404,
            detail=f"Generation request {request_id} not found"
        )

    # Criar preview do código (primeiras 500 chars)
    code_preview = None
    if request_data.get("code_content"):
        code_preview = request_data["code_content"][:500]
        if len(request_data["code_content"]) > 500:
            code_preview += "\n... (truncated)"

    return GenerationStatusResponse(
        request_id=request_data["request_id"],
        status=request_data["status"],
        artifacts=request_data.get("artifacts", []),
        pipeline_id=request_data.get("pipeline_id"),
        error=request_data.get("error"),
        created_at=request_data["created_at"],
        updated_at=request_data["updated_at"],
        code_preview=code_preview
    )


@router.get("", response_model=ListGenerationResponse)
async def list_generation_requests() -> ListGenerationResponse:
    """
    Lista todas as requisições de geração (para debug).

    Returns:
        ListGenerationResponse com lista de requisições e contagem por status
    """
    requests_list = [
        {
            "request_id": req["request_id"],
            "status": req["status"],
            "ticket_id": req["ticket_id"],
            "template_id": req["template_id"],
            "created_at": req["created_at"],
            "updated_at": req["updated_at"]
        }
        for req in GENERATION_REQUESTS.values()
    ]

    # Contagem por status
    status_counts = {}
    for req in GENERATION_REQUESTS.values():
        s = req["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    return ListGenerationResponse(
        total=len(GENERATION_REQUESTS),
        requests=requests_list,
        status_counts=status_counts
    )
