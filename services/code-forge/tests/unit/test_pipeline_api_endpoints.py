"""
Testes para os endpoints da Pipeline API do Code Forge.

Cobre trigger_pipeline, get_pipeline e estados de pipeline.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_trigger_pipeline_success():
    """Trigger de pipeline deve criar ticket e retornar pipeline_id."""
    from src.api.pipeline_api import set_pipeline_engine, trigger_pipeline

    # Configurar mock pipeline engine
    mock_engine = AsyncMock()
    mock_engine.get_pipeline_context = MagicMock(return_value=None)
    set_pipeline_engine(mock_engine)

    payload = {
        "artifact_id": "test-service",
        "parameters": {"language": "python", "framework": "fastapi"},
    }

    response = await trigger_pipeline(payload, mock_engine, None)

    assert "pipeline_id" in response
    assert response["status"] in ["queued", "running"]
    assert "ticket_id" in response


@pytest.mark.asyncio
async def test_trigger_pipeline_missing_artifact_id():
    """Trigger de pipeline deve falhar sem artifact_id."""
    from src.api.pipeline_api import trigger_pipeline
    from fastapi import HTTPException

    payload = {"parameters": {"language": "python"}}

    with pytest.raises(HTTPException) as exc_info:
        await trigger_pipeline(payload, None, None)

    assert exc_info.value.status_code == 400
    assert "artifact_id is required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_trigger_pipeline_mock_mode():
    """Trigger de pipeline em modo mock quando engine nao disponivel."""
    from src.api.pipeline_api import trigger_pipeline

    payload = {"artifact_id": "test-service", "parameters": {"language": "python"}}

    response = await trigger_pipeline(payload, None, None)

    assert "pipeline_id" in response
    assert response["status"] == "queued"


@pytest.mark.asyncio
async def test_get_pipeline_active_context():
    """Get pipeline deve retornar contexto ativo se disponivel."""
    from src.api.pipeline_api import set_pipeline_engine, get_pipeline
    from src.models.pipeline_context import PipelineContext
    from src.models.execution_ticket import (
        ExecutionTicket,
        TaskType,
        TicketStatus,
        Priority,
        RiskBand,
        SLA,
        QoS,
        SecurityLevel,
        DeliveryMode,
        Consistency,
        Durability,
    )

    # Criar contexto mock
    ticket = ExecutionTicket(
        ticket_id="ticket-123",
        plan_id="plan-123",
        intent_id="intent-123",
        task_type=TaskType.BUILD,
        status=TicketStatus.RUNNING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.MEDIUM,
        parameters={},
        sla=SLA(deadline=datetime.now(), timeout_ms=300000, max_retries=1),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.EVENTUAL,
            durability=Durability.PERSISTENT,
        ),
        security_level=SecurityLevel.INTERNAL,
        created_at=datetime.now(),
    )

    context = PipelineContext(
        pipeline_id="pipeline-123", ticket=ticket, trace_id="trace-123", span_id="span-123"
    )

    mock_engine = MagicMock()
    mock_engine.get_pipeline_context = MagicMock(return_value=context)
    set_pipeline_engine(mock_engine)

    response = await get_pipeline("pipeline-123", mock_engine, None)

    assert response["pipeline_id"] == "pipeline-123"
    assert response["status"] == "running"
    assert response["stage"] == "building"


@pytest.mark.asyncio
async def test_get_pipeline_from_redis():
    """Get pipeline deve buscar estado no Redis."""
    from src.api.pipeline_api import set_pipeline_engine, set_redis_client, get_pipeline

    pipeline_id = "pipeline-123"
    state = {
        "pipeline_id": pipeline_id,
        "artifact_id": "test-service",
        "status": "completed",
        "stage": "COMPLETED",
        "duration_ms": 5000,
        "artifacts": [{"type": "image", "name": "test-service:latest"}],
    }

    mock_engine = MagicMock()
    mock_engine.get_pipeline_context = MagicMock(return_value=None)

    mock_redis = AsyncMock()
    mock_redis.client.hgetall = AsyncMock(return_value=state)

    set_pipeline_engine(mock_engine)
    set_redis_client(mock_redis)

    response = await get_pipeline(pipeline_id, mock_engine, mock_redis)

    assert response["pipeline_id"] == pipeline_id
    assert response["status"] == "completed"
    assert response["stage"] == "completed"


@pytest.mark.asyncio
async def test_get_pipeline_not_found():
    """Get pipeline deve retornar 404 quando pipeline nao existe."""
    from src.api.pipeline_api import set_pipeline_engine, set_redis_client, get_pipeline
    from fastapi import HTTPException

    mock_engine = MagicMock()
    mock_engine.get_pipeline_context = MagicMock(return_value=None)

    mock_redis = AsyncMock()
    mock_redis.client.hgetall = AsyncMock(return_value=None)

    set_pipeline_engine(mock_engine)
    set_redis_client(mock_redis)

    with pytest.raises(HTTPException) as exc_info:
        await get_pipeline("nonexistent", mock_engine, mock_redis)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_normalize_pipeline_status_completed():
    """Normalizacao deve manter status completed."""
    from src.api.pipeline_api import _normalize_pipeline_status

    result = _normalize_pipeline_status("completed")
    assert result == "completed"


@pytest.mark.asyncio
async def test_normalize_pipeline_status_requires_review():
    """Normalizacao deve mapear requires_review para completed."""
    from src.api.pipeline_api import _normalize_pipeline_status

    result = _normalize_pipeline_status("requires_review")
    assert result == "completed"


@pytest.mark.asyncio
async def test_normalize_pipeline_status_partial():
    """Normalizacao deve mapear partial para failed."""
    from src.api.pipeline_api import _normalize_pipeline_status

    result = _normalize_pipeline_status("partial")
    assert result == "failed"


@pytest.mark.asyncio
async def test_create_ticket_from_request():
    """Criacao de ticket deve mapear parametros corretamente."""
    from src.api.pipeline_api import _create_ticket_from_request
    from src.models.execution_ticket import TaskType, TicketStatus

    artifact_id = "test-service"
    parameters = {"plan_id": "plan-123", "intent_id": "intent-123", "decision_id": "decision-123"}

    ticket = _create_ticket_from_request(artifact_id, parameters)

    assert ticket.task_type == TaskType.BUILD
    assert ticket.status == TicketStatus.PENDING
    assert ticket.metadata["artifact_id"] == artifact_id
    assert ticket.plan_id == "plan-123"
    assert ticket.intent_id == "intent-123"
    assert ticket.decision_id == "decision-123"


@pytest.mark.asyncio
async def test_save_pipeline_state():
    """Salvar estado no Redis deve usar chave correta."""
    from src.api.pipeline_api import _save_pipeline_state

    mock_redis = AsyncMock()
    mock_redis.client.hset = AsyncMock(return_value=None)
    mock_redis.client.expire = AsyncMock(return_value=None)

    pipeline_id = "pipeline-123"
    state = {"status": "running", "stage": "BUILDING"}

    await _save_pipeline_state(mock_redis, pipeline_id, state)

    mock_redis.client.hset.assert_called_once()
    mock_redis.client.expire.assert_called_once()


@pytest.mark.asyncio
async def test_get_pipeline_state_empty():
    """Get pipeline state deve retornar None quando chave nao existe."""
    from src.api.pipeline_api import _get_pipeline_state

    mock_redis = AsyncMock()
    mock_redis.client.hgetall = AsyncMock(return_value={})

    result = await _get_pipeline_state(mock_redis, "nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_serialize_value_dict():
    """Serializacao deve converter dict para JSON string."""
    from src.api.pipeline_api import _serialize_value

    value = {"key": "value", "nested": {"a": 1}}
    result = _serialize_value(value)

    assert isinstance(result, str)
    assert "key" in result
    assert "value" in result


@pytest.mark.asyncio
async def test_deserialize_value_json():
    """Deserializacao deve converter JSON string para dict."""
    from src.api.pipeline_api import _deserialize_value

    json_str = '{"key": "value", "nested": {"a": 1}}'
    result = _deserialize_value(json_str)

    assert isinstance(result, dict)
    assert result["key"] == "value"
    assert result["nested"]["a"] == 1


@pytest.mark.asyncio
async def test_deserialize_value_plain_string():
    """Deserializacao deve retornar string plain quando nao é JSON."""
    from src.api.pipeline_api import _deserialize_value

    result = _deserialize_value("plain string")

    assert result == "plain string"
