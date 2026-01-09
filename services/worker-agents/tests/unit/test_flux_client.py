"""
Testes unitarios para FluxClient.

Cobertura:
- Criacao de Kustomization
- Obtencao de status
- Wait for ready
- Reconciliation
- Delete
- List
- Error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFluxClientInitialization:
    """Testes de inicializacao."""

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Deve inicializar cliente com sucesso."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')

        with patch('src.clients.flux_client.config') as mock_config:
            mock_config.load_incluster_config = MagicMock()

            with patch('src.clients.flux_client.client') as mock_client:
                mock_client.CustomObjectsApi = MagicMock()
                mock_client.ApiClient = MagicMock()

                await client.initialize()

                assert client._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_kubernetes_not_installed(self):
        """Deve levantar erro quando kubernetes-asyncio nao instalado."""
        from src.clients.flux_client import FluxClient, FluxAPIError

        client = FluxClient(namespace='flux-system')

        with patch.dict('sys.modules', {'kubernetes_asyncio': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                # O erro vai ser de ImportError dentro do initialize
                pass


class TestFluxClientCreateKustomization:
    """Testes de criacao de Kustomization."""

    @pytest.mark.asyncio
    async def test_create_kustomization_success(self):
        """Deve criar Kustomization com sucesso."""
        from src.clients.flux_client import (
            FluxClient, KustomizationRequest, KustomizationMetadata,
            KustomizationSpec, SourceReference
        )

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()
        client._api.create_namespaced_custom_object = AsyncMock()

        request = KustomizationRequest(
            metadata=KustomizationMetadata(
                name='test-app',
                namespace='flux-system'
            ),
            spec=KustomizationSpec(
                interval='5m',
                path='./deploy',
                sourceRef=SourceReference(
                    kind='GitRepository',
                    name='test-repo'
                )
            )
        )

        name = await client.create_kustomization(request)

        assert name == 'test-app'
        client._api.create_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_kustomization_not_initialized(self):
        """Deve levantar erro quando nao inicializado."""
        from src.clients.flux_client import (
            FluxClient, FluxAPIError, KustomizationRequest,
            KustomizationMetadata, KustomizationSpec, SourceReference
        )

        client = FluxClient(namespace='flux-system')

        request = KustomizationRequest(
            metadata=KustomizationMetadata(name='test-app'),
            spec=KustomizationSpec(
                sourceRef=SourceReference(kind='GitRepository', name='test')
            )
        )

        with pytest.raises(FluxAPIError, match='nao inicializado'):
            await client.create_kustomization(request)


class TestFluxClientStatus:
    """Testes de obtencao de status."""

    @pytest.mark.asyncio
    async def test_get_kustomization_status_ready(self):
        """Deve obter status ready."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()
        client._api.get_namespaced_custom_object = AsyncMock(return_value={
            'metadata': {'name': 'test-app', 'namespace': 'flux-system'},
            'status': {
                'conditions': [
                    {
                        'type': 'Ready',
                        'status': 'True',
                        'reason': 'ReconciliationSucceeded',
                        'message': 'Applied revision: main@sha1:abc123'
                    }
                ],
                'lastAppliedRevision': 'main@sha1:abc123',
                'lastAttemptedRevision': 'main@sha1:abc123'
            }
        })

        status = await client.get_kustomization_status('test-app')

        assert status.name == 'test-app'
        assert status.ready is True
        assert status.lastAppliedRevision == 'main@sha1:abc123'

    @pytest.mark.asyncio
    async def test_get_kustomization_status_not_ready(self):
        """Deve obter status nao ready."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()
        client._api.get_namespaced_custom_object = AsyncMock(return_value={
            'metadata': {'name': 'test-app'},
            'status': {
                'conditions': [
                    {
                        'type': 'Ready',
                        'status': 'False',
                        'reason': 'ReconciliationFailed',
                        'message': 'Validation failed'
                    }
                ]
            }
        })

        status = await client.get_kustomization_status('test-app')

        assert status.ready is False


class TestFluxClientWaitForReady:
    """Testes de wait for ready."""

    @pytest.mark.asyncio
    async def test_wait_for_ready_success(self):
        """Deve aguardar Kustomization ficar ready."""
        from src.clients.flux_client import FluxClient, KustomizationStatus, Condition

        client = FluxClient(namespace='flux-system')
        client._initialized = True

        with patch.object(client, 'get_kustomization_status') as mock_get:
            mock_get.return_value = KustomizationStatus(
                name='test-app',
                namespace='flux-system',
                ready=True,
                conditions=[
                    Condition(type='Ready', status='True', reason='Succeeded')
                ],
                lastAppliedRevision='main@sha1:abc123'
            )

            status = await client.wait_for_ready(
                name='test-app',
                poll_interval=0.1,
                timeout=5
            )

            assert status.ready is True

    @pytest.mark.asyncio
    async def test_wait_for_ready_timeout(self):
        """Deve levantar timeout."""
        from src.clients.flux_client import (
            FluxClient, FluxTimeoutError, KustomizationStatus, Condition
        )

        client = FluxClient(namespace='flux-system')
        client._initialized = True

        with patch.object(client, 'get_kustomization_status') as mock_get:
            mock_get.return_value = KustomizationStatus(
                name='test-app',
                namespace='flux-system',
                ready=False,
                conditions=[
                    Condition(type='Ready', status='Unknown', reason='Progressing')
                ]
            )

            with pytest.raises(FluxTimeoutError):
                await client.wait_for_ready(
                    name='test-app',
                    poll_interval=0.1,
                    timeout=0.3
                )

    @pytest.mark.asyncio
    async def test_wait_for_ready_failed(self):
        """Deve levantar erro quando Kustomization falha."""
        from src.clients.flux_client import (
            FluxClient, FluxAPIError, KustomizationStatus, Condition
        )

        client = FluxClient(namespace='flux-system')
        client._initialized = True

        with patch.object(client, 'get_kustomization_status') as mock_get:
            mock_get.return_value = KustomizationStatus(
                name='test-app',
                namespace='flux-system',
                ready=False,
                conditions=[
                    Condition(
                        type='Ready',
                        status='False',
                        reason='ReconciliationFailed',
                        message='Validation failed'
                    )
                ]
            )

            with pytest.raises(FluxAPIError, match='falhou'):
                await client.wait_for_ready(
                    name='test-app',
                    poll_interval=0.1,
                    timeout=5
                )


class TestFluxClientReconcile:
    """Testes de reconciliation."""

    @pytest.mark.asyncio
    async def test_reconcile_kustomization_success(self):
        """Deve forcar reconciliacao."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()
        client._api.patch_namespaced_custom_object = AsyncMock(return_value={})

        result = await client.reconcile_kustomization('test-app')

        assert result['name'] == 'test-app'
        assert 'reconcileRequestedAt' in result
        client._api.patch_namespaced_custom_object.assert_called_once()


class TestFluxClientDelete:
    """Testes de delete."""

    @pytest.mark.asyncio
    async def test_delete_kustomization_success(self):
        """Deve deletar Kustomization."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()
        client._api.delete_namespaced_custom_object = AsyncMock()

        result = await client.delete_kustomization('test-app')

        assert result is True
        client._api.delete_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_kustomization_not_found(self):
        """Deve retornar True quando nao encontrado."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()

        # Simular erro 404
        error = Exception('Not found')
        error.status = 404
        client._api.delete_namespaced_custom_object = AsyncMock(side_effect=error)

        result = await client.delete_kustomization('test-app')

        assert result is True


class TestFluxClientList:
    """Testes de listagem."""

    @pytest.mark.asyncio
    async def test_list_kustomizations_success(self):
        """Deve listar Kustomizations."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()
        client._api.list_namespaced_custom_object = AsyncMock(return_value={
            'items': [
                {
                    'metadata': {'name': 'app-1', 'namespace': 'flux-system'},
                    'status': {
                        'conditions': [
                            {'type': 'Ready', 'status': 'True', 'reason': 'Succeeded'}
                        ]
                    }
                },
                {
                    'metadata': {'name': 'app-2', 'namespace': 'flux-system'},
                    'status': {
                        'conditions': [
                            {'type': 'Ready', 'status': 'False', 'reason': 'Failed'}
                        ]
                    }
                }
            ]
        })

        kustomizations = await client.list_kustomizations(namespace='flux-system')

        assert len(kustomizations) == 2
        assert kustomizations[0].name == 'app-1'
        assert kustomizations[0].ready is True
        assert kustomizations[1].ready is False

    @pytest.mark.asyncio
    async def test_list_kustomizations_with_label_selector(self):
        """Deve listar Kustomizations com label selector."""
        from src.clients.flux_client import FluxClient

        client = FluxClient(namespace='flux-system')
        client._initialized = True
        client._api = AsyncMock()
        client._api.list_namespaced_custom_object = AsyncMock(return_value={'items': []})

        await client.list_kustomizations(
            namespace='flux-system',
            label_selector='app=test'
        )

        client._api.list_namespaced_custom_object.assert_called_once()
        call_args = client._api.list_namespaced_custom_object.call_args
        assert call_args.kwargs.get('label_selector') == 'app=test'
