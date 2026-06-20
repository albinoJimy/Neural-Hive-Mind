"""
Testes do wiring do Fluxo G (Task 5 — caminho-real-first-class).

Cobre:
1. Registo: as 12 activities G6-G13 invocadas pelo FluxoGWorkflow estão
   importadas/registadas no temporal_worker (evita ActivityNotRegistered).
2. Persistência: generate_code (G6) persiste code_artifact_id em MongoDB.
3. Fail-safe: sem mongodb_client, generate_code continua e marca degradação.
4. Porta: URLs do code-forge usam :8080 (configurável via CODE_FORGE_URL),
   não :8020.
"""

import ast
import importlib
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Activities G6-G13 invocadas pelo FluxoGWorkflow (caminho real).
# Conjunto exato derivado dos imports do workflow.
G6_G13_ACTIVITIES = {
    # G6
    "generate_code",
    # G7
    "build_package",
    "validate_build_quality",
    # G8
    "deploy_software",
    "verify_deployment",
    "rollback_deployment",
    # G9-G13
    "collect_post_deployment_metrics",
    "analyze_deployment_quality",
    "generate_specialist_feedback",
    "record_feedback_for_ml",
    "check_feedback_thresholds",
}


def _worker_source() -> str:
    worker_path = Path(__file__).parent.parent / "src" / "workers" / "temporal_worker.py"
    return worker_path.read_text(encoding="utf-8")


def _registered_activity_names() -> set[str]:
    """
    Extrai estaticamente os nomes na lista `activities=[...]` do Worker(...)
    em temporal_worker.py, sem necessitar de um Temporal real.
    """
    source = _worker_source()
    tree = ast.parse(source)

    names: set[str] = set()
    for node in ast.walk(tree):
        # Procurar chamada Worker(...) e o keyword activities=[...]
        if isinstance(node, ast.Call):
            func = node.func
            func_name = getattr(func, "id", None) or getattr(func, "attr", None)
            if func_name != "Worker":
                continue
            for kw in node.keywords:
                if kw.arg == "activities" and isinstance(kw.value, ast.List):
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Name):
                            names.add(elt.id)
                        elif isinstance(elt, ast.Attribute):
                            names.add(elt.attr)
    return names


def _workflow_invoked_activities() -> set[str]:
    """
    Extrai estaticamente as funções de activity invocadas pelo FluxoGWorkflow
    via workflow.execute_activity(<activity>, ...).
    """
    wf_path = Path(__file__).parent.parent / "src" / "workflows" / "fluxo_g_workflow.py"
    source = wf_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    invoked: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            func_name = getattr(func, "attr", None)
            if func_name != "execute_activity":
                continue
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Name):
                    invoked.add(first.id)
                elif isinstance(first, ast.Attribute):
                    invoked.add(first.attr)
    return invoked


class TestActivityRegistration:
    """G6-G13 devem estar registadas no worker (caminho real, sem Temporal)."""

    def test_all_g6_g13_activities_registered(self):
        registered = _registered_activity_names()
        missing = G6_G13_ACTIVITIES - registered
        assert not missing, (
            f"Activities G6-G13 NÃO registadas no Worker: {sorted(missing)}. "
            "Plano 'generation' daria ActivityNotRegistered."
        )

    def test_no_activity_not_registered_for_fluxo_g(self):
        """
        Toda activity invocada pelo FluxoGWorkflow deve estar registada no
        worker — garantia de ausência de ActivityNotRegistered no plano
        'generation'.
        """
        invoked = _workflow_invoked_activities()
        registered = _registered_activity_names()
        # Sanidade: o workflow invoca de facto as G6-G13 do fluxo feliz.
        # rollback_deployment é uma activity de compensação: está importada e
        # registada, mas não é invocada no caminho feliz (só em rollback).
        happy_path = G6_G13_ACTIVITIES - {"rollback_deployment"}
        assert happy_path.issubset(invoked), (
            "Teste desatualizado: workflow não invoca todas as G6-G13 esperadas. "
            f"Em falta na invocação: {sorted(happy_path - invoked)}"
        )
        not_registered = invoked - registered
        assert not not_registered, (
            "FluxoGWorkflow invoca activities NÃO registadas no Worker "
            f"(ActivityNotRegistered): {sorted(not_registered)}"
        )

    def test_set_code_generation_dependencies_called_with_mongodb(self):
        """O worker deve injetar mongodb_client em code_generation activities."""
        source = _worker_source()
        assert "set_code_generation_dependencies" in source, (
            "set_code_generation_dependencies não é chamada no worker — "
            "code_generation_activity ficaria sem mongodb_client."
        )
        assert "mongodb_client=self.mongodb_client" in source or (
            "set_code_generation_dependencies" in source and "mongodb_client" in source
        )


@pytest.fixture()
def reload_code_gen_module():
    """
    Recarrega o módulo code_generation_activity garantindo estado de
    dependências limpo entre testes.
    """
    import src.activities.code_generation_activity as mod

    importlib.reload(mod)
    yield mod
    importlib.reload(mod)


def _make_code_forge_responses(artifact_id="ART-123"):
    """Cria mock client cujo POST inicia geração e GET devolve completed."""
    post_resp = MagicMock()
    post_resp.status_code = 202
    post_resp.json.return_value = {"request_id": "REQ-1"}

    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = {
        "status": "completed",
        "artifacts": [
            {
                "artifact_type": "code",
                "artifact_id": artifact_id,
                "language": "python",
                "framework": "fastapi",
                "generation_method": "LLM",
                "confidence_score": 0.9,
                "lines_of_code": 120,
            }
        ],
        "code_preview": "print('hi')",
    }

    client = MagicMock()
    client.post = AsyncMock(return_value=post_resp)
    client.get = AsyncMock(return_value=get_resp)
    return client


@pytest.mark.asyncio()
class TestGenerateCodePersistence:
    async def test_persists_code_artifact_id_in_mongodb(self, reload_code_gen_module):
        mod = reload_code_gen_module
        http_client = _make_code_forge_responses(artifact_id="ART-PERSIST")

        # Mongo mock: db["code_artifacts"].update_one(...)
        collection = MagicMock()
        collection.update_one = AsyncMock(return_value=MagicMock())
        db = MagicMock()
        db.__getitem__.return_value = collection
        mongodb_client = MagicMock()
        mongodb_client.db = db

        mod.set_code_generation_dependencies(http_client=http_client, mongodb_client=mongodb_client)

        cognitive_plan = {"plan_id": "PLAN-1", "intent_id": "INT-1"}
        result = await mod.generate_code({}, {}, cognitive_plan)

        assert result["code_artifact_id"] == "ART-PERSIST"

        # Coleção correta
        db.__getitem__.assert_any_call("code_artifacts")
        # Upsert chamado com o artifact_id correto
        assert collection.update_one.await_count == 1
        call = collection.update_one.await_args
        # filter por code_artifact_id (idempotência)
        filter_arg = call.args[0] if call.args else call.kwargs.get("filter")
        assert filter_arg == {"code_artifact_id": "ART-PERSIST"}
        # deve usar upsert para idempotência
        assert call.kwargs.get("upsert") is True
        # documento contém plan_id
        update_doc = call.args[1] if len(call.args) > 1 else call.kwargs.get("update")
        set_doc = update_doc.get("$set", update_doc)
        assert set_doc.get("plan_id") == "PLAN-1"
        assert set_doc.get("code_artifact_id") == "ART-PERSIST"

    async def test_failsafe_without_mongodb_marks_degraded(self, reload_code_gen_module):
        mod = reload_code_gen_module
        http_client = _make_code_forge_responses(artifact_id="ART-NOMONGO")

        mod.set_code_generation_dependencies(http_client=http_client, mongodb_client=None)

        # Capturar chamadas ao logger.warning para verificar degraded=True.
        warnings_captured = []

        class _SpyLogger:
            def warning(self, event=None, **kwargs):
                warnings_captured.append((event, kwargs))

            def info(self, *a, **k):
                pass

            def error(self, *a, **k):
                pass

            def exception(self, *a, **k):
                pass

            def debug(self, *a, **k):
                pass

        mod.logger = _SpyLogger()

        cognitive_plan = {"plan_id": "PLAN-2", "intent_id": "INT-2"}
        # Não deve rebentar mesmo sem MongoDB
        result = await mod.generate_code({}, {}, cognitive_plan)

        assert result["code_artifact_id"] == "ART-NOMONGO"
        # Marcou degradação (warning com degraded=True)
        assert any(
            kw.get("degraded") is True for _, kw in warnings_captured
        ), "Sem mongodb_client, generate_code deve marcar degradação (log degraded=True)."


class TestCodeForgePort:
    def test_generate_code_uses_8080_not_8020(self):
        """As URLs do code-forge devem usar :8080 por default, não :8020."""
        import src.activities.code_generation_activity as mod

        importlib.reload(mod)
        src_code = inspect.getsource(mod)
        assert ":8020" not in src_code, "code_generation_activity ainda referencia :8020 hardcoded."

    def test_build_package_uses_8080_not_8020(self):
        import src.activities.build_package_activity as mod

        importlib.reload(mod)
        src_code = inspect.getsource(mod)
        assert ":8020" not in src_code, "build_package_activity ainda referencia :8020 hardcoded."

    def test_code_forge_url_env_override(self, monkeypatch):
        """CODE_FORGE_URL deve sobrepor a base URL."""
        monkeypatch.setenv("CODE_FORGE_URL", "http://code-forge:9999")
        import src.activities.code_generation_activity as mod

        importlib.reload(mod)
        base = mod._code_forge_base_url()
        assert base == "http://code-forge:9999"
        # cleanup: restaurar default
        monkeypatch.delenv("CODE_FORGE_URL", raising=False)
        importlib.reload(mod)
        assert mod._code_forge_base_url() == "http://code-forge:8080"
