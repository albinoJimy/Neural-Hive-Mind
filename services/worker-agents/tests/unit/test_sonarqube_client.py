"""
Testes unitarios para SonarQubeClient.

Cobertura:
- Trigger de analise
- Obtencao de resultados
- Configuracao via env
- Error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSonarQubeClientInitialization:
    """Testes de inicializacao."""

    def test_init_direct(self):
        """Deve inicializar com parametros diretos."""
        from src.clients.sonarqube_client import SonarQubeClient

        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token',
            timeout=600
        )

        assert client.base_url == 'http://sonar.local'
        assert client.token == 'test-token'

    def test_from_env_success(self):
        """Deve criar cliente via environment."""
        from src.clients.sonarqube_client import SonarQubeClient

        with patch.dict('os.environ', {
            'SONARQUBE_URL': 'http://sonar.local',
            'SONARQUBE_TOKEN': 'test-token'
        }):
            client = SonarQubeClient.from_env()

            assert client.base_url == 'http://sonar.local'
            assert client.token == 'test-token'

    def test_from_env_with_config(self):
        """Deve usar config quando fornecido."""
        from src.clients.sonarqube_client import SonarQubeClient

        mock_config = MagicMock()
        mock_config.sonarqube_url = 'http://sonar-config.local'
        mock_config.sonarqube_token = 'config-token'
        mock_config.sonarqube_timeout_seconds = 900

        with patch.dict('os.environ', {}, clear=True):
            client = SonarQubeClient.from_env(config=mock_config)

            assert client.base_url == 'http://sonar-config.local'
            assert client.token == 'config-token'

    def test_from_env_missing_config(self):
        """Deve levantar erro quando config ausente."""
        from src.clients.sonarqube_client import SonarQubeClient

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match='not found'):
                SonarQubeClient.from_env()


class TestSonarQubeClientAnalysis:
    """Testes de analise."""

    @pytest.mark.asyncio
    async def test_trigger_analysis_success(self):
        """Deve disparar analise com sucesso."""
        from src.clients.sonarqube_client import SonarQubeClient

        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token'
        )

        analysis = await client.trigger_analysis(
            project_key='test-project',
            sources_path='/tmp/src'
        )

        assert analysis.task_id is not None
        assert analysis.passed is True
        assert isinstance(analysis.issues, list)
        assert analysis.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_trigger_analysis_missing_project_key(self):
        """Deve levantar erro quando project_key ausente."""
        from src.clients.sonarqube_client import SonarQubeClient

        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token'
        )

        with pytest.raises(ValueError, match='project_key required'):
            await client.trigger_analysis(
                project_key='',
                sources_path='/tmp/src'
            )


class TestSonarQubeAnalysis:
    """Testes do modelo SonarQubeAnalysis."""

    def test_sonarqube_analysis_creation(self):
        """Deve criar analysis corretamente."""
        from src.clients.sonarqube_client import SonarQubeAnalysis

        issues = [
            {'key': 'issue-1', 'severity': 'MAJOR', 'message': 'Code smell'},
            {'key': 'issue-2', 'severity': 'CRITICAL', 'message': 'Security issue'}
        ]

        analysis = SonarQubeAnalysis(
            task_id='task-123',
            passed=False,
            issues=issues,
            duration_seconds=120.5,
            logs=['Analysis started', 'Analysis completed']
        )

        assert analysis.task_id == 'task-123'
        assert analysis.passed is False
        assert len(analysis.issues) == 2
        assert analysis.duration_seconds == 120.5

    def test_sonarqube_analysis_no_issues(self):
        """Deve criar analysis sem issues."""
        from src.clients.sonarqube_client import SonarQubeAnalysis

        analysis = SonarQubeAnalysis(
            task_id='task-456',
            passed=True,
            issues=[],
            duration_seconds=60.0,
            logs=None
        )

        assert analysis.passed is True
        assert len(analysis.issues) == 0
        assert analysis.logs is None
