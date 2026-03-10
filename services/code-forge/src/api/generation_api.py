"""
API para geração de código (CodeForge Generation API).

Esta API expõe endpoints para geração de código assíncrona,
integrando-se com CodeComposer existente para geração real.

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
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
import structlog

from opentelemetry import trace
from prometheus_client import Counter, Histogram

from ..clients.redis_client import RedisClient
from ..services.code_composer import CodeComposer
from ..models.pipeline_context import PipelineContext
from ..models.execution_ticket import ExecutionTicket
from ..models.artifact import ArtifactType, GenerationMethod

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)
router = APIRouter(prefix="/api/v1/generate", tags=["generation"])

# Cliente Redis (injetado via dependency)
_redis_client: Optional[RedisClient] = None

def get_redis_client() -> Optional[RedisClient]:
    """Dependency para obter cliente Redis."""
    global _redis_client
    return _redis_client

def set_redis_client(client: RedisClient):
    """Configura o cliente Redis global."""
    global _redis_client
    _redis_client = client


# Cliente MongoDB e LLM (injetados via dependency)
_mongodb_client = None
_llm_client = None


def set_generation_api_clients(
    redis_client: Optional[RedisClient] = None,
    mongodb_client: Optional['MongoDBClient'] = None,
    llm_client: Optional['LLMClient'] = None
):
    """Configura os clientes globais da API de geração."""
    global _redis_client, _mongodb_client, _llm_client
    if redis_client:
        _redis_client = redis_client
    if mongodb_client:
        _mongodb_client = mongodb_client
    if llm_client:
        _llm_client = llm_client


def get_mongodb_client():
    """Dependency para obter cliente MongoDB."""
    global _mongodb_client
    return _mongodb_client


def get_llm_client():
    """Dependency para obter cliente LLM."""
    global _llm_client
    return _llm_client

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


# Models para resposta
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
    code_preview: Optional[str] = None


class ListGenerationResponse(BaseModel):
    """Resposta de listagem de requisições."""
    total: int
    requests: List[Dict[str, Any]]
    status_counts: Dict[str, int]


# Keys do Redis
GENERATION_KEY_PREFIX = "generation:"
GENERATION_LIST_KEY = "generation:all"
GENERATION_TTL = 86400  # 24 horas


async def _save_generation_state(redis_client: RedisClient, request_id: str, state: Dict[str, Any]):
    """Salva estado da requisição no Redis."""
    key = f"{GENERATION_KEY_PREFIX}{request_id}"
    await redis_client.set_value(
        key,
        hashlib.sha256(str(state).encode()).hexdigest(),  # Valor dummy para uso com hset
        ttl=GENERATION_TTL
    )
    # Usar hset para estado completo
    string_state = {k: _serialize_for_redis(v) for k, v in state.items()}
    await redis_client.client.hset(key, mapping=string_state)
    await redis_client.client.expire(key, GENERATION_TTL)

    # Adicionar à lista de requisições
    await redis_client.client.sadd(GENERATION_LIST_KEY, request_id)


async def _get_generation_state(redis_client: RedisClient, request_id: str) -> Optional[Dict[str, Any]]:
    """Recupera estado da requisição do Redis."""
    key = f"{GENERATION_KEY_PREFIX}{request_id}"
    state = await redis_client.client.hgetall(key)

    if state:
        # Deserializar valores
        return {k: _deserialize_from_redis(v) for k, v in state.items()}
    return None


async def _update_generation_state(redis_client: RedisClient, request_id: str, updates: Dict[str, Any]):
    """Atualiza campos específicos do estado."""
    key = f"{GENERATION_KEY_PREFIX}{request_id}"
    string_updates = {k: _serialize_for_redis(v) for k, v in updates.items()}
    await redis_client.client.hset(key, mapping=string_updates)
    await redis_client.client.expire(key, GENERATION_TTL)


def _serialize_for_redis(value: Any) -> str:
    """Serializa valor para armazenamento Redis."""
    if isinstance(value, (dict, list)):
        import json
        return json.dumps(value)
    return str(value)


def _deserialize_from_redis(value: str) -> Any:
    """Deserializa valor do Redis."""
    if not value:
        return None
    try:
        import json
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


async def _process_generation_task(
    request_id: str,
    ticket_id: str,
    template_id: str,
    parameters: Dict[str, Any],
    redis_client: RedisClient,
    code_composer: CodeComposer
):
    """
    Processa geração de código em background usando CodeComposer real.

    Args:
        request_id: ID da requisição de geração
        ticket_id: ID do ticket de execução
        template_id: ID do template a usar
        parameters: Parâmetros para geração
        redis_client: Cliente Redis para persistência
        code_composer: Instância de CodeComposer
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
            await _update_generation_state(
                redis_client, request_id,
                {"status": "processing", "updated_at": datetime.utcnow().isoformat()}
            )

            # Criar ticket de execução com todos os campos obrigatórios
            from ..models.execution_ticket import TaskType, TicketStatus, Priority, RiskBand, SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability

            ticket = ExecutionTicket(
                ticket_id=ticket_id,
                parameters=parameters,
                intent_id=parameters.get('intent_id'),
                plan_id=parameters.get('plan_id'),
                decision_id=parameters.get('decision_id'),
                correlation_id=parameters.get('correlation_id'),
                task_type=TaskType.BUILD,
                status=TicketStatus.PENDING,
                priority=Priority.NORMAL,
                risk_band=RiskBand.MEDIUM,
                sla=SLA(
                    deadline=datetime.utcnow(),
                    timeout_ms=300000,
                    max_retries=1
                ),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.EVENTUAL,
                    durability=Durability.PERSISTENT
                ),
                security_level=SecurityLevel.INTERNAL,
                created_at=datetime.utcnow()
            )

            # Criar contexto de pipeline
            context = PipelineContext(
                pipeline_id=request_id,
                ticket=ticket,
                trace_id=request_id,
                span_id=request_id[:16]
            )

            # Criar template mock (será selecionado pelo TemplateSelector em produção)
            from ..models.template import Template, TemplateMetadata, TemplateLanguage, TemplateType
            template = Template(
                template_id=template_id,
                metadata=TemplateMetadata(
                    name=template_id,
                    version='1.0.0',
                    description='Selected template',
                    author='Neural Hive Team',
                    tags=[],
                    language=TemplateLanguage.PYTHON,
                    type=TemplateType.MICROSERVICE
                ),
                parameters=[],
                content_path='',
                examples={}
            )
            context.selected_template = template

            # Executar CodeComposer real
            await code_composer.compose(context)

            # Extrair artefatos gerados
            artifact = context.get_latest_artifact()

            if artifact:
                # Recuperar código do MongoDB para preview
                code_content = await code_composer.mongodb_client.get_artifact_content(artifact.artifact_id)
                code_preview = code_content[:500] if code_content else None
                if code_content and len(code_content) > 500:
                    code_preview += "\n... (truncated)"

                # Criar artifact info
                artifact_info = {
                    "type": artifact.artifact_type.lower(),
                    "language": artifact.language,
                    "content_hash": artifact.content_hash,
                    "size_bytes": len(code_content.encode()) if code_content else 0,
                    "generated_at": artifact.created_at.isoformat(),
                    "template_id": template_id,
                    "artifact_id": artifact.artifact_id,
                    "confidence_score": artifact.confidence_score,
                    "generation_method": artifact.generation_method.value
                }

                # Atualizar status para COMPLETED
                await _update_generation_state(
                    redis_client, request_id,
                    {
                        "status": "completed",
                        "updated_at": datetime.utcnow().isoformat(),
                        "artifacts": [artifact_info],
                        "code_preview": code_preview,
                        "pipeline_id": request_id
                    }
                )

                duration = (datetime.utcnow() - start_time).total_seconds()
                generation_duration_seconds.labels(method="code_composer").observe(duration)
                generation_requests_total.labels(status="completed").inc()

                logger.info(
                    "generation_task_completed",
                    request_id=request_id,
                    artifact_id=artifact.artifact_id,
                    duration_seconds=duration
                )
            else:
                raise Exception("No artifact generated by CodeComposer")

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
        await _update_generation_state(
            redis_client, request_id,
            {
                "status": "failed",
                "error": str(e),
                "updated_at": datetime.utcnow().isoformat()
            }
        )


@router.post("", response_model=GenerationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_generation_request(
    payload: Dict[str, Any],
    redis_client: Optional[RedisClient] = Depends(get_redis_client)
) -> GenerationResponse:
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

        # Inicializar estado no Redis (ou memória se Redis não disponível)
        state = {
            "request_id": request_id,
            "status": "queued",
            "ticket_id": ticket_id,
            "template_id": template_id,
            "parameters": _serialize_for_redis(parameters),
            "target_repo": target_repo,
            "branch": branch,
            "artifacts": "[]",
            "error": "",
            "pipeline_id": "",
            "created_at": now,
            "updated_at": now,
            "code_preview": ""
        }

        if redis_client:
            await _save_generation_state(redis_client, request_id, state)
        else:
            # Fallback em memória se Redis não configurado
            import sys
            if not hasattr(sys.modules[__name__], '_in_memory_state'):
                sys.modules[__name__]._in_memory_state = {}
            sys.modules[__name__]._in_memory_state[request_id] = state

        # Disparar processamento em background
        if redis_client:
            # Usar clientes injetados do startup (centralizados no main.py)
            global _mongodb_client, _llm_client
            code_composer = CodeComposer(
                mongodb_client=_mongodb_client,
                llm_client=_llm_client
            )

            asyncio.create_task(
                _process_generation_task(
                    request_id=request_id,
                    ticket_id=ticket_id,
                    template_id=template_id,
                    parameters=parameters,
                    redis_client=redis_client,
                    code_composer=code_composer
                )
            )
        else:
            # Fallback com heurística simples
            asyncio.create_task(
                _process_generation_task_legacy(request_id, ticket_id, template_id, parameters)
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


async def _process_generation_task_legacy(request_id: str, ticket_id: str, template_id: str, parameters: Dict[str, Any]):
    """Fallback de processamento sem Redis/CodeComposer (para compatibilidade)."""
    import sys
    in_memory_state = getattr(sys.modules[__name__], '_in_memory_state', {})

    try:
        # Atualizar status
        if request_id in in_memory_state:
            in_memory_state[request_id]["status"] = "processing"
            in_memory_state[request_id]["updated_at"] = datetime.utcnow().isoformat()

        # Simular processamento
        await asyncio.sleep(1)

        # Gerar código heurístico
        from ._heuristic import generate_code_heuristic
        code_content = generate_code_heuristic(
            service_name=parameters.get("service_name", "generated-service"),
            language=parameters.get("language", "python").lower(),
            description=parameters.get("description", ""),
            requirements=parameters.get("requirements", [])
        )

        # Calcular hash
        content_hash = hashlib.sha256(code_content.encode()).hexdigest()

        artifact = {
            "type": "code",
            "language": parameters.get("language", "python"),
            "content_hash": content_hash,
            "size_bytes": len(code_content.encode()),
            "generated_at": datetime.utcnow().isoformat(),
            "template_id": template_id
        }

        if request_id in in_memory_state:
            in_memory_state[request_id]["status"] = "completed"
            in_memory_state[request_id]["updated_at"] = datetime.utcnow().isoformat()
            in_memory_state[request_id]["artifacts"] = [artifact]
            in_memory_state[request_id]["code_preview"] = code_content[:500]

        generation_requests_total.labels(status="completed").inc()

    except Exception as e:
        if request_id in in_memory_state:
            in_memory_state[request_id]["status"] = "failed"
            in_memory_state[request_id]["error"] = str(e)
            in_memory_state[request_id]["updated_at"] = datetime.utcnow().isoformat()
        generation_requests_total.labels(status="failed").inc()


@router.get("/{request_id}", response_model=GenerationStatusResponse)
async def get_generation_status(
    request_id: str,
    redis_client: Optional[RedisClient] = Depends(get_redis_client)
) -> GenerationStatusResponse:
    """
    Obtém status de uma requisição de geração.

    Args:
        request_id: ID da requisição de geração

    Returns:
        GenerationStatusResponse com status atual e artefatos (se completado)

    Raises:
        HTTPException 404: Se request_id não encontrado
    """
    if redis_client:
        request_data = await _get_generation_state(redis_client, request_id)
    else:
        import sys
        in_memory_state = getattr(sys.modules[__name__], '_in_memory_state', {})
        request_data = in_memory_state.get(request_id)

    if not request_data:
        raise HTTPException(
            status_code=404,
            detail=f"Generation request {request_id} not found"
        )

    # Criar preview do código
    code_preview = request_data.get("code_preview", "")

    return GenerationStatusResponse(
        request_id=request_data["request_id"],
        status=request_data["status"],
        artifacts=_deserialize_from_redis(request_data.get("artifacts", "[]")),
        pipeline_id=request_data.get("pipeline_id") or None,
        error=request_data.get("error") or None,
        created_at=request_data["created_at"],
        updated_at=request_data["updated_at"],
        code_preview=code_preview or None
    )


@router.get("", response_model=ListGenerationResponse)
async def list_generation_requests(
    redis_client: Optional[RedisClient] = Depends(get_redis_client)
) -> ListGenerationResponse:
    """
    Lista todas as requisições de geração (para debug).

    Returns:
        ListGenerationResponse com lista de requisições e contagem por status
    """
    if redis_client:
        # Buscar IDs da lista
        request_ids = await redis_client.client.smembers(GENERATION_LIST_KEY)
        requests_list = []
        status_counts = {}

        for req_id in request_ids:
            data = await _get_generation_state(redis_client, req_id)
            if data:
                requests_list.append({
                    "request_id": data["request_id"],
                    "status": data["status"],
                    "ticket_id": data["ticket_id"],
                    "template_id": data["template_id"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"]
                })

                s = data["status"]
                status_counts[s] = status_counts.get(s, 0) + 1

        return ListGenerationResponse(
            total=len(requests_list),
            requests=requests_list,
            status_counts=status_counts
        )
    else:
        import sys
        in_memory_state = getattr(sys.modules[__name__], '_in_memory_state', {})

        requests_list = [
            {
                "request_id": req["request_id"],
                "status": req["status"],
                "ticket_id": req["ticket_id"],
                "template_id": req["template_id"],
                "created_at": req["created_at"],
                "updated_at": req["updated_at"]
            }
            for req in in_memory_state.values()
        ]

        status_counts = {}
        for req in in_memory_state.values():
            s = req["status"]
            status_counts[s] = status_counts.get(s, 0) + 1

        return ListGenerationResponse(
            total=len(in_memory_state),
            requests=requests_list,
            status_counts=status_counts
        )
