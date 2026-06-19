"""
Testes unitários para o contrato de evidência no ExecutionEngine (Task 1 da spec
caminho-real-first-class).

Cobrem:
- ``_has_real_evidence``: cada task_type do contrato (evidência presente vs ausente).
- Gate de COMPLETED em ``_execute_ticket``:
  (a) caminho real produz evidência -> COMPLETED;
  (b) simulação/noop/evidência-ausente com strict_real_path=True -> FAILED;
  (c) simulação/noop com strict_real_path=False -> COMPLETED mas simulated_total++.

Regra transversal: metadata.simulated==True OU output.noop==True NÃO é trabalho real.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Mock neural_hive_observability antes de importar o módulo
mock_tracer_module = MagicMock()
mock_tracer_module.get_tracer = MagicMock()
sys.modules["neural_hive_observability"] = mock_tracer_module

import engine.execution_engine as execution_engine_module
from engine.execution_engine import ExecutionEngine


@pytest.fixture(autouse=True)
def _reset_tracer_mock(monkeypatch):
    """Configura o tracer mock antes de cada teste.

    Faz patch directo de ``get_tracer`` no namespace do módulo do engine, tornando
    os testes de ``_execute_ticket`` imunes à poluição de ``sys.modules`` por outros
    ficheiros de teste (que reatribuem/mutam o módulo neural_hive_observability).
    """
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    span.set_attribute = MagicMock()

    tracer = MagicMock()
    tracer.start_as_current_span = MagicMock(return_value=span)
    monkeypatch.setattr(execution_engine_module, "get_tracer", lambda: tracer)


class StubTicketClient:
    """Cliente de ticket stub que regista as chamadas de update_ticket_status."""

    def __init__(self, tickets_by_id=None):
        self.tickets_by_id = tickets_by_id or {}
        self.status_updates = []

    async def get_ticket(self, ticket_id):
        return self.tickets_by_id[ticket_id]

    async def update_ticket_status(self, ticket_id, status, **kwargs):
        self.status_updates.append((ticket_id, status, kwargs))


class StubResultProducer:
    """Producer stub que regista os resultados publicados."""

    def __init__(self):
        self.published = []

    async def publish_result(self, ticket_id, status, result, **kwargs):
        self.published.append((ticket_id, status, result, kwargs))


class CountingMetrics:
    """Métricas mínimas que contam incrementos de simulated_total por labels."""

    def __init__(self):
        self.simulated_total = MagicMock()
        self.tickets_completed_total = MagicMock()
        self.tickets_failed_total = MagicMock()
        self.task_duration_seconds = MagicMock()


def _make_engine(ticket_client=None, result_producer=None, metrics=None, strict=False):
    """Cria um ExecutionEngine com dependências mínimas para testes de unidade."""
    config = SimpleNamespace(
        max_concurrent_tasks=5,
        max_retries_per_ticket=0,
        retry_backoff_base_seconds=0,
        retry_backoff_max_seconds=0,
        task_timeout_multiplier=1.0,
        strict_real_path=strict,
    )
    return ExecutionEngine(
        config=config,
        ticket_client=ticket_client or StubTicketClient(),
        result_producer=result_producer or StubResultProducer(),
        dependency_coordinator=MagicMock(),
        executor_registry=MagicMock(),
        redis_client=None,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# _has_real_evidence — contrato por task_type
# ---------------------------------------------------------------------------


def test_evidence_query_com_count_e_documentos():
    engine = _make_engine()
    result = {"success": True, "output": {"documents": [{"id": 1}], "count": 1}}
    ok, reason = engine._has_real_evidence("QUERY", result)
    assert ok is True
    assert reason is None


def test_evidence_query_sem_count_falha():
    engine = _make_engine()
    result = {"success": True, "output": {"documents": []}}
    ok, reason = engine._has_real_evidence("QUERY", result)
    assert ok is False
    assert reason is not None


def test_evidence_query_redis_get_passa():
    """C1: Redis GET devolve {key,value,exists} (sem count/lista) e é trabalho real."""
    engine = _make_engine()
    # Dict de saída real do query_executor._execute_redis_query (operation=get).
    result = {
        "success": True,
        "output": {"key": "session:42", "value": {"user": "x"}, "exists": True},
        "metadata": {"executor": "QueryExecutor", "query_type": "redis", "operation": "get"},
    }
    ok, reason = engine._has_real_evidence("QUERY", result)
    assert ok is True
    assert reason is None


def test_evidence_query_redis_get_inexistente_passa():
    """C1: Redis GET de chave ausente (exists=False) ainda é evidência real (operação ocorreu)."""
    engine = _make_engine()
    result = {
        "success": True,
        "output": {"key": "missing", "value": None, "exists": False},
        "metadata": {"executor": "QueryExecutor", "query_type": "redis", "operation": "get"},
    }
    ok, reason = engine._has_real_evidence("QUERY", result)
    assert ok is True
    assert reason is None


def test_evidence_transform_noop_falha():
    engine = _make_engine()
    result = {"success": True, "output": {"transformed_data": None, "noop": True}}
    ok, reason = engine._has_real_evidence("TRANSFORM", result)
    assert ok is False
    assert "noop" in reason.lower()


def test_evidence_transform_real_passa():
    engine = _make_engine()
    result = {"success": True, "output": {"transformed_data": [1, 2, 3]}}
    ok, reason = engine._has_real_evidence("TRANSFORM", result)
    assert ok is True
    assert reason is None


def test_evidence_transform_csv_rows_passa():
    """C2: CSV transform devolve {rows, count} e é trabalho real."""
    engine = _make_engine()
    # Dict de saída real do transform_executor._execute_csv_transform (output_format=json).
    result = {
        "success": True,
        "output": {"rows": [{"a": "1"}, {"a": "2"}], "count": 2},
        "metadata": {"executor": "TransformExecutor", "transform_type": "csv"},
    }
    ok, reason = engine._has_real_evidence("TRANSFORM", result)
    assert ok is True
    assert reason is None


def test_evidence_transform_csv_vazio_mas_real_passa():
    """C2: CSV vazio (rows=[], count=0) ainda é trabalho real (parse ocorreu, não é noop)."""
    engine = _make_engine()
    result = {
        "success": True,
        "output": {"rows": [], "count": 0},
        "metadata": {"executor": "TransformExecutor", "transform_type": "csv"},
    }
    ok, reason = engine._has_real_evidence("TRANSFORM", result)
    assert ok is True
    assert reason is None


def test_evidence_validate_simulated_falha():
    engine = _make_engine()
    result = {"success": True, "output": {}, "metadata": {"simulated": True}}
    ok, reason = engine._has_real_evidence("VALIDATE", result)
    assert ok is False
    assert "simul" in reason.lower()


def test_evidence_validate_real_passa():
    engine = _make_engine()
    result = {"success": True, "output": {"result": "allow"}, "metadata": {"simulated": False}}
    ok, reason = engine._has_real_evidence("VALIDATE", result)
    assert ok is True


def test_evidence_build_com_digest_passa():
    engine = _make_engine()
    result = {
        "success": True,
        "output": {"artifact": "ghcr.io/x/y:1", "digest": "sha256:abc"},
    }
    ok, reason = engine._has_real_evidence("BUILD", result)
    assert ok is True


def test_evidence_build_sem_referencia_falha():
    engine = _make_engine()
    result = {"success": True, "output": {}}
    ok, reason = engine._has_real_evidence("BUILD", result)
    assert ok is False


def test_evidence_build_sem_digest_falha():
    """Gap#2: artefacto sem digest verificável -> evidência inválida (contrato §4)."""
    engine = _make_engine()
    result = {"success": True, "output": {"artifact": "ghcr.io/x/y:1"}}
    ok, reason = engine._has_real_evidence("BUILD", result)
    assert ok is False
    assert "digest" in (reason or "").lower()


def test_evidence_deploy_simulated_falha():
    engine = _make_engine()
    result = {"success": True, "output": {}, "metadata": {"simulated": True}}
    ok, reason = engine._has_real_evidence("DEPLOY", result)
    assert ok is False


def test_evidence_deploy_reconciliado_passa():
    engine = _make_engine()
    result = {
        "success": True,
        "output": {"resource": "app", "status": "Healthy"},
        "metadata": {"simulated": False},
    }
    ok, reason = engine._has_real_evidence("DEPLOY", result)
    assert ok is True


def test_evidence_execute_exit_code_real_passa():
    engine = _make_engine()
    result = {"success": True, "output": {"exit_code": 0, "stdout": "ok"}}
    ok, reason = engine._has_real_evidence("EXECUTE", result)
    assert ok is True


def test_evidence_execute_stdout_simulacao_falha():
    engine = _make_engine()
    result = {"success": True, "output": {"exit_code": 0, "stdout": "[SIMULAÇÃO] executado"}}
    ok, reason = engine._has_real_evidence("EXECUTE", result)
    assert ok is False


def test_evidence_generate_code_com_artifact_id_passa():
    engine = _make_engine()
    result = {"success": True, "output": {"code_artifact_id": "art-123"}}
    ok, reason = engine._has_real_evidence("GENERATE_CODE", result)
    assert ok is True


def test_evidence_generate_code_sem_artifact_id_falha():
    engine = _make_engine()
    result = {"success": True, "output": {}}
    ok, reason = engine._has_real_evidence("GENERATE_CODE", result)
    assert ok is False


def test_evidence_simulated_metadata_e_sempre_nao_real():
    """Regra transversal: metadata.simulated==True nunca é trabalho real."""
    engine = _make_engine()
    result = {
        "success": True,
        "output": {"count": 5, "documents": [1]},
        "metadata": {"simulated": True},
    }
    ok, reason = engine._has_real_evidence("QUERY", result)
    assert ok is False
    assert "simul" in reason.lower()


def test_evidence_output_noop_e_sempre_nao_real():
    """Regra transversal: output.noop==True nunca é trabalho real."""
    engine = _make_engine()
    result = {"success": True, "output": {"noop": True, "count": 0}}
    ok, reason = engine._has_real_evidence("QUERY", result)
    assert ok is False
    assert "noop" in reason.lower()


def test_evidence_task_type_desconhecido_e_unverified():
    """task_type sem evidência definida: aceita (ok=True) mas com razão unverified."""
    engine = _make_engine()
    result = {"success": True, "output": {"x": 1}}
    ok, reason = engine._has_real_evidence("COMPENSATE", result)
    assert ok is True
    assert reason == "unverified"


# ---------------------------------------------------------------------------
# Gate em _execute_ticket — COMPLETED vs FAILED
# ---------------------------------------------------------------------------


def _patch_engine_for_execute(engine, result):
    """Configura os métodos auxiliares do engine para isolar o gate de evidência."""
    engine.dependency_coordinator.wait_for_dependencies = AsyncMock()
    engine._inject_dependency_outputs = AsyncMock()
    engine._execute_task_with_retry = AsyncMock(return_value=result)
    engine._mark_ticket_processed = AsyncMock()
    engine._clear_ticket_processing = AsyncMock()


@pytest.mark.asyncio()
async def test_caminho_real_query_marca_completed():
    """(a) Caminho real (query com count+documents) -> COMPLETED."""
    client = StubTicketClient()
    producer = StubResultProducer()
    engine = _make_engine(client, producer, metrics=CountingMetrics(), strict=True)
    result = {"success": True, "output": {"documents": [{"id": 1}], "count": 1}}
    _patch_engine_for_execute(engine, result)

    await engine._execute_ticket({"ticket_id": "q1", "task_type": "QUERY"})

    statuses = [s for (_, s, _) in client.status_updates]
    assert "COMPLETED" in statuses
    assert "FAILED" not in statuses


@pytest.mark.asyncio()
async def test_simulacao_strict_marca_failed_com_razao():
    """(b) Simulação com strict_real_path=True -> FAILED com razão real_path_unverified."""
    client = StubTicketClient()
    producer = StubResultProducer()
    metrics = CountingMetrics()
    engine = _make_engine(client, producer, metrics=metrics, strict=True)
    result = {"success": True, "output": {}, "metadata": {"simulated": True}}
    _patch_engine_for_execute(engine, result)

    await engine._execute_ticket({"ticket_id": "v1", "task_type": "VALIDATE"})

    statuses = [s for (_, s, _) in client.status_updates]
    assert "FAILED" in statuses
    assert "COMPLETED" not in statuses
    # razão de falha propagada
    failed = next(kw for (_, s, kw) in client.status_updates if s == "FAILED")
    assert "real_path_unverified" in (failed.get("error_message") or "")
    # métrica de simulação incrementada
    metrics.simulated_total.labels.assert_called()


@pytest.mark.asyncio()
async def test_noop_observacao_marca_completed_mas_conta_metrica():
    """(b) noop com strict_real_path=False -> COMPLETED mas simulated_total++."""
    client = StubTicketClient()
    producer = StubResultProducer()
    metrics = CountingMetrics()
    engine = _make_engine(client, producer, metrics=metrics, strict=False)
    result = {"success": True, "output": {"transformed_data": None, "noop": True}}
    _patch_engine_for_execute(engine, result)

    await engine._execute_ticket({"ticket_id": "t1", "task_type": "TRANSFORM"})

    statuses = [s for (_, s, _) in client.status_updates]
    assert "COMPLETED" in statuses
    assert "FAILED" not in statuses
    # métrica de simulação incrementada mesmo em modo observação
    metrics.simulated_total.labels.assert_called_with(executor="transform", task_type="TRANSFORM")


@pytest.mark.asyncio()
async def test_evidencia_especifica_ausente_strict_marca_failed():
    """(Gap#3) QUERY sem count/documentos (não simulado) + strict -> FAILED real_path_unverified.

    Caminho distinto de ``simulated=True``: o resultado não está marcado como simulação
    nem é noop, mas falha o contrato de evidência específico do task_type. Deve mesmo
    assim ir a FAILED em modo estrito e incrementar ``simulated_total``.
    """
    client = StubTicketClient()
    producer = StubResultProducer()
    metrics = CountingMetrics()
    engine = _make_engine(client, producer, metrics=metrics, strict=True)
    result = {"success": True, "output": {"documents": []}}
    _patch_engine_for_execute(engine, result)

    await engine._execute_ticket({"ticket_id": "q-missing", "task_type": "QUERY"})

    statuses = [s for (_, s, _) in client.status_updates]
    assert "FAILED" in statuses
    assert "COMPLETED" not in statuses
    failed = next(kw for (_, s, kw) in client.status_updates if s == "FAILED")
    assert "real_path_unverified" in (failed.get("error_message") or "")
    # simulated_total incrementado mesmo sem metadata.simulated.
    metrics.simulated_total.labels.assert_called_with(executor="query", task_type="QUERY")


@pytest.mark.asyncio()
async def test_execucao_falhada_continua_failed():
    """Resultado success=False continua FAILED (não regressão do ramo existente)."""
    client = StubTicketClient()
    producer = StubResultProducer()
    engine = _make_engine(client, producer, metrics=CountingMetrics(), strict=True)
    result = {"success": False, "output": None, "error": "boom"}
    _patch_engine_for_execute(engine, result)

    await engine._execute_ticket({"ticket_id": "f1", "task_type": "QUERY"})

    statuses = [s for (_, s, _) in client.status_updates]
    assert "FAILED" in statuses
    assert "COMPLETED" not in statuses
