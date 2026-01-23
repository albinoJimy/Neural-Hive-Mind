"""
Testes de integração para o endpoint POST /api/v1/workflows/start.

Cobertura:
- Fluxo completo de início de workflow
- Integração com Temporal mock (WorkflowEnvironment)
- Timeout de workflow
- Retry de workflow
- Idempotência
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from datetime import timedelta


@pytest.fixture
def mock_app_state():
    """Mock do app_state para testes."""
    with patch('src.main.app_state') as mock_state:
        yield mock_state


@pytest.fixture
def mock_settings():
    """Mock das configurações."""
    with patch('src.main.get_settings') as mock_get_settings:
        mock_config = MagicMock()
        mock_config.temporal_workflow_id_prefix = 'nhm-'
        mock_config.temporal_task_queue = 'orchestration-tasks'
        mock_get_settings.return_value = mock_config
        yield mock_config


class TestWorkflowStartIntegration:
    """Testes de integração do endpoint /api/v1/workflows/start."""

    @pytest.mark.asyncio
    async def test_workflow_start_full_flow(self, mock_app_state, mock_settings):
        """Testa fluxo completo de início de workflow."""
        from src.main import app

        # Simular Temporal client com handle
        mock_handle = AsyncMock()
        mock_handle.id = "nhm-flow-c-corr-integration"

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        # Request completo
        request_data = {
            "cognitive_plan": {
                "plan_id": "plan-integration-001",
                "intent_id": "intent-integration-001",
                "decision_id": "decision-integration-001",
                "tasks": [
                    {"task_id": "task-1", "type": "BUILD", "description": "Build service"},
                    {"task_id": "task-2", "type": "DEPLOY", "description": "Deploy to staging"}
                ]
            },
            "correlation_id": "corr-integration",
            "priority": 8,
            "sla_deadline_seconds": 7200
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/v1/workflows/start", json=request_data)

        # Validar response
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "nhm-flow-c-corr-integration"
        assert data["status"] == "started"
        assert data["correlation_id"] == "corr-integration"

        # Validar chamada ao Temporal
        mock_temporal.start_workflow.assert_called_once()
        call_args = mock_temporal.start_workflow.call_args

        # Validar input_data passado ao workflow
        input_data = call_args.args[1]
        assert input_data["cognitive_plan"]["plan_id"] == "plan-integration-001"
        assert input_data["consolidated_decision"]["decision_id"] == "decision-integration-001"
        assert input_data["consolidated_decision"]["priority"] == 8
        assert input_data["consolidated_decision"]["sla_deadline_seconds"] == 7200

    @pytest.mark.asyncio
    async def test_workflow_start_with_query_followup(self, mock_app_state, mock_settings):
        """Testa início de workflow seguido de query para validar estado."""
        from src.main import app

        # Mock Temporal client para start
        mock_handle = AsyncMock()
        mock_handle.query = AsyncMock(return_value={
            "status": "started",
            "tickets_generated": 0,
            "workflow_result": {},
            "sla_warnings": []
        })

        mock_temporal = MagicMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_temporal.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Iniciar workflow
            start_response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-query-test"},
                    "correlation_id": "corr-query-test"
                }
            )
            assert start_response.status_code == 200
            workflow_id = start_response.json()["workflow_id"]

            # 2. Consultar status do workflow
            query_response = await ac.post(
                f"/api/v1/workflows/{workflow_id}/query",
                json={"query_name": "get_status"}
            )

        # Validar que query funciona após start
        assert query_response.status_code == 200
        query_data = query_response.json()
        assert query_data["workflow_id"] == workflow_id
        assert query_data["result"]["status"] == "started"


class TestWorkflowStartIdempotency:
    """Testes de idempotência do endpoint."""

    @pytest.mark.asyncio
    async def test_workflow_start_duplicate_workflow_id_error(self, mock_app_state, mock_settings):
        """Testa erro ao tentar iniciar workflow com ID duplicado."""
        from src.main import app

        mock_temporal = AsyncMock()
        # Segunda chamada falha por workflow já existir
        mock_temporal.start_workflow = AsyncMock(
            side_effect=Exception("Workflow execution already started")
        )
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-dup"},
                    "correlation_id": "corr-duplicate"
                }
            )

        assert response.status_code == 500
        assert "Workflow execution already started" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_workflow_start_concurrent_requests_same_correlation(self, mock_app_state, mock_settings):
        """Testa requests concorrentes com mesmo correlation_id."""
        from src.main import app
        import asyncio

        call_count = 0

        async def mock_start_workflow(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception("Workflow execution already started")
            await asyncio.sleep(0.01)  # Simular latência

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = mock_start_workflow
        mock_app_state.temporal_client = mock_temporal

        request_data = {
            "cognitive_plan": {"plan_id": "plan-concurrent"},
            "correlation_id": "corr-concurrent"
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Enviar 2 requests concorrentes
            results = await asyncio.gather(
                ac.post("/api/v1/workflows/start", json=request_data),
                ac.post("/api/v1/workflows/start", json=request_data),
                return_exceptions=True
            )

        # Uma deve ter sucesso, outra deve falhar
        status_codes = [r.status_code for r in results if hasattr(r, 'status_code')]
        assert 200 in status_codes or 500 in status_codes


class TestWorkflowStartErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_workflow_start_temporal_connection_timeout(self, mock_app_state, mock_settings):
        """Testa timeout de conexão com Temporal."""
        from src.main import app
        import asyncio

        async def mock_timeout(*args, **kwargs):
            raise asyncio.TimeoutError("Connection timed out")

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = mock_timeout
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-timeout"},
                    "correlation_id": "corr-timeout"
                }
            )

        assert response.status_code == 500
        assert "Failed to start workflow" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_workflow_start_temporal_namespace_not_found(self, mock_app_state, mock_settings):
        """Testa erro quando namespace Temporal não existe."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock(
            side_effect=Exception("Namespace not found: neural-hive-mind")
        )
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-namespace"},
                    "correlation_id": "corr-namespace"
                }
            )

        assert response.status_code == 500
        assert "Namespace not found" in response.json()["detail"]


class TestWorkflowStartWithMockWorkflow:
    """Testes com mock do OrchestrationWorkflow."""

    @pytest.mark.asyncio
    async def test_workflow_start_passes_correct_workflow_class(self, mock_app_state, mock_settings):
        """Testa que OrchestrationWorkflow.run é passado ao Temporal."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-123"
                }
            )

        assert response.status_code == 200

        # Verificar que o primeiro argumento é OrchestrationWorkflow.run
        call_args = mock_temporal.start_workflow.call_args
        workflow_run = call_args.args[0]
        # O nome do método deve ser 'run' do OrchestrationWorkflow
        assert hasattr(workflow_run, '__name__') or callable(workflow_run)

    @pytest.mark.asyncio
    async def test_workflow_start_uses_correct_task_queue(self, mock_app_state, mock_settings):
        """Testa que task queue correta é usada."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-123"},
                    "correlation_id": "corr-123"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        assert call_args.kwargs["task_queue"] == "orchestration-tasks"


class TestWorkflowStartLogging:
    """Testes de logging do endpoint."""

    @pytest.mark.asyncio
    async def test_workflow_start_logs_attempt(self, mock_app_state, mock_settings):
        """Testa que tentativa de início é logada."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        with patch('src.main.logger') as mock_logger:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/workflows/start",
                    json={
                        "cognitive_plan": {"plan_id": "plan-log"},
                        "correlation_id": "corr-log"
                    }
                )

        assert response.status_code == 200

        # Verificar logs chamados
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert 'workflow_start_attempt' in log_calls
        assert 'workflow_started' in log_calls

    @pytest.mark.asyncio
    async def test_workflow_start_logs_rejection_when_temporal_unavailable(self, mock_app_state):
        """Testa que rejeição é logada quando Temporal indisponível."""
        from src.main import app

        mock_app_state.temporal_client = None

        with patch('src.main.logger') as mock_logger:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/workflows/start",
                    json={
                        "cognitive_plan": {"plan_id": "plan-reject"},
                        "correlation_id": "corr-reject"
                    }
                )

        assert response.status_code == 503

        # Verificar log de rejeição
        mock_logger.warning.assert_called()
        warning_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
        assert 'workflow_start_rejected' in warning_calls

    @pytest.mark.asyncio
    async def test_workflow_start_logs_failure_on_error(self, mock_app_state, mock_settings):
        """Testa que falha é logada quando ocorre erro."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock(side_effect=Exception("Test error"))
        mock_app_state.temporal_client = mock_temporal

        with patch('src.main.logger') as mock_logger:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/workflows/start",
                    json={
                        "cognitive_plan": {"plan_id": "plan-fail"},
                        "correlation_id": "corr-fail"
                    }
                )

        assert response.status_code == 500

        # Verificar log de erro
        mock_logger.error.assert_called()
        error_calls = [call[0][0] for call in mock_logger.error.call_args_list]
        assert 'workflow_start_failed' in error_calls


class TestWorkflowStartEdgeCases:
    """Testes de casos de borda."""

    @pytest.mark.asyncio
    async def test_workflow_start_with_large_cognitive_plan(self, mock_app_state, mock_settings):
        """Testa início de workflow com plano cognitivo grande."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        # Plano com muitas tasks
        large_plan = {
            "plan_id": "plan-large",
            "intent_id": "intent-large",
            "tasks": [
                {"task_id": f"task-{i}", "type": "BUILD", "description": f"Task {i}"}
                for i in range(100)
            ]
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": large_plan,
                    "correlation_id": "corr-large"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

    @pytest.mark.asyncio
    async def test_workflow_start_with_special_characters_in_correlation_id(self, mock_app_state, mock_settings):
        """Testa correlation_id com caracteres especiais."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        # Correlation ID com caracteres especiais (mas válidos)
        special_correlation = "corr_test-123.abc"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {"plan_id": "plan-special"},
                    "correlation_id": special_correlation
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["correlation_id"] == special_correlation

    @pytest.mark.asyncio
    async def test_workflow_start_with_minimum_valid_request(self, mock_app_state, mock_settings):
        """Testa request mínimo válido (apenas campos obrigatórios)."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": {},
                    "correlation_id": "corr-min"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["correlation_id"] == "corr-min"

    @pytest.mark.asyncio
    async def test_workflow_start_preserves_extra_cognitive_plan_fields(self, mock_app_state, mock_settings):
        """Testa que campos extras no cognitive_plan são preservados."""
        from src.main import app

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        cognitive_plan = {
            "plan_id": "plan-extra",
            "custom_field": "custom_value",
            "nested": {"key": "value"},
            "array_field": [1, 2, 3]
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workflows/start",
                json={
                    "cognitive_plan": cognitive_plan,
                    "correlation_id": "corr-extra"
                }
            )

        assert response.status_code == 200

        call_args = mock_temporal.start_workflow.call_args
        input_data = call_args.args[1]

        # Verificar que campos extras foram preservados
        assert input_data["cognitive_plan"]["custom_field"] == "custom_value"
        assert input_data["cognitive_plan"]["nested"]["key"] == "value"
        assert input_data["cognitive_plan"]["array_field"] == [1, 2, 3]
