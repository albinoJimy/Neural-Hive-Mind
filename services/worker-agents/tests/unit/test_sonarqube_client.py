"""
Testes unitários para SonarQubeClient.

Cobertura:
- Inicialização e configuracao
- Trigger de analise via API REST
- Polling de status de analise
- Fetch de issues e quality gates
- Error handling
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from src.clients.sonarqube_client import (
    SonarQubeClient,
    SonarQubeAnalysis,
    SonarQubeIssue,
    SonarQubeQualityGate,
    SonarQubeStatus,
    SonarQubeSeverity,
    SonarQubeClientError,
    SonarQubeAPIError,
    SonarQubeTimeoutError,
)


class TestSonarQubeClientInitialization:
    """Testes de inicializacao."""

    def test_init_direct(self):
        """Deve inicializar com parametros diretos."""
        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token',
            timeout=600,
            poll_interval=10,
        )

        assert client.base_url == 'http://sonar.local'
        assert client.token == 'test-token'
        assert client.timeout == 600
        assert client.poll_interval == 10

    def test_from_env_success(self):
        """Deve criar cliente via environment."""
        with patch.dict('os.environ', {
            'SONARQUBE_URL': 'http://sonar.local',
            'SONARQUBE_TOKEN': 'test-token'
        }):
            client = SonarQubeClient.from_env()

        assert client.base_url == 'http://sonar.local'
        assert client.token == 'test-token'

    def test_from_env_with_config(self):
        """Deve usar config quando fornecido."""
        mock_config = MagicMock()
        mock_config.sonarqube_url = 'http://sonar-config.local'
        mock_config.sonarqube_token = 'config-token'
        mock_config.sonarqube_timeout_seconds = 900

        with patch.dict('os.environ', {}, clear=True):
            client = SonarQubeClient.from_env(config=mock_config)

        assert client.base_url == 'http://sonar-config.local'
        assert client.token == 'config-token'
        assert client.timeout == 900

    def test_from_env_missing_config(self):
        """Deve levantar erro quando config ausente."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match='SONARQUBE_TOKEN not configured'):
                SonarQubeClient.from_env()

    async def test_close(self):
        """Deve fechar HTTP client."""
        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token'
        )
        await client.close()


class TestSonarQubeClientAnalysis:
    """Testes de analise via API."""

    @pytest.mark.asyncio
    async def test_trigger_analysis_success(self):
        """Deve disparar analise com sucesso."""
        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token'
        )

        # Mock HTTP responses
        mock_search_response = MagicMock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = {
            'components': [
                {'key': 'test-project', 'name': 'Test Project'}
            ]
        }

        mock_analyses_response = MagicMock()
        mock_analyses_response.status_code = 200
        mock_analyses_response.json.return_value = {
            'analyses': [
                {
                    'id': 'analysis-123',
                    'status': 'SUCCESS',
                    'taskId': 'task-456',
                }
            ]
        }

        mock_an_response = MagicMock()
        mock_an_response.status_code = 200
        mock_an_response.json.return_value = {}

        with patch.object(client._client, 'get', side_effect=[
            mock_search_response,
            mock_analyses_response,
            mock_an_response,
        ]):
            analysis = await client.trigger_analysis(
                project_key='test-project',
                sources_path='/tmp/src'
            )

        assert analysis.project_key == 'test-project'
        assert analysis.status == SonarQubeStatus.SUCCESS
        assert analysis.passed is True

    @pytest.mark.asyncio
    async def test_trigger_analysis_missing_project_key(self):
        """Deve levantar erro quando project_key ausente."""
        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token'
        )

        with pytest.raises(ValueError, match='project_key required'):
            await client.trigger_analysis(
                project_key='',
                sources_path='/tmp/src'
            )

    @pytest.mark.asyncio
    async def test_trigger_analysis_project_not_found(self):
        """Deve retornar erro quando projecto nao existe."""
        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token'
        )

        # Mock empty project search
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'components': []}

        with patch.object(client._client, 'get', return_value=mock_response):
            analysis = await client.trigger_analysis(
                project_key='nonexistent',
                sources_path='/tmp/src'
            )

        assert analysis.passed is False
        assert 'Project not found' in analysis.error

    @pytest.mark.asyncio
    async def test_poll_task_timeout(self):
        """Deve timeout quando polling demora demais."""
        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token',
            poll_interval=1,
        )

        # Mock task that stays pending
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'PENDING'}

        with patch.object(client._client, 'get', return_value=mock_response):
            with pytest.raises(SonarQubeTimeoutError):
                await client._poll_ce_task('task-123', max_wait=2)

    @pytest.mark.asyncio
    async def test_get_organization_health(self):
        """Deve obter metricas de saude."""
        client = SonarQubeClient(
            base_url='http://sonar.local',
            token='test-token'
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'indices': [
                {'key': 'quality_gate', 'name': 'Quality Gate'}
            ]
        }

        with patch.object(client._client, 'get', return_value=mock_response):
            health = await client.get_organization_health()

        assert 'indices' in health


class TestSonarQubeIssue:
    """Testes do modelo SonarQubeIssue."""

    def test_issue_creation(self):
        """Deve criar issue com todos os campos."""
        issue = SonarQubeIssue(
            key='issue-1',
            rule='python:S1134',
            severity=SonarQubeSeverity.MAJOR,
            component='src/main.py',
            line=42,
            message='Unused variable',
            debt=15,
            effort='5min',
        )

        assert issue.key == 'issue-1'
        assert issue.severity == SonarQubeSeverity.MAJOR
        assert issue.line == 42
        assert issue.debt == 15

    def test_issue_minimal(self):
        """Deve criar issue com campos minimos."""
        issue = SonarQubeIssue(
            key='issue-2',
            rule='javascript:S123',
            severity=SonarQubeSeverity.MINOR,
            component='app.js',
            line=None,
            message='Minor issue',
            debt=None,
            effort=None,
        )

        assert issue.key == 'issue-2'
        assert issue.line is None


class TestSonarQubeQualityGate:
    """Testes do modelo SonarQubeQualityGate."""

    def test_quality_gate_creation(self):
        """Deve criar quality gate com condicoes."""
        qg = SonarQubeQualityGate(
            id='qg-1',
            name='My Quality Gate',
            status='OK',
            conditions=[
                {'metric': 'coverage', 'status': 'OK', 'actual': 85.0},
                {'metric': 'vulnerabilities', 'status': 'ERROR', 'actual': 5},
            ],
        )

        assert qg.id == 'qg-1'
        assert qg.status == 'OK'
        assert len(qg.conditions) == 2

    def test_quality_gate_no_conditions(self):
        """Deve criar quality gate sem condicoes."""
        qg = SonarQubeQualityGate(
            id='qg-2',
            name='Empty Gate',
            status='NONE',
        )

        assert qg.status == 'NONE'
        assert len(qg.conditions) == 0


class TestSonarQubeAnalysis:
    """Testes do modelo SonarQubeAnalysis."""

    def test_sonarqube_analysis_creation(self):
        """Deve criar analysis corretamente."""
        issues = [
            SonarQubeIssue(
                key='issue-1',
                rule='python:S1134',
                severity=SonarQubeSeverity.MAJOR,
                component='src/main.py',
                line=42,
                message='Unused variable',
            ),
            SonarQubeIssue(
                key='issue-2',
                rule='javascript:S123',
                severity=SonarQubeSeverity.CRITICAL,
                component='app.js',
                line=10,
                message='Security issue',
            ),
        ]

        qg = SonarQubeQualityGate(
            id='qg-1',
            name='My Gate',
            status='ERROR',
        )

        analysis = SonarQubeAnalysis(
            task_id='task-123',
            project_key='test-project',
            status=SonarQubeStatus.SUCCESS,
            passed=False,
            issues=issues,
            quality_gate=qg,
            metrics={'coverage': 85.0, 'vulnerabilities': 5},
            duration_seconds=120.5,
            logs=['Analysis started', 'Analysis completed'],
        )

        assert analysis.task_id == 'task-123'
        assert analysis.passed is False
        assert len(analysis.issues) == 2
        assert analysis.quality_gate.status == 'ERROR'
        assert analysis.metrics['coverage'] == 85.0

    def test_sonarqube_analysis_no_issues(self):
        """Deve criar analysis sem issues."""
        analysis = SonarQubeAnalysis(
            task_id='task-456',
            project_key='test-project',
            status=SonarQubeStatus.SUCCESS,
            passed=True,
            issues=[],
            quality_gate=None,
            duration_seconds=60.0,
        )

        assert analysis.passed is True
        assert len(analysis.issues) == 0

    def test_sonarqube_analysis_with_error(self):
        """Deve incluir informacao de erro."""
        analysis = SonarQubeAnalysis(
            task_id='task-789',
            project_key='test-project',
            status=SonarQubeStatus.FAILED,
            passed=False,
            issues=[],
            duration_seconds=0,
            logs=['Scan failed'],
            error='Timeout exceeded',
        )

        assert analysis.status == SonarQubeStatus.FAILED
        assert analysis.error == 'Timeout exceeded'
