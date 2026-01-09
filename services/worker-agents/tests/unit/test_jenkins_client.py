"""
Testes unitarios para JenkinsClient.

Cobertura:
- Trigger de job
- Polling de status de build
- Obtencao de test report
- Obtencao de coverage
- Queue management
- Timeout handling
- Error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestJenkinsClientTrigger:
    """Testes de trigger de job."""

    @pytest.mark.asyncio
    async def test_trigger_job_success(self):
        """Deve disparar job com sucesso."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token',
            user='admin'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {'Location': 'http://jenkins.local/queue/item/123/'}
            mock_http.post = AsyncMock(return_value=mock_response)

            queue_id = await client.trigger_job('my-job')

            assert queue_id == 123
            mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_job_with_parameters(self):
        """Deve disparar job com parametros."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token',
            user='admin'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {'X-Queue-Id': '456'}
            mock_http.post = AsyncMock(return_value=mock_response)

            queue_id = await client.trigger_job(
                job_name='my-job',
                parameters={'BRANCH': 'develop', 'ENV': 'staging'}
            )

            assert queue_id == 456

    @pytest.mark.asyncio
    async def test_trigger_job_api_error(self):
        """Deve propagar erro da API."""
        from src.clients.jenkins_client import JenkinsClient, JenkinsAPIError
        import httpx

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token',
            user='admin'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = 'Internal Server Error'
            mock_response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    'Error', request=MagicMock(), response=mock_response
                )
            )
            mock_http.post = AsyncMock(return_value=mock_response)

            with pytest.raises(JenkinsAPIError) as exc_info:
                await client.trigger_job('my-job')

            assert exc_info.value.status_code == 500


class TestJenkinsClientQueue:
    """Testes de queue management."""

    @pytest.mark.asyncio
    async def test_get_queue_item_pending(self):
        """Deve obter item na fila."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'blocked': True,
                'buildable': False,
                'why': 'Waiting for available executor',
                'executable': None
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            item = await client.get_queue_item(123)

            assert item.queue_id == 123
            assert item.blocked is True
            assert item.build_number is None

    @pytest.mark.asyncio
    async def test_get_queue_item_started(self):
        """Deve obter item quando build iniciou."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'blocked': False,
                'buildable': True,
                'why': None,
                'executable': {'number': 42, 'url': 'http://jenkins/job/my-job/42/'}
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            item = await client.get_queue_item(123)

            assert item.build_number == 42

    @pytest.mark.asyncio
    async def test_wait_for_build_number_success(self):
        """Deve aguardar e retornar build number."""
        from src.clients.jenkins_client import JenkinsClient, JenkinsQueueItem

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'get_queue_item') as mock_get:
            mock_get.return_value = JenkinsQueueItem(
                queue_id=123,
                blocked=False,
                buildable=True,
                build_number=42
            )

            build_number = await client.wait_for_build_number(
                job_name='my-job',
                queue_id=123,
                poll_interval=0.1,
                timeout=5
            )

            assert build_number == 42


class TestJenkinsClientBuildStatus:
    """Testes de obtencao de status de build."""

    @pytest.mark.asyncio
    async def test_get_build_status_success(self):
        """Deve obter status de build SUCCESS."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'number': 42,
                'result': 'SUCCESS',
                'building': False,
                'duration': 120000,
                'url': 'http://jenkins/job/my-job/42/'
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            status = await client.get_build_status('my-job', 42)

            assert status.build_number == 42
            assert status.status == 'SUCCESS'
            assert status.success is True
            assert status.completed is True
            assert status.duration_seconds == 120.0

    @pytest.mark.asyncio
    async def test_get_build_status_building(self):
        """Deve obter status de build em execucao."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'number': 42,
                'result': None,
                'building': True,
                'duration': 0
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            status = await client.get_build_status('my-job', 42)

            assert status.status == 'BUILDING'
            assert status.completed is False

    @pytest.mark.asyncio
    async def test_get_build_status_failure(self):
        """Deve obter status de build FAILURE."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'number': 42,
                'result': 'FAILURE',
                'building': False,
                'duration': 60000
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            status = await client.get_build_status('my-job', 42)

            assert status.status == 'FAILURE'
            assert status.success is False


class TestJenkinsClientWait:
    """Testes de wait for build."""

    @pytest.mark.asyncio
    async def test_wait_for_build_success(self):
        """Deve aguardar build completar."""
        from src.clients.jenkins_client import JenkinsClient, JenkinsBuildStatus

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'get_build_status') as mock_get:
            mock_get.return_value = JenkinsBuildStatus(
                build_number=42,
                status='SUCCESS',
                result='SUCCESS',
                building=False,
                duration_seconds=120.0
            )

            with patch.object(client, 'get_test_report', return_value={
                'passCount': 50, 'failCount': 0, 'skipCount': 2
            }):
                with patch.object(client, 'get_coverage_report', return_value=85.5):
                    status = await client.wait_for_build(
                        job_name='my-job',
                        build_number=42,
                        poll_interval=0.1,
                        timeout=5
                    )

                    assert status.success is True
                    assert status.tests_passed == 50
                    assert status.coverage == 85.5

    @pytest.mark.asyncio
    async def test_wait_for_build_timeout(self):
        """Deve levantar timeout."""
        from src.clients.jenkins_client import (
            JenkinsClient, JenkinsBuildStatus, JenkinsTimeoutError
        )

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'get_build_status') as mock_get:
            mock_get.return_value = JenkinsBuildStatus(
                build_number=42,
                status='BUILDING',
                building=True
            )

            with pytest.raises(JenkinsTimeoutError):
                await client.wait_for_build(
                    job_name='my-job',
                    build_number=42,
                    poll_interval=0.1,
                    timeout=0.3
                )


class TestJenkinsClientReports:
    """Testes de obtencao de reports."""

    @pytest.mark.asyncio
    async def test_get_test_report_success(self):
        """Deve obter test report."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'passCount': 100,
                'failCount': 5,
                'skipCount': 3,
                'totalCount': 108,
                'duration': 45.5
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            report = await client.get_test_report('my-job', 42)

            assert report['passCount'] == 100
            assert report['failCount'] == 5

    @pytest.mark.asyncio
    async def test_get_test_report_not_found(self):
        """Deve retornar report vazio quando nao encontrado."""
        from src.clients.jenkins_client import JenkinsClient
        import httpx

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    'Not Found', request=MagicMock(), response=mock_response
                )
            )
            mock_http.get = AsyncMock(return_value=mock_response)

            report = await client.get_test_report('my-job', 42)

            assert report['passCount'] == 0
            assert report['totalCount'] == 0

    @pytest.mark.asyncio
    async def test_get_coverage_report_jacoco(self):
        """Deve obter coverage do Jacoco."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={
                'lineCoverage': {'percentageFloat': 82.5}
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            coverage = await client.get_coverage_report('my-job', 42)

            assert coverage == 82.5

    @pytest.mark.asyncio
    async def test_get_console_output(self):
        """Deve obter console output."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.text = 'Started by user admin\nBuilding...\nFinished: SUCCESS'
            mock_http.get = AsyncMock(return_value=mock_response)

            output = await client.get_console_output('my-job', 42)

            assert 'Finished: SUCCESS' in output


class TestJenkinsClientOperations:
    """Testes de operacoes diversas."""

    @pytest.mark.asyncio
    async def test_stop_build(self):
        """Deve parar build em execucao."""
        from src.clients.jenkins_client import JenkinsClient

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_http.post = AsyncMock(return_value=mock_response)

            result = await client.stop_build('my-job', 42)

            assert result is True

    @pytest.mark.asyncio
    async def test_get_last_build(self):
        """Deve obter ultimo build."""
        from src.clients.jenkins_client import JenkinsClient, JenkinsBuildStatus

        client = JenkinsClient(
            base_url='http://jenkins.local',
            token='test-token'
        )

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={'number': 42})
            mock_http.get = AsyncMock(return_value=mock_response)

            with patch.object(client, 'get_build_status') as mock_get:
                mock_get.return_value = JenkinsBuildStatus(
                    build_number=42,
                    status='SUCCESS'
                )

                status = await client.get_last_build('my-job')

                assert status.build_number == 42


class TestJenkinsClientFromEnv:
    """Testes de criacao via environment."""

    def test_from_env_success(self):
        """Deve criar cliente via environment."""
        from src.clients.jenkins_client import JenkinsClient

        with patch.dict('os.environ', {
            'JENKINS_URL': 'http://jenkins.local',
            'JENKINS_TOKEN': 'test-token',
            'JENKINS_USER': 'admin'
        }):
            client = JenkinsClient.from_env()

            assert client.base_url == 'http://jenkins.local'
            assert client.token == 'test-token'
            assert client.user == 'admin'

    def test_from_env_missing_credentials(self):
        """Deve levantar erro quando credenciais ausentes."""
        from src.clients.jenkins_client import JenkinsClient

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match='not configured'):
                JenkinsClient.from_env()
