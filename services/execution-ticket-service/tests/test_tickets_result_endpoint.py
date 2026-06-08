"""Testes para o endpoint GET /api/v1/tickets/{id}/result e helper de desserialização.

Cobre o fix do bug P1-workers (ponto 1): o GET deve devolver o output da execução
como OBJETO JSON, e não null nem string, mesmo quando o modelo Avro (`metadata`
como `map<string>`) força os valores a string.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

# Importar módulos - path configurado no conftest.py
from src.api import tickets as tickets_api

# ---------------------------------------------------------------------------
# _deserialize_result
# ---------------------------------------------------------------------------


def test_deserialize_result_objeto():
    """Um result já em objeto é devolvido inalterado."""
    obj = {"success": True, "output": {"count": 3}}
    assert tickets_api._deserialize_result({"result": obj}) == obj


def test_deserialize_result_string_json():
    """Um result serializado como string JSON é desserializado para objeto."""
    obj = {"success": True, "output": {"count": 3}}
    metadata = {"result": json.dumps(obj)}

    deserialized = tickets_api._deserialize_result(metadata)

    assert deserialized == obj
    assert isinstance(deserialized, dict)


def test_deserialize_result_ausente():
    """Sem chave result, devolve None."""
    assert tickets_api._deserialize_result({}) is None
    assert tickets_api._deserialize_result(None) is None


def test_deserialize_result_string_nao_json():
    """Uma string não-JSON é mantida como está (não rebenta)."""
    assert tickets_api._deserialize_result({"result": "nao-json"}) == "nao-json"


def _make_postgres_client(ticket_orm):
    """Cria mock de PostgresClient cujo get_ticket_by_id devolve o ORM dado."""
    client = MagicMock()
    client.get_ticket_by_id = AsyncMock(return_value=ticket_orm)
    return client


@pytest.mark.asyncio()
async def test_get_ticket_result_objeto():
    """O endpoint devolve result como objeto (lido do JSONB cru do ORM)."""
    ticket_id = str(uuid4())
    result_obj = {"success": True, "output": {"documents": [{"id": 1}], "count": 1}}
    ticket_orm = SimpleNamespace(
        ticket_id=ticket_id,
        status="COMPLETED",
        ticket_metadata={"result": result_obj},
    )
    client = _make_postgres_client(ticket_orm)

    with patch("src.api.tickets.get_postgres_client", return_value=client):
        response = await tickets_api.get_ticket_result(ticket_id)

    assert response.ticket_id == ticket_id
    assert response.status == "COMPLETED"
    assert response.result == result_obj
    assert isinstance(response.result, dict)


@pytest.mark.asyncio()
async def test_get_ticket_result_desserializa_string():
    """Se o result no metadata for string JSON, é devolvido como objeto."""
    ticket_id = str(uuid4())
    result_obj = {"success": True, "output": {"rows": [1, 2]}}
    ticket_orm = SimpleNamespace(
        ticket_id=ticket_id,
        status="COMPLETED",
        ticket_metadata={"result": json.dumps(result_obj)},
    )
    client = _make_postgres_client(ticket_orm)

    with patch("src.api.tickets.get_postgres_client", return_value=client):
        response = await tickets_api.get_ticket_result(ticket_id)

    assert response.result == result_obj
    assert isinstance(response.result, dict)


@pytest.mark.asyncio()
async def test_get_ticket_result_not_found():
    """Ticket inexistente devolve 404."""
    ticket_id = str(uuid4())
    client = _make_postgres_client(None)

    with (
        patch("src.api.tickets.get_postgres_client", return_value=client),
        pytest.raises(HTTPException) as exc,
    ):
        await tickets_api.get_ticket_result(ticket_id)

    assert exc.value.status_code == 404


@pytest.mark.asyncio()
async def test_get_ticket_result_sem_result():
    """Ticket sem result no metadata devolve result=None (não rebenta)."""
    ticket_id = str(uuid4())
    ticket_orm = SimpleNamespace(
        ticket_id=ticket_id,
        status="RUNNING",
        ticket_metadata={},
    )
    client = _make_postgres_client(ticket_orm)

    with patch("src.api.tickets.get_postgres_client", return_value=client):
        response = await tickets_api.get_ticket_result(ticket_id)

    assert response.result is None
    assert response.status == "RUNNING"
