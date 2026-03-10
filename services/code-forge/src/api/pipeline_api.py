"""
API para execução e monitoramento de pipelines CI/CD.

Integra-se com PipelineEngine para execução real de pipelines
de geração de código.
"""

from datetime import datetime
from typing import Dict, Optional
import uuid
import asyncio
from fastapi import APIRouter, HTTPException, Depends
import structlog

from ..services.pipeline_engine import PipelineEngine
from ..models.execution_ticket import ExecutionTicket, TaskType, TicketStatus, Priority, RiskBand, SLA, QoS, SecurityLevel, DeliveryMode, Consistency, Durability
from ..clients.redis_client import RedisClient

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])

# Pipeline Engine (injetado via dependency)
_pipeline_engine: Optional[PipelineEngine] = None
_redis_client: Optional[RedisClient] = None

PIPELINE_STATE_PREFIX = "pipeline_state:"
PIPELINE_TTL = 86400  # 24 horas


def get_pipeline_engine() -> Optional[PipelineEngine]:
    """Dependency para obter PipelineEngine."""
    global _pipeline_engine
    return _pipeline_engine


def get_redis_client() -> Optional[RedisClient]:
    """Dependency para obter Redis client."""
    global _redis_client
    return _redis_client


def set_pipeline_engine(engine: PipelineEngine):
    """Configura o PipelineEngine global."""
    global _pipeline_engine
    _pipeline_engine = engine


def set_redis_client(client: RedisClient):
    """Configura o Redis client global."""
    global _redis_client
    _redis_client = client


async def _save_pipeline_state(redis_client: RedisClient, pipeline_id: str, state: Dict):
    """Salva estado do pipeline no Redis."""
    key = f"{PIPELINE_STATE_PREFIX}{pipeline_id}"
    string_state = {k: _serialize_value(v) for k, v in state.items()}
    await redis_client.client.hset(key, mapping=string_state)
    await redis_client.client.expire(key, PIPELINE_TTL)


async def _get_pipeline_state(redis_client: RedisClient, pipeline_id: str) -> Optional[Dict]:
    """Recupera estado do pipeline do Redis."""
    key = f"{PIPELINE_STATE_PREFIX}{pipeline_id}"
    state = await redis_client.client.hgetall(key)
    if state:
        return {k: _deserialize_value(v) for k, v in state.items()}
    return None


def _serialize_value(value: any) -> str:
    """Serializa valor para armazenamento."""
    if isinstance(value, (dict, list)):
        import json
        return json.dumps(value)
    return str(value)


def _deserialize_value(value: str) -> any:
    """Deserializa valor do Redis."""
    if not value:
        return None
    try:
        import json
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _normalize_pipeline_status(status: str) -> str:
    """
    Normaliza status de pipeline para contrato reconhecido por consumidores.

    Mapeia estados terminais não reconhecidos (requires_review, partial) para
    valores terminais padrão que CodeForgeClient.wait_for_pipeline_completion()
    reconhece como terminais: completed, failed, cancelled.
    """
    terminal_mapping = {
        "requires_review": "completed",  # Requer revisão mas terminal
        "partial": "failed",  # Parcialmente completo = falha para consumidores
    }
    return terminal_mapping.get(status, status)


def _create_ticket_from_request(
    artifact_id: str,
    parameters: Optional[Dict] = None
) -> ExecutionTicket:
    """Cria ExecutionTicket a partir da requisição."""
    return ExecutionTicket(
        ticket_id=str(uuid.uuid4()),
        plan_id=parameters.get('plan_id') if parameters else None,
        intent_id=parameters.get('intent_id') if parameters else None,
        decision_id=parameters.get('decision_id') if parameters else None,
        task_type=TaskType.BUILD,
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.MEDIUM,
        parameters=parameters or {},
        sla=SLA(
            deadline=datetime.now(),
            timeout_ms=300000,  # 5 minutos
            max_retries=1
        ),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT
        ),
        security_level=SecurityLevel.INTERNAL,
        created_at=datetime.now(),
        metadata={'artifact_id': artifact_id}
    )


@router.post("", status_code=201)
async def trigger_pipeline(
    payload: Dict,
    pipeline_engine: Optional[PipelineEngine] = Depends(get_pipeline_engine),
    redis_client: Optional[RedisClient] = Depends(get_redis_client)
):
    """
    Dispara pipeline CI/CD usando PipelineEngine real.

    Args:
        payload: Dict com artifact_id e parameters opcionais

    Returns:
        Dict com pipeline_id e status inicial
    """
    artifact_id = payload.get("artifact_id")
    if not artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id is required")

    parameters = payload.get("parameters", {})

    # Criar ticket de execução
    ticket = _create_ticket_from_request(artifact_id, parameters)

    # Se PipelineEngine está disponível, executar pipeline real
    if pipeline_engine:
        # Disparar execução em background
        asyncio.create_task(_execute_pipeline_async(
            pipeline_engine, ticket, redis_client
        ))

        # Retornar estado inicial imediatamente
        return {
            "pipeline_id": ticket.ticket_id,
            "status": "queued",
            "ticket_id": ticket.ticket_id
        }
    else:
        # Fallback: modo mock se PipelineEngine não configurado
        state = {
            "pipeline_id": str(uuid.uuid4()),
            "artifact_id": artifact_id,
            "status": "queued",
            "stage": "QUEUED",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "parameters": parameters
        }

        if redis_client:
            await _save_pipeline_state(redis_client, state["pipeline_id"], state)
        else:
            # Estado em memória (não recomendado para produção)
            import sys
            if not hasattr(sys.modules[__name__], '_mock_pipelines'):
                sys.modules[__name__]._mock_pipelines = {}
            sys.modules[__name__]._mock_pipelines[state["pipeline_id"]] = state

        logger.info("pipeline_triggered_mock_mode", pipeline_id=state["pipeline_id"])
        return {"pipeline_id": state["pipeline_id"], "status": state["status"]}


async def _execute_pipeline_async(
    pipeline_engine: PipelineEngine,
    ticket: ExecutionTicket,
    redis_client: Optional[RedisClient]
):
    """Executa pipeline em background e atualiza estado."""
    pipeline_id = ticket.ticket_id

    try:
        logger.info("pipeline_execution_started", pipeline_id=pipeline_id)

        # Salvar estado inicial
        if redis_client:
            await _save_pipeline_state(redis_client, pipeline_id, {
                "pipeline_id": pipeline_id,
                "artifact_id": ticket.metadata.get('artifact_id'),
                "status": "running",
                "stage": "BUILDING",
                "created_at": ticket.created_at.isoformat(),
                "updated_at": datetime.now().isoformat(),
                "ticket_id": ticket.ticket_id
            })

        # Executar pipeline real
        result = await pipeline_engine.execute_pipeline(ticket)

        # Salvar estado final (mapear estados terminais não reconhecidos)
        normalized_status = _normalize_pipeline_status(result.status.lower())
        if redis_client:
            await _save_pipeline_state(redis_client, pipeline_id, {
                "pipeline_id": pipeline_id,
                "artifact_id": ticket.metadata.get('artifact_id'),
                "status": normalized_status,
                "stage": "COMPLETED" if result.status == "COMPLETED" else "FAILED",
                "created_at": result.created_at.isoformat(),
                "updated_at": (result.completed_at or datetime.now()).isoformat(),
                "artifacts": [a.model_dump() for a in result.artifacts],
                "duration_ms": result.total_duration_ms,
                "error": result.error_message,
                "ticket_id": ticket.ticket_id
            })

        logger.info(
            "pipeline_execution_completed",
            pipeline_id=pipeline_id,
            status=result.status
        )

    except Exception as e:
        logger.error("pipeline_execution_failed", pipeline_id=pipeline_id, error=str(e))

        # Salvar estado de erro
        if redis_client:
            await _save_pipeline_state(redis_client, pipeline_id, {
                "pipeline_id": pipeline_id,
                "artifact_id": ticket.metadata.get('artifact_id'),
                "status": "failed",
                "stage": "FAILED",
                "created_at": ticket.created_at.isoformat(),
                "updated_at": datetime.now().isoformat(),
                "error": str(e),
                "ticket_id": ticket.ticket_id
            })


@router.get("/{pipeline_id}")
async def get_pipeline(
    pipeline_id: str,
    pipeline_engine: Optional[PipelineEngine] = Depends(get_pipeline_engine),
    redis_client: Optional[RedisClient] = Depends(get_redis_client)
):
    """
    Retorna status do pipeline.

    Args:
        pipeline_id: ID do pipeline

    Returns:
        Dict com status atual do pipeline
    """
    # Buscar contexto ativo primeiro
    if pipeline_engine:
        active_context = pipeline_engine.get_pipeline_context(pipeline_id)
        if active_context:
            return {
                "pipeline_id": pipeline_id,
                "status": "running",
                "stage": "BUILDING",
                "duration_ms": active_context.calculate_duration(),
                "artifacts": [a.model_dump() for a in active_context.generated_artifacts],
                "stages": [
                    {
                        "name": s.stage_name,
                        "status": s.status.lower(),
                        "duration_ms": s.duration_ms
                    }
                    for s in active_context.pipeline_stages
                ]
            }

    # Buscar no Redis
    if redis_client:
        state = await _get_pipeline_state(redis_client, pipeline_id)
        if state:
            return {
                "pipeline_id": state.get("pipeline_id"),
                "status": state.get("status"),
                "stage": state.get("stage"),
                "duration_ms": state.get("duration_ms", 0),
                "artifacts": state.get("artifacts", []),
                "error": state.get("error"),
                "created_at": state.get("created_at"),
                "updated_at": state.get("updated_at")
            }

    # Fallback em memória
    import sys
    mock_pipelines = getattr(sys.modules[__name__], '_mock_pipelines', {})
    state = mock_pipelines.get(pipeline_id)

    if state:
        # Evolui estado mock de forma determinística
        stage_order = ["QUEUED", "BUILDING", "TESTING", "PACKAGING", "COMPLETED"]
        current_index = stage_order.index(state["stage"])
        if state["stage"] != "COMPLETED":
            state["stage"] = stage_order[min(current_index + 1, len(stage_order) - 1)]
            if state["stage"] == "COMPLETED":
                state["status"] = "completed"
                state["duration_ms"] = 5000
                state["artifacts"] = [{"type": "image", "name": f"{state['artifact_id']}:latest"}]
            state["updated_at"] = datetime.now().isoformat()

        return {
            "pipeline_id": state["pipeline_id"],
            "status": state["status"],
            "stage": state["stage"].lower(),
            "duration_ms": state.get("duration_ms", 0),
            "artifacts": state.get("artifacts", []),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at")
        }

    raise HTTPException(status_code=404, detail="Pipeline not found")
