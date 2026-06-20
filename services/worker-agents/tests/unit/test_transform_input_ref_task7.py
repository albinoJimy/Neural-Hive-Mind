"""
Testes da Task 7 — "Transform real (data-flow semântico do STE)".

Cobre os 3 caminhos obrigatórios da DoD:
1. Caminho real: transform com `input_ref` + `operations` + `dependency_outputs`
   resolve o input_ref para os documentos reais, aplica operations e produz output
   derivado (noop != True, success True).
2. Fail/degradação MARCADA: `input_ref` presente mas sem dependency_outputs (ou
   campo ausente) → resultado honesto marcado (real_path_unavailable), NUNCA um
   transform "completo" silencioso.
3. Sem simulação silenciosa: sem input_ref nem dependência → no-op gracioso
   marcado; helper `resolve_input_ref` testado unitariamente (vários formatos +
   fallbacks).

NÃO modifica testes existentes (contrato). Ficheiro NOVO.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from src.executors import transform_executor as transform_executor_module
from src.executors.transform_executor import TransformExecutor, resolve_input_ref


@pytest.fixture(autouse=True)
def _patch_tracer(monkeypatch):
    """Garante que get_tracer devolve um tracer com span context manager.

    Independente da ordem de import na suite completa (o módulo real de
    observabilidade pode devolver None), forçamos um tracer mockado.
    """
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=False)
    span.set_attribute = MagicMock()
    tracer = MagicMock()
    tracer.start_as_current_span = MagicMock(return_value=span)
    monkeypatch.setattr(transform_executor_module, "get_tracer", lambda: tracer)


def _make_executor():
    config = SimpleNamespace()
    metrics = SimpleNamespace(real_path_unavailable_total=MagicMock())
    metrics.real_path_unavailable_total.labels.return_value = MagicMock()
    return TransformExecutor(config=config, metrics=metrics)


def _base_ticket(parameters):
    return {
        "ticket_id": "t-transform-1",
        "task_id": "t-transform-1",
        "task_type": "transform",
        "parameters": parameters,
    }


# ---------------------------------------------------------------------------
# Helper puro resolve_input_ref (unitário)
# ---------------------------------------------------------------------------
class TestResolveInputRef:
    def test_generico_dep_output_documents(self):
        dep_outputs = {"q1": {"output": {"documents": [{"a": 1}], "count": 1}}}
        value, reason = resolve_input_ref("${dep.output.documents}", dep_outputs)
        assert reason is None
        assert value == [{"a": 1}]

    def test_explicito_por_dep_id(self):
        dep_outputs = {
            "q1": {"output": {"documents": [{"a": 1}]}},
            "q2": {"output": {"results": [{"b": 2}]}},
        }
        value, reason = resolve_input_ref("${q2.output.results}", dep_outputs)
        assert reason is None
        assert value == [{"b": 2}]

    def test_fallback_documents_para_results(self):
        # Pede documents mas a dependência só tem results → fallback.
        dep_outputs = {"q1": {"output": {"results": [{"b": 2}]}}}
        value, reason = resolve_input_ref("${dep.output.documents}", dep_outputs)
        assert reason is None
        assert value == [{"b": 2}]

    def test_output_aninhado_sem_chave_output(self):
        # dependency_output sem chave 'output' (já é o output direto).
        dep_outputs = {"q1": {"documents": [{"a": 1}]}}
        value, reason = resolve_input_ref("${dep.output.documents}", dep_outputs)
        assert reason is None
        assert value == [{"a": 1}]

    def test_sem_dependency_outputs_devolve_reason(self):
        value, reason = resolve_input_ref("${dep.output.documents}", {})
        assert value is None
        assert reason is not None

    def test_campo_ausente_devolve_reason(self):
        dep_outputs = {"q1": {"output": {"foo": 1}}}
        value, reason = resolve_input_ref("${dep.output.documents}", dep_outputs)
        assert value is None
        assert reason is not None

    def test_input_ref_invalido_devolve_reason(self):
        value, reason = resolve_input_ref("nao-e-um-ref", {"q1": {"output": {}}})
        assert value is None
        assert reason is not None


# ---------------------------------------------------------------------------
# Caminho 1: real — resolve input_ref e aplica operations
# ---------------------------------------------------------------------------
class TestTransformRealPath:
    @pytest.mark.asyncio()
    async def test_resolve_input_ref_e_aplica_count(self):
        executor = _make_executor()
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_ref": "${dep.output.documents}",
                "operations": [{"type": "count"}],
                "dependency_outputs": {
                    "q1": {"output": {"documents": [{"id": 1}, {"id": 2}], "count": 2}}
                },
            }
        )

        result = await executor.execute(ticket)

        assert result["success"] is True
        output = result["output"]
        assert output.get("noop") is not True
        # count derivado real dos 2 documentos
        assert output["transformed_data"] == {"count": 2}

    @pytest.mark.asyncio()
    async def test_caminho_producao_envelope_em_input_data_conta_documentos(self):
        """Caminho de produção (engine): o execution_engine pré-injeta o ENVELOPE
        {documents, count} em input_data. input_ref tem de ter precedência e
        navegar até documents — senão count contaria as 2 chaves do envelope."""
        executor = _make_executor()
        docs = [{"id": i} for i in range(50)]
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_ref": "${dep.output.documents}",
                "operations": [{"type": "count"}],
                # o engine pré-injeta o envelope (dict truthy de 2 chaves) em input_data
                "input_data": {"documents": docs, "count": 50},
                "dependency_outputs": {"q1": {"output": {"documents": docs, "count": 50}}},
            }
        )

        result = await executor.execute(ticket)

        assert result["success"] is True
        assert result["output"].get("noop") is not True
        # 50 documentos reais, NÃO 2 (as chaves do envelope)
        assert result["output"]["transformed_data"] == {"count": 50}

    @pytest.mark.asyncio()
    async def test_input_ref_resolve_lista_vazia_nao_e_noop(self):
        """Query devolveu 0 documentos: lista vazia é dado REAL → count=0, não no-op."""
        executor = _make_executor()
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_ref": "${dep.output.documents}",
                "operations": [{"type": "count"}],
                "input_data": {"documents": [], "count": 0},
                "dependency_outputs": {"q1": {"output": {"documents": [], "count": 0}}},
            }
        )

        result = await executor.execute(ticket)

        assert result["success"] is True
        assert result["output"].get("noop") is not True
        assert result["output"]["transformed_data"] == {"count": 0}

    @pytest.mark.asyncio()
    async def test_resolve_e_aplica_select_keys(self):
        executor = _make_executor()
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_ref": "${dep.output.documents}",
                "operations": [{"type": "select_keys", "keys": ["id"]}],
                "dependency_outputs": {
                    "q1": {"output": {"documents": [{"id": 1, "x": 9}, {"id": 2, "x": 8}]}}
                },
            }
        )

        result = await executor.execute(ticket)

        assert result["success"] is True
        assert result["output"].get("noop") is not True
        assert result["output"]["transformed_data"] == [{"id": 1}, {"id": 2}]


# ---------------------------------------------------------------------------
# Caminho 2: degradação MARCADA — input_ref presente mas não resolve
# ---------------------------------------------------------------------------
class TestTransformDegradacaoMarcada:
    @pytest.mark.asyncio()
    async def test_input_ref_sem_dependency_outputs_falha_marcado(self):
        executor = _make_executor()
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_ref": "${dep.output.documents}",
                "operations": [{"type": "count"}],
                # sem dependency_outputs
            }
        )

        result = await executor.execute(ticket)

        # Resultado honesto: NÃO finge transform completo
        assert result["success"] is False
        assert result["metadata"].get("real_path_unavailable") is True
        assert result["output"].get("noop") is not True
        # métrica de degradação incrementada
        executor.metrics.real_path_unavailable_total.labels.assert_called()

    @pytest.mark.asyncio()
    async def test_input_ref_campo_ausente_falha_marcado(self):
        executor = _make_executor()
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_ref": "${dep.output.documents}",
                "operations": [{"type": "count"}],
                "dependency_outputs": {"q1": {"output": {"foo": 1}}},
            }
        )

        result = await executor.execute(ticket)

        assert result["success"] is False
        assert result["metadata"].get("real_path_unavailable") is True


# ---------------------------------------------------------------------------
# Caminho 3: no-op gracioso só para standalone (sem input_ref nem dependência)
# ---------------------------------------------------------------------------
class TestTransformNoopStandalone:
    @pytest.mark.asyncio()
    async def test_standalone_sem_input_ref_noop_gracioso(self):
        executor = _make_executor()
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_data": None,
                "operations": [],
                # sem input_ref, sem dependency_outputs
            }
        )

        result = await executor.execute(ticket)

        assert result["success"] is True
        assert result["output"].get("noop") is True
        # standalone não toca na métrica de degradação
        executor.metrics.real_path_unavailable_total.labels.assert_not_called()

    @pytest.mark.asyncio()
    async def test_input_data_direto_ainda_funciona(self):
        # Caso em que dependency_outputs já injetou input_data (encadeamento simples).
        executor = _make_executor()
        ticket = _base_ticket(
            {
                "transform_type": "json",
                "input_data": [{"id": 1}, {"id": 2}, {"id": 3}],
                "operations": [{"type": "count"}],
            }
        )

        result = await executor.execute(ticket)

        assert result["success"] is True
        assert result["output"].get("noop") is not True
        assert result["output"]["transformed_data"] == {"count": 3}
