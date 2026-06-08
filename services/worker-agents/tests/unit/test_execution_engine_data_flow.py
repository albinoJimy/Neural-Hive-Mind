"""
Testes unitários para o data flow entre tasks no ExecutionEngine.

Cobre o fix do bug P1-workers:
- Normalização do resultado do executor (garantir chave `success`), evitando a
  falha silenciosa "Task execution failed without exception".
- Injeção dos outputs das dependências como input da task seguinte (QUERY ->
  TRANSFORM), desserializando outputs em string JSON para dict/list.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Mock neural_hive_observability antes de importar o módulo
mock_tracer_module = MagicMock()
mock_tracer_module.get_tracer = MagicMock()
sys.modules["neural_hive_observability"] = mock_tracer_module

from engine.execution_engine import ExecutionEngine


class StubTicketClient:
    """Cliente de ticket stub que devolve tickets pré-configurados por ID."""

    def __init__(self, tickets_by_id=None):
        self.tickets_by_id = tickets_by_id or {}

    async def get_ticket(self, ticket_id):
        return self.tickets_by_id[ticket_id]


def _make_engine(ticket_client=None):
    """Cria um ExecutionEngine com dependências mínimas para testes de unidade."""
    config = SimpleNamespace(
        max_concurrent_tasks=5,
        max_retries_per_ticket=0,
        retry_backoff_base_seconds=0,
        retry_backoff_max_seconds=0,
        task_timeout_multiplier=1.0,
    )
    return ExecutionEngine(
        config=config,
        ticket_client=ticket_client or StubTicketClient(),
        result_producer=MagicMock(),
        dependency_coordinator=MagicMock(),
        executor_registry=MagicMock(),
        redis_client=None,
        metrics=None,
    )


# ---------------------------------------------------------------------------
# _normalize_executor_result
# ---------------------------------------------------------------------------


def test_normalize_result_preserva_dict_com_success():
    """Um resultado válido (com chave success) é devolvido inalterado."""
    engine = _make_engine()
    result = {"success": True, "output": {"ok": True}}

    normalized = engine._normalize_executor_result(result, "t-1", "QUERY")

    assert normalized is result
    assert normalized["success"] is True


def test_normalize_result_dict_sem_success_marca_falha():
    """Dict sem `success` é normalizado para falha explícita, sem perder conteúdo."""
    engine = _make_engine()
    result = {"output": {"data": 1}}

    normalized = engine._normalize_executor_result(result, "t-2", "TRANSFORM")

    assert normalized["success"] is False
    assert normalized["output"] == {"data": 1}
    assert "error" in normalized


def test_normalize_result_nao_dict_marca_falha():
    """Resultado não-dict é normalizado para dict de falha."""
    engine = _make_engine()

    normalized = engine._normalize_executor_result("texto", "t-3", "TRANSFORM")

    assert normalized["success"] is False
    assert normalized["output"] == "texto"
    assert "error" in normalized


# ---------------------------------------------------------------------------
# _inject_dependency_outputs (data flow QUERY -> TRANSFORM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_inject_dependency_outputs_query_para_transform():
    """O output (objeto) de uma QUERY é injetado como input_data da TRANSFORM."""
    query_output = {"documents": [{"id": 1}, {"id": 2}], "count": 2}
    query_ticket = {
        "ticket_id": "query-1",
        "status": "COMPLETED",
        "metadata": {"result": {"success": True, "output": query_output}},
    }
    client = StubTicketClient({"query-1": query_ticket})
    engine = _make_engine(client)

    transform_ticket = {
        "ticket_id": "transform-1",
        "task_type": "TRANSFORM",
        "dependencies": ["query-1"],
        "parameters": {},
    }

    await engine._inject_dependency_outputs(transform_ticket)

    params = transform_ticket["parameters"]
    # input_data deve ser o output da QUERY (dict), não string nem None.
    assert params["input_data"] == query_output
    assert isinstance(params["input_data"], dict)
    assert params["dependency_outputs"]["query-1"]["output"] == query_output


@pytest.mark.asyncio()
async def test_inject_dependency_outputs_desserializa_result_string():
    """Se metadata['result'] vier como string JSON, é desserializado para dict."""
    query_output = {"rows": [1, 2, 3]}
    result_obj = {"success": True, "output": query_output}
    query_ticket = {
        "ticket_id": "query-2",
        "status": "COMPLETED",
        # result persistido como string JSON (contrato Avro dict[str, str]).
        "metadata": {"result": json.dumps(result_obj)},
    }
    client = StubTicketClient({"query-2": query_ticket})
    engine = _make_engine(client)

    transform_ticket = {
        "ticket_id": "transform-2",
        "task_type": "TRANSFORM",
        "dependencies": ["query-2"],
        "parameters": {},
    }

    await engine._inject_dependency_outputs(transform_ticket)

    params = transform_ticket["parameters"]
    assert params["input_data"] == query_output
    assert isinstance(params["input_data"], dict)


@pytest.mark.asyncio()
async def test_inject_dependency_outputs_output_string_desserializado():
    """Se o output vier como string JSON aninhada, é desserializado para input_data."""
    inner = [{"a": 1}, {"a": 2}]
    query_ticket = {
        "ticket_id": "query-3",
        "status": "COMPLETED",
        # output como string JSON (serialização aninhada)
        "metadata": {"result": {"success": True, "output": json.dumps(inner)}},
    }
    client = StubTicketClient({"query-3": query_ticket})
    engine = _make_engine(client)

    transform_ticket = {
        "ticket_id": "transform-3",
        "task_type": "TRANSFORM",
        "dependencies": ["query-3"],
        "parameters": {},
    }

    await engine._inject_dependency_outputs(transform_ticket)

    params = transform_ticket["parameters"]
    # input_data deve ser a lista desserializada, não a string.
    assert params["input_data"] == inner
    assert isinstance(params["input_data"], list)


@pytest.mark.asyncio()
async def test_inject_dependency_outputs_preserva_input_data_existente():
    """Se a task já traz input_data próprio, este não é sobrescrito."""
    query_ticket = {
        "ticket_id": "query-4",
        "status": "COMPLETED",
        "metadata": {"result": {"success": True, "output": {"x": 1}}},
    }
    client = StubTicketClient({"query-4": query_ticket})
    engine = _make_engine(client)

    transform_ticket = {
        "ticket_id": "transform-4",
        "task_type": "TRANSFORM",
        "dependencies": ["query-4"],
        "parameters": {"input_data": {"original": True}},
    }

    await engine._inject_dependency_outputs(transform_ticket)

    assert transform_ticket["parameters"]["input_data"] == {"original": True}
