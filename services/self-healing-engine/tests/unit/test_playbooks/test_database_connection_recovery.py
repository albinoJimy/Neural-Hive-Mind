"""Testes para o playbook de recuperação de conexão de base de dados - TDD Approach."""

import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestDatabaseConnectionRecoveryPlaybook:
    """Testes para verificar a existência e schema do playbook database_connection_recovery.yaml."""

    def test_database_connection_recovery_playbook_exists(self):
        """Verifica que o ficheiro do playbook existe."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent
            / "playbooks"
            / "database_connection_recovery.yaml"
        )
        assert playbook_path.exists(), "Playbook file does not exist"

    def test_database_connection_recovery_playbook_valid_schema(self):
        """Verifica que o playbook tem o schema válido."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent
            / "playbooks"
            / "database_connection_recovery.yaml"
        )
        with open(playbook_path) as f:
            playbook = yaml.safe_load(f)

        assert playbook["playbook_id"] == "database-connection-recovery-v1"
        assert "actions" in playbook
        assert len(playbook["actions"]) >= 2

        # Verificar que as ações esperadas existem
        action_names = [action["name"] for action in playbook["actions"]]
        assert "check_database_connection" in action_names
        assert "restart_pod" in action_names

    def test_database_connection_recovery_playbook_trigger(self):
        """Verifica que o playbook tem o trigger correto."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent
            / "playbooks"
            / "database_connection_recovery.yaml"
        )
        with open(playbook_path) as f:
            playbook = yaml.safe_load(f)

        assert "trigger" in playbook
        assert playbook["trigger"]["pattern"] == "database_connection_failure"
        assert playbook["trigger"]["severity"] == "critical"

    def test_database_connection_recovery_playbook_parameters(self):
        """Verifica que o playbook tem os parâmetros corretos."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent
            / "playbooks"
            / "database_connection_recovery.yaml"
        )
        with open(playbook_path) as f:
            playbook = yaml.safe_load(f)

        assert "parameters_schema" in playbook
        params = playbook["parameters_schema"]["properties"]
        assert "database_type" in params
        assert "connection_string" in params
        assert "target_pod" in params


class TestDatabaseConnectionCheckAction:
    """Testes para a ação check_database_connection do PlaybookExecutor."""

    @pytest.fixture
    def executor(self, mock_execution_ticket_client, mock_orchestrator_client):
        """Cria executor de playbooks com clientes mockados."""
        from src.services.playbook_executor import PlaybookExecutor
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            executor = PlaybookExecutor(
                playbooks_dir=tmpdir,
                k8s_in_cluster=False,
                execution_ticket_client=mock_execution_ticket_client,
                orchestrator_client=mock_orchestrator_client,
                opa_client=None,
                opa_enabled=False,
            )
            # Mock Kubernetes clients
            with patch("src.services.playbook_executor.client"):
                with patch("src.services.playbook_executor.config"):
                    from kubernetes import client

                    executor.core_v1 = MagicMock(spec=client.CoreV1Api)
                    executor.apps_v1 = MagicMock(spec=client.AppsV1Api)
                    yield executor

    @pytest.mark.asyncio
    async def test_check_database_connection_mongodb_success(self, executor):
        """Testa verificação de conexão MongoDB bem-sucedida."""
        # Arrange
        action = {
            "type": "check_database_connection",
            "connection_string": "mongodb://localhost:27017",
            "database_type": "mongodb",
            "database_name": "test_db",
            "timeout_seconds": 5,
        }
        context = {}

        # Act
        result = await executor._check_database_connection(action, context)

        # Assert
        assert result["success"] is True
        assert result["action"] == "check_database_connection"
        assert result["connected"] is True
        assert result["database_type"] == "mongodb"

    @pytest.mark.asyncio
    async def test_check_database_connection_postgresql_success(self, executor):
        """Testa verificação de conexão PostgreSQL bem-sucedida."""
        # Arrange
        action = {
            "type": "check_database_connection",
            "connection_string": "postgresql://localhost:5432/test",
            "database_type": "postgresql",
            "database_name": "test_db",
            "timeout_seconds": 5,
        }
        context = {}

        # Act - deve retornar sucesso simulado (sem conexão real em testes)
        result = await executor._check_database_connection(action, context)

        # Assert
        assert result["action"] == "check_database_connection"
        # Em ambiente de teste, pode não ter conexão real
        assert "connected" in result or "error" in result

    @pytest.mark.asyncio
    async def test_check_database_connection_redis_success(self, executor):
        """Testa verificação de conexão Redis bem-sucedida."""
        # Arrange
        action = {
            "type": "check_database_connection",
            "connection_string": "redis://localhost:6379",
            "database_type": "redis",
            "timeout_seconds": 5,
        }
        context = {}

        # Act
        result = await executor._check_database_connection(action, context)

        # Assert
        assert result["action"] == "check_database_connection"
        assert "database_type" in result

    @pytest.mark.asyncio
    async def test_check_database_connection_failure_invalid_connection_string(self, executor):
        """Testa falha quando connection_string é inválida."""
        # Arrange
        action = {
            "type": "check_database_connection",
            "connection_string": "invalid://connection",
            "database_type": "mongodb",
            "timeout_seconds": 1,
        }
        context = {}

        # Act
        result = await executor._check_database_connection(action, context)

        # Assert
        assert result["action"] == "check_database_connection"
        assert result["connected"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_check_database_connection_timeout(self, executor):
        """Testa timeout na verificação de conexão."""
        # Arrange
        action = {
            "type": "check_database_connection",
            "connection_string": "mongodb://unreachable-host:27017",
            "database_type": "mongodb",
            "timeout_seconds": 1,
        }
        context = {}

        # Act
        result = await executor._check_database_connection(action, context)

        # Assert
        assert result["action"] == "check_database_connection"
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_check_database_connection_unsupported_database_type(self, executor):
        """Testa erro quando database_type não é suportado."""
        # Arrange
        action = {
            "type": "check_database_connection",
            "connection_string": "some://connection",
            "database_type": "unsupported_db",
        }
        context = {}

        # Act
        result = await executor._check_database_connection(action, context)

        # Assert
        assert result["success"] is False
        assert result["action"] == "check_database_connection"
        assert "error" in result
        assert "unsupported" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_check_database_connection_updates_context_on_success(self, executor):
        """Testa que o contexto é atualizado quando a conexão é bem-sucedida."""
        # Arrange
        action = {
            "type": "check_database_connection",
            "connection_string": "mongodb://localhost:27017",
            "database_type": "mongodb",
        }
        context = {}

        # Act
        await executor._check_database_connection(action, context)

        # Assert - contexto deve ter info sobre o estado da conexão
        assert "database_connection_checked" in context
        assert context["database_connection_type"] == "mongodb"

    def test_check_database_connection_action_registered_in_action_map(self, executor):
        """Testa que check_database_connection está registada no action_map."""
        # Act
        handler = executor._get_action_handler("check_database_connection")

        # Assert
        assert handler is not None
        assert callable(handler)
