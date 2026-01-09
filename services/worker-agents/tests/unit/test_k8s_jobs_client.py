"""
Testes unitarios para KubernetesJobsClient.

Cobertura:
- Criacao de Job
- Execucao de Job
- Polling de status
- Obtencao de logs
- Cleanup de Jobs
- Timeout handling
- Error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestK8sJobsClientInitialization:
    """Testes de inicializacao."""

    @pytest.mark.asyncio
    async def test_initialize_from_kubeconfig(self):
        """Deve inicializar com kubeconfig."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(
            kubeconfig_path='/path/to/kubeconfig',
            namespace='test-ns'
        )

        with patch('src.clients.k8s_jobs_client.config') as mock_config:
            mock_config.load_kube_config = AsyncMock()

            with patch('src.clients.k8s_jobs_client.client') as mock_client:
                mock_client.BatchV1Api = MagicMock()
                mock_client.CoreV1Api = MagicMock()

                await client.initialize()

                assert client._initialized is True
                mock_config.load_kube_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_incluster(self):
        """Deve inicializar in-cluster."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')

        with patch('src.clients.k8s_jobs_client.config') as mock_config:
            mock_config.load_incluster_config = MagicMock()

            with patch('src.clients.k8s_jobs_client.client') as mock_client:
                mock_client.BatchV1Api = MagicMock()
                mock_client.CoreV1Api = MagicMock()

                await client.initialize()

                assert client._initialized is True
                mock_config.load_incluster_config.assert_called_once()


class TestK8sJobsClientJobManifest:
    """Testes de construcao de manifest."""

    def test_build_job_manifest_basic(self):
        """Deve construir manifest basico."""
        from src.clients.k8s_jobs_client import (
            KubernetesJobsClient, K8sJobRequest
        )

        client = KubernetesJobsClient(namespace='test-ns')

        request = K8sJobRequest(
            name='test-job',
            namespace='test-ns',
            image='python:3.11',
            command=['python', '-c', 'print("hello")']
        )

        manifest = client._build_job_manifest(request)

        assert manifest['apiVersion'] == 'batch/v1'
        assert manifest['kind'] == 'Job'
        assert manifest['metadata']['name'] == 'test-job'
        assert manifest['metadata']['namespace'] == 'test-ns'
        assert manifest['spec']['template']['spec']['containers'][0]['image'] == 'python:3.11'

    def test_build_job_manifest_with_resources(self):
        """Deve construir manifest com resource limits."""
        from src.clients.k8s_jobs_client import (
            KubernetesJobsClient, K8sJobRequest, K8sResourceRequirements
        )

        client = KubernetesJobsClient(namespace='test-ns')

        request = K8sJobRequest(
            name='test-job',
            namespace='test-ns',
            image='python:3.11',
            command=['python', 'script.py'],
            resource_limits=K8sResourceRequirements(
                cpu_request='500m',
                cpu_limit='2000m',
                memory_request='256Mi',
                memory_limit='1Gi'
            )
        )

        manifest = client._build_job_manifest(request)
        container = manifest['spec']['template']['spec']['containers'][0]

        assert container['resources']['requests']['cpu'] == '500m'
        assert container['resources']['limits']['memory'] == '1Gi'

    def test_build_job_manifest_with_env_vars(self):
        """Deve construir manifest com env vars."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient, K8sJobRequest

        client = KubernetesJobsClient(namespace='test-ns')

        request = K8sJobRequest(
            name='test-job',
            namespace='test-ns',
            image='python:3.11',
            command=['python', 'script.py'],
            env_vars={'DEBUG': 'true', 'LOG_LEVEL': 'info'}
        )

        manifest = client._build_job_manifest(request)
        container = manifest['spec']['template']['spec']['containers'][0]

        env_names = [e['name'] for e in container['env']]
        assert 'DEBUG' in env_names
        assert 'LOG_LEVEL' in env_names

    def test_generate_job_name(self):
        """Deve gerar nome unico para Job."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')

        name1 = client._generate_job_name('exec')
        name2 = client._generate_job_name('exec')

        assert name1.startswith('exec-')
        assert name2.startswith('exec-')
        assert name1 != name2


class TestK8sJobsClientExecution:
    """Testes de execucao de Job."""

    @pytest.mark.asyncio
    async def test_execute_job_success(self):
        """Deve executar Job com sucesso."""
        from src.clients.k8s_jobs_client import (
            KubernetesJobsClient, K8sJobRequest, K8sJobStatus
        )

        client = KubernetesJobsClient(namespace='test-ns')
        client._initialized = True
        client._batch_api = AsyncMock()
        client._core_api = AsyncMock()

        # Mock create job
        with patch.object(client, '_create_job', return_value='test-job'):
            # Mock wait for job
            with patch.object(client, '_wait_for_job', return_value=K8sJobStatus.SUCCEEDED):
                # Mock get pod and logs
                with patch.object(client, '_get_pod_for_job', return_value='test-pod'):
                    with patch.object(client, '_get_pod_logs', return_value='Output line 1\nOutput line 2'):
                        with patch.object(client, '_get_pod_exit_code', return_value=0):
                            with patch.object(client, '_get_job_status', return_value={
                                'succeeded': 1, 'failed': 0, 'start_time': None, 'completion_time': None
                            }):
                                with patch.object(client, '_delete_job', return_value=None):
                                    request = K8sJobRequest(
                                        name='test-job',
                                        namespace='test-ns',
                                        image='python:3.11',
                                        command=['python', '-c', 'print("hello")']
                                    )

                                    result = await client.execute_job(request)

                                    assert result.job_name == 'test-job'
                                    assert result.status == K8sJobStatus.SUCCEEDED
                                    assert result.exit_code == 0
                                    assert 'Output line' in result.logs

    @pytest.mark.asyncio
    async def test_execute_job_failure(self):
        """Deve retornar falha quando Job falha."""
        from src.clients.k8s_jobs_client import (
            KubernetesJobsClient, K8sJobRequest, K8sJobStatus
        )

        client = KubernetesJobsClient(namespace='test-ns')
        client._initialized = True

        with patch.object(client, '_create_job', return_value='test-job'):
            with patch.object(client, '_wait_for_job', return_value=K8sJobStatus.FAILED):
                with patch.object(client, '_get_pod_for_job', return_value='test-pod'):
                    with patch.object(client, '_get_pod_logs', return_value='Error: command failed'):
                        with patch.object(client, '_get_pod_exit_code', return_value=1):
                            with patch.object(client, '_get_job_status', return_value={'failed': 1}):
                                with patch.object(client, '_delete_job', return_value=None):
                                    request = K8sJobRequest(
                                        name='test-job',
                                        namespace='test-ns',
                                        image='python:3.11',
                                        command=['python', 'bad_script.py']
                                    )

                                    result = await client.execute_job(request)

                                    assert result.status == K8sJobStatus.FAILED
                                    assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_execute_job_timeout(self):
        """Deve levantar timeout."""
        from src.clients.k8s_jobs_client import (
            KubernetesJobsClient, K8sJobRequest, K8sJobTimeoutError
        )

        client = KubernetesJobsClient(namespace='test-ns')
        client._initialized = True

        with patch.object(client, '_create_job', return_value='test-job'):
            with patch.object(client, '_wait_for_job', side_effect=K8sJobTimeoutError('Timeout')):
                with patch.object(client, '_delete_job', return_value=None):
                    request = K8sJobRequest(
                        name='test-job',
                        namespace='test-ns',
                        image='python:3.11',
                        command=['python', 'long_script.py'],
                        timeout_seconds=1
                    )

                    with pytest.raises(K8sJobTimeoutError):
                        await client.execute_job(request)


class TestK8sJobsClientStatus:
    """Testes de obtencao de status."""

    @pytest.mark.asyncio
    async def test_get_job_status_succeeded(self):
        """Deve obter status succeeded."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')
        client._batch_api = AsyncMock()

        mock_job = MagicMock()
        mock_job.status.active = 0
        mock_job.status.succeeded = 1
        mock_job.status.failed = 0
        mock_job.status.start_time = None
        mock_job.status.completion_time = None
        mock_job.status.conditions = []

        client._batch_api.read_namespaced_job_status = AsyncMock(return_value=mock_job)

        status = await client._get_job_status('test-job', 'test-ns')

        assert status['succeeded'] == 1
        assert status['failed'] == 0

    @pytest.mark.asyncio
    async def test_wait_for_job_completes(self):
        """Deve aguardar Job completar."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient, K8sJobStatus

        client = KubernetesJobsClient(namespace='test-ns', poll_interval=0.1)

        with patch.object(client, '_get_job_status') as mock_get:
            mock_get.return_value = {'succeeded': 1, 'failed': 0, 'active': 0}

            status = await client._wait_for_job('test-job', 'test-ns', timeout_seconds=5)

            assert status == K8sJobStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_wait_for_job_fails(self):
        """Deve detectar Job falhou."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient, K8sJobStatus

        client = KubernetesJobsClient(namespace='test-ns', poll_interval=0.1)

        with patch.object(client, '_get_job_status') as mock_get:
            mock_get.return_value = {'succeeded': 0, 'failed': 1, 'active': 0}

            status = await client._wait_for_job('test-job', 'test-ns', timeout_seconds=5)

            assert status == K8sJobStatus.FAILED


class TestK8sJobsClientPodOperations:
    """Testes de operacoes com Pods."""

    @pytest.mark.asyncio
    async def test_get_pod_for_job(self):
        """Deve obter Pod criado pelo Job."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')
        client._core_api = AsyncMock()

        mock_pod = MagicMock()
        mock_pod.metadata.name = 'test-job-abc123'

        mock_pods = MagicMock()
        mock_pods.items = [mock_pod]

        client._core_api.list_namespaced_pod = AsyncMock(return_value=mock_pods)

        pod_name = await client._get_pod_for_job('test-job', 'test-ns')

        assert pod_name == 'test-job-abc123'

    @pytest.mark.asyncio
    async def test_get_pod_logs(self):
        """Deve obter logs do Pod."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')
        client._core_api = AsyncMock()
        client._core_api.read_namespaced_pod_log = AsyncMock(
            return_value='Line 1\nLine 2\nLine 3'
        )

        logs = await client._get_pod_logs('test-pod', 'test-ns')

        assert 'Line 1' in logs
        assert 'Line 3' in logs

    @pytest.mark.asyncio
    async def test_get_pod_exit_code(self):
        """Deve obter exit code do container."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')
        client._core_api = AsyncMock()

        mock_container_status = MagicMock()
        mock_container_status.name = 'executor'
        mock_container_status.state.terminated.exit_code = 0

        mock_pod = MagicMock()
        mock_pod.status.container_statuses = [mock_container_status]

        client._core_api.read_namespaced_pod_status = AsyncMock(return_value=mock_pod)

        exit_code = await client._get_pod_exit_code('test-pod', 'test-ns')

        assert exit_code == 0


class TestK8sJobsClientHealthCheck:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Deve retornar True quando API acessivel."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')
        client._batch_api = AsyncMock()
        client._batch_api.get_api_resources = AsyncMock()

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Deve retornar False quando API inacessivel."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')
        client._batch_api = None

        result = await client.health_check()

        assert result is False


class TestK8sJobsClientCleanup:
    """Testes de cleanup de Jobs."""

    @pytest.mark.asyncio
    async def test_delete_job_success(self):
        """Deve deletar Job com sucesso."""
        from src.clients.k8s_jobs_client import KubernetesJobsClient

        client = KubernetesJobsClient(namespace='test-ns')
        client._batch_api = AsyncMock()
        client._batch_api.delete_namespaced_job = AsyncMock()

        await client._delete_job('test-job', 'test-ns')

        client._batch_api.delete_namespaced_job.assert_called_once()
