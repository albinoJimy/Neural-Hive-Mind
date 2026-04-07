import asyncio
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from src.services.playbook_executor import PlaybookExecutor


@pytest.mark.asyncio
async def test_execute_playbook_runs_actions(tmp_path, mock_tracer):
    playbook_path = tmp_path / "sample.yaml"
    playbook_content = {
        "playbook_name": "sample",
        "actions": [
            {"type": "update_policy", "parameters": {"policy_name": "p1", "enabled": True}},
            {
                "type": "notify_agent",
                "parameters": {
                    "agent_id": "worker-1",
                    "notification_type": "INFO",
                    "message": "ok",
                },
            },
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("sample", context={})

    assert result["success"] is True
    assert result["total_actions"] == 2


@pytest.mark.asyncio
async def test_execute_playbook_timeout(tmp_path, mock_tracer):
    playbook_path = tmp_path / "slow.yaml"
    playbook_content = {"playbook_name": "slow", "actions": [{"type": "update_policy"}]}
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)

        async def slow_actions(actions, context, on_action_completed=None):
            await asyncio.sleep(0.05)
            return {"success": True, "actions": []}

        executor._execute_actions = slow_actions  # type: ignore

        result = await executor.execute_playbook("slow", context={}, timeout_seconds=0.01)

    assert result["success"] is False
    assert result.get("status") == "TIMEOUT"


@pytest.mark.asyncio
async def test_wait_action(tmp_path, mock_tracer):
    """Test the wait action."""
    playbook_path = tmp_path / "wait_test.yaml"
    playbook_content = {
        "playbook_name": "wait_test",
        "actions": [{"type": "wait", "parameters": {"seconds": 0.1}}],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("wait_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_apply_policy_action(tmp_path, mock_tracer):
    """Test the apply_policy action (alias for update_policy)."""
    playbook_path = tmp_path / "apply_policy_test.yaml"
    playbook_content = {
        "playbook_name": "apply_policy_test",
        "actions": [
            {"type": "apply_policy", "parameters": {"policy_name": "test-policy", "enabled": True}}
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("apply_policy_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_delete_pod_action(tmp_path, mock_tracer):
    """Test the delete_pod action."""
    playbook_path = tmp_path / "delete_pod_test.yaml"
    playbook_content = {
        "playbook_name": "delete_pod_test",
        "actions": [
            {"type": "delete_pod", "parameters": {"pod_name": "test-pod", "namespace": "default"}}
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("delete_pod_test", context={})

    # Sem Kubernetes configurado, a ação retorna erro, mas execução completa
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_patch_deployment_action(tmp_path, mock_tracer):
    """Test the patch_deployment action."""
    playbook_path = tmp_path / "patch_deployment_test.yaml"
    playbook_content = {
        "playbook_name": "patch_deployment_test",
        "actions": [
            {
                "type": "patch_deployment",
                "parameters": {
                    "deployment_name": "test-deployment",
                    "namespace": "default",
                    "patch": {"spec": {"replicas": 3}},
                },
            }
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("patch_deployment_test", context={})

    # Sem Kubernetes configurado, a ação retorna erro, mas execução completa
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_cleanup_poison_messages_action(tmp_path, mock_tracer):
    """Test the cleanup_poison_messages action."""
    playbook_path = tmp_path / "cleanup_poison_test.yaml"
    playbook_content = {
        "playbook_name": "cleanup_poison_test",
        "actions": [
            {
                "type": "cleanup_poison_messages",
                "parameters": {"topic": "test-topic", "partition": 0, "offset": 123},
            }
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("cleanup_poison_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 1


@pytest.mark.asyncio
async def test_combined_actions(tmp_path, mock_tracer):
    """Test a playbook with multiple new action types."""
    playbook_path = tmp_path / "combined_test.yaml"
    playbook_content = {
        "playbook_name": "combined_test",
        "actions": [
            {"type": "wait", "parameters": {"seconds": 0.01}},
            {"type": "update_policy", "parameters": {"policy_name": "test-policy"}},
            {
                "type": "notify_agent",
                "parameters": {
                    "agent_id": "test-agent",
                    "notification_type": "INFO",
                    "message": "test",
                },
            },
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("combined_test", context={})

    assert result["success"] is True
    assert result["total_actions"] == 3


# ============================================================================
# Tests de Validação Pydantic para Playbooks (GAPS-04-02)
# ============================================================================


def test_playbook_action_valid_type():
    """Testa validação de tipo de ação válido."""
    from src.models.remediation_models import PlaybookAction, ActionType

    action = PlaybookAction(type=ActionType.REALLOCATE_TICKET)
    assert action.type == ActionType.REALLOCATE_TICKET
    assert action.parameters == {}
    assert action.continue_on_failure is False


def test_playbook_action_invalid_type():
    """Testa erro para tipo de ação inválido."""
    from src.models.remediation_models import PlaybookAction
    from pydantic import ValidationError

    try:
        PlaybookAction(type="invalid_action_type")
        assert False, "Deveria ter levantado ValidationError"
    except ValidationError as e:
        # Pydantic v2 error message format
        assert "validation error" in str(e) or "Input should be" in str(e)


def test_playbook_action_with_parameters():
    """Testa ação com parâmetros."""
    from src.models.remediation_models import PlaybookAction, ActionType

    action = PlaybookAction(
        type=ActionType.REALLOCATE_TICKET,
        parameters={"ticket_id": "t-123", "worker_id": "worker-1"},
        description="Realocar ticket para worker específico",
        continue_on_failure=True,
        timeout_seconds=60,
    )

    assert action.type == ActionType.REALLOCATE_TICKET
    assert action.parameters["ticket_id"] == "t-123"
    assert action.continue_on_failure is True
    assert action.timeout_seconds == 60


def test_playbook_model_valid():
    """Testa modelo Playbook válido."""
    from datetime import datetime
    from src.models.remediation_models import Playbook, PlaybookAction, ActionType

    playbook = Playbook(
        playbook_name="test_playbook",
        description="Playbook de teste",
        timeout_seconds=300,
        actions=[
            PlaybookAction(type=ActionType.REALLOCATE_TICKET),
            PlaybookAction(type=ActionType.WAIT, parameters={"seconds": 5}),
        ],
        tags=["test", "unit"],
        version="1.0.0",
    )

    assert playbook.playbook_name == "test_playbook"
    assert len(playbook.actions) == 2


def test_playbook_model_empty_actions():
    """Testa erro quando playbook não tem ações."""
    from src.models.remediation_models import Playbook
    from pydantic import ValidationError

    try:
        Playbook(playbook_name="empty", actions=[])
        assert False, "Deveria ter levantado ValidationError"
    except ValidationError as e:
        # Pydantic v2 error message format
        assert "at least 1 item" in str(e) or "List should have at least" in str(e)


def test_playbook_validation_result():
    """Testa modelo de resultado de validação."""
    from src.models.remediation_models import PlaybookValidationResult

    result = PlaybookValidationResult(
        valid=True,
        playbook_name="test",
        errors=[],
        warnings=["Timeout muito alto"],
        action_count=3,
        parsed_actions=["reallocate_ticket", "wait", "log"],
        estimated_duration_seconds=150,
    )

    assert result.valid is True
    assert len(result.warnings) == 1
    assert result.action_count == 3
    assert result.estimated_duration_seconds == 150


def test_validate_playbook_structure_valid(tmp_path):
    """Testa validação de estrutura de playbook válido."""
    playbook_path = tmp_path / "valid_playbook.yaml"  # Filename must match playbook_name
    playbook_content = {
        "playbook_name": "valid_playbook",
        "description": "Playbook válido para teste",
        "timeout_seconds": 300,
        "actions": [
            {"type": "reallocate_ticket", "parameters": {"ticket_id": "t-123"}},
            {"type": "wait", "parameters": {"seconds": 5}},
        ],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
    result = executor.validate_playbook_structure("valid_playbook")

    assert result["valid"] is True
    assert result["action_count"] == 2
    assert "reallocate_ticket" in result["parsed_actions"]
    assert "wait" in result["parsed_actions"]
    assert len(result["errors"]) == 0


def test_validate_playbook_structure_not_found(tmp_path):
    """Testa validação de playbook inexistente."""
    executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
    result = executor.validate_playbook_structure("inexistente")

    assert result["valid"] is False
    assert "não encontrado" in result["errors"][0]


def test_validate_playbook_structure_invalid_action_type(tmp_path):
    """Testa validação com tipo de ação inválido."""
    playbook_path = tmp_path / "invalid_type.yaml"
    playbook_content = {
        "playbook_name": "invalid_type",
        "actions": [{"type": "acao_inexistente", "parameters": {}}],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
    result = executor.validate_playbook_structure("invalid_type")

    assert result["valid"] is False
    # Pydantic v2 error message might be different
    assert len(result["errors"]) > 0


def test_validate_playbook_structure_warnings(tmp_path):
    """Testa geração de avisos na validação."""
    playbook_path = tmp_path / "warnings.yaml"
    # Criar 25 ações para gerar warning de "muitas ações"
    actions = [{"type": "log", "parameters": {"message": f"msg{i}"}} for i in range(25)]
    playbook_content = {
        "playbook_name": "warnings",
        "timeout_seconds": 700,  # Gera warning de timeout alto
        "actions": actions,
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
    result = executor.validate_playbook_structure("warnings")

    assert result["valid"] is True
    assert len(result["warnings"]) > 0
    assert any("muitas ações" in w for w in result["warnings"])
    assert any("Timeout muito alto" in w for w in result["warnings"])


def test_validate_playbook_structure_from_dict(tmp_path):
    """Testa validação passando dict diretamente."""
    executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)

    playbook_data = {
        "playbook_name": "from_dict",
        "actions": [{"type": "wait", "parameters": {"seconds": 1}}],
    }

    result = executor.validate_playbook_structure("from_dict", playbook_data=playbook_data)

    assert result["valid"] is True
    assert result["action_count"] == 1


@pytest.mark.asyncio
async def test_execute_playbook_with_validation_enabled(tmp_path, mock_tracer):
    """Testa execução com validação habilitada."""
    playbook_path = tmp_path / "validated.yaml"
    playbook_content = {
        "playbook_name": "validated",
        "actions": [{"type": "wait", "parameters": {"seconds": 0.01}}],
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        # validate_before_exec=True é o default
        result = await executor.execute_playbook("validated", context={})

    assert result["success"] is True


@pytest.mark.asyncio
async def test_execute_playbook_invalid_structure_fails(tmp_path, mock_tracer):
    """Testa que playbook com estrutura inválida falha na execução."""
    playbook_path = tmp_path / "invalid.yaml"
    playbook_content = {
        "playbook_name": "invalid",
        "actions": [{"type": "tipo_invalido"}],  # Tipo inválido
    }
    playbook_path.write_text(yaml.safe_dump(playbook_content))

    with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
        executor = PlaybookExecutor(playbooks_dir=str(tmp_path), k8s_in_cluster=False)
        result = await executor.execute_playbook("invalid", context={})

    assert result["success"] is False
    assert "validation" in str(result.get("error", "")).lower()


def test_all_action_types_defined():
    """Testa que todos os tipos de ação esperados estão definidos."""
    from src.models.remediation_models import ActionType

    expected_types = {
        "reallocate_ticket",
        "reallocate_multiple_tickets",
        "update_ticket_status",
        "get_ticket",
        "pause_workflow",
        "resume_workflow",
        "trigger_replanning",
        "get_workflow_status",
        "check_worker_health",
        "check_service_health",
        "restart_pod",
        "delete_pod",
        "scale_deployment",
        "check_kafka_lag",
        "reset_consumer_offset",
        "check_database_connection",
        "execute_query",
        "wait",
        "log",
        "notify",
    }

    actual_types = {t.value for t in ActionType}

    assert expected_types.issubset(actual_types), f"Missing types: {expected_types - actual_types}"

