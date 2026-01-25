"""
Testes de integracao para API de Authorization Audit.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_mongodb_client_with_data():
    """Mock do MongoDB client com dados de auditoria."""
    from unittest.mock import AsyncMock, MagicMock

    # Dados de teste
    audit_data = [
        {
            '_id': 'id1',
            'timestamp': (datetime.now() - timedelta(minutes=30)).isoformat(),
            'user_id': 'user-123',
            'tenant_id': 'tenant-abc',
            'decision': 'allow',
            'policy_path': 'neuralhive/orchestrator/security_constraints',
            'violations': [],
            'resource': {'type': 'ticket', 'id': 'ticket-1'},
            'context': {'workflow_id': 'wf-1'}
        },
        {
            '_id': 'id2',
            'timestamp': (datetime.now() - timedelta(minutes=20)).isoformat(),
            'user_id': 'user-456',
            'tenant_id': 'tenant-abc',
            'decision': 'deny',
            'policy_path': 'neuralhive/orchestrator/resource_limits',
            'violations': [{'severity': 'warning', 'msg': 'Limite excedido'}],
            'resource': {'type': 'workflow', 'id': 'wf-2'},
            'context': {'workflow_id': 'wf-2'}
        },
        {
            '_id': 'id3',
            'timestamp': (datetime.now() - timedelta(minutes=10)).isoformat(),
            'user_id': 'user-123',
            'tenant_id': 'tenant-xyz',
            'decision': 'allow',
            'policy_path': 'neuralhive/orchestrator/security_constraints',
            'violations': [],
            'resource': {'type': 'ticket', 'id': 'ticket-3'},
            'context': {'workflow_id': 'wf-3'}
        },
    ]

    # Mock cursor
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.skip = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=audit_data)

    # Mock collection
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=mock_cursor)
    mock_collection.count_documents = AsyncMock(return_value=len(audit_data))

    # Mock client
    mock_client = MagicMock()
    mock_client.authorization_audit = mock_collection

    return mock_client, audit_data


class TestAuthorizationAuditAPI:
    """Testes para endpoint /api/v1/audit/authorizations."""

    @pytest.mark.asyncio
    async def test_query_authorization_audit_all(self, mock_mongodb_client_with_data):
        """Testa query de todas as entradas de auditoria."""
        mock_client, audit_data = mock_mongodb_client_with_data

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get('/api/v1/audit/authorizations')

                assert response.status_code == 200
                data = response.json()
                assert 'total' in data
                assert 'results' in data
                assert data['total'] == 3
                assert len(data['results']) == 3

    @pytest.mark.asyncio
    async def test_query_authorization_audit_by_tenant(self, mock_mongodb_client_with_data):
        """Testa query filtrada por tenant."""
        mock_client, audit_data = mock_mongodb_client_with_data

        # Filtrar apenas tenant-abc
        filtered_data = [d for d in audit_data if d['tenant_id'] == 'tenant-abc']
        mock_client.authorization_audit.find.return_value.to_list = AsyncMock(return_value=filtered_data)
        mock_client.authorization_audit.count_documents = AsyncMock(return_value=len(filtered_data))

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get(
                    '/api/v1/audit/authorizations',
                    params={'tenant_id': 'tenant-abc'}
                )

                assert response.status_code == 200
                data = response.json()

                # Verificar filtro aplicado
                assert data['query']['tenant_id'] == 'tenant-abc'

    @pytest.mark.asyncio
    async def test_query_authorization_audit_by_decision(self, mock_mongodb_client_with_data):
        """Testa query filtrada por decisao."""
        mock_client, audit_data = mock_mongodb_client_with_data

        # Filtrar apenas deny
        filtered_data = [d for d in audit_data if d['decision'] == 'deny']
        mock_client.authorization_audit.find.return_value.to_list = AsyncMock(return_value=filtered_data)
        mock_client.authorization_audit.count_documents = AsyncMock(return_value=len(filtered_data))

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get(
                    '/api/v1/audit/authorizations',
                    params={'decision': 'deny'}
                )

                assert response.status_code == 200
                data = response.json()
                assert data['query']['decision'] == 'deny'

    @pytest.mark.asyncio
    async def test_query_authorization_audit_pagination(self, mock_mongodb_client_with_data):
        """Testa paginacao de resultados."""
        mock_client, audit_data = mock_mongodb_client_with_data

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                # Primeira pagina
                response1 = await client.get(
                    '/api/v1/audit/authorizations',
                    params={'limit': 2, 'skip': 0}
                )

                assert response1.status_code == 200
                data1 = response1.json()
                assert data1['query']['limit'] == 2
                assert data1['query']['skip'] == 0

                # Segunda pagina
                response2 = await client.get(
                    '/api/v1/audit/authorizations',
                    params={'limit': 2, 'skip': 2}
                )

                assert response2.status_code == 200
                data2 = response2.json()
                assert data2['query']['skip'] == 2

    @pytest.mark.asyncio
    async def test_query_authorization_audit_time_range(self, mock_mongodb_client_with_data):
        """Testa query com filtro de periodo."""
        mock_client, audit_data = mock_mongodb_client_with_data

        now = datetime.now()
        start_time = (now - timedelta(hours=1)).isoformat()
        end_time = now.isoformat()

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get(
                    '/api/v1/audit/authorizations',
                    params={
                        'start_time': start_time,
                        'end_time': end_time
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data['query']['start_time'] == start_time
                assert data['query']['end_time'] == end_time

    @pytest.mark.asyncio
    async def test_query_authorization_audit_mongodb_unavailable(self):
        """Testa resposta quando MongoDB nao esta disponivel."""
        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = None

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get('/api/v1/audit/authorizations')

                assert response.status_code == 503
                assert 'MongoDB' in response.json()['detail']

    @pytest.mark.asyncio
    async def test_query_authorization_audit_removes_mongodb_id(self, mock_mongodb_client_with_data):
        """Testa que _id do MongoDB e removido dos resultados."""
        mock_client, audit_data = mock_mongodb_client_with_data

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get('/api/v1/audit/authorizations')

                assert response.status_code == 200
                data = response.json()

                # Verificar que _id foi removido
                for result in data['results']:
                    assert '_id' not in result

    @pytest.mark.asyncio
    async def test_query_authorization_audit_by_user_id(self, mock_mongodb_client_with_data):
        """Testa query filtrada por user_id."""
        mock_client, audit_data = mock_mongodb_client_with_data

        # Filtrar por user-123
        filtered_data = [d for d in audit_data if d['user_id'] == 'user-123']
        mock_client.authorization_audit.find.return_value.to_list = AsyncMock(return_value=filtered_data)
        mock_client.authorization_audit.count_documents = AsyncMock(return_value=len(filtered_data))

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get(
                    '/api/v1/audit/authorizations',
                    params={'user_id': 'user-123'}
                )

                assert response.status_code == 200
                data = response.json()
                assert data['query']['user_id'] == 'user-123'

    @pytest.mark.asyncio
    async def test_query_authorization_audit_by_policy_path(self, mock_mongodb_client_with_data):
        """Testa query filtrada por policy_path."""
        mock_client, audit_data = mock_mongodb_client_with_data

        policy = 'neuralhive/orchestrator/security_constraints'
        filtered_data = [d for d in audit_data if d['policy_path'] == policy]
        mock_client.authorization_audit.find.return_value.to_list = AsyncMock(return_value=filtered_data)
        mock_client.authorization_audit.count_documents = AsyncMock(return_value=len(filtered_data))

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get(
                    '/api/v1/audit/authorizations',
                    params={'policy_path': policy}
                )

                assert response.status_code == 200
                data = response.json()
                assert data['query']['policy_path'] == policy

    @pytest.mark.asyncio
    async def test_query_authorization_audit_limit_validation(self, mock_mongodb_client_with_data):
        """Testa validacao de limite maximo."""
        mock_client, _ = mock_mongodb_client_with_data

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                # Limite acima do maximo (1000)
                response = await client.get(
                    '/api/v1/audit/authorizations',
                    params={'limit': 2000}
                )

                # FastAPI deve rejeitar com 422 (Validation Error)
                assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_authorization_audit_combined_filters(self, mock_mongodb_client_with_data):
        """Testa multiplos filtros combinados."""
        mock_client, audit_data = mock_mongodb_client_with_data

        with patch('src.main.app_state') as mock_app_state:
            mock_app_state.mongodb_client = mock_client

            from httpx import AsyncClient, ASGITransport
            from src.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get(
                    '/api/v1/audit/authorizations',
                    params={
                        'tenant_id': 'tenant-abc',
                        'decision': 'allow',
                        'user_id': 'user-123',
                        'limit': 50
                    }
                )

                assert response.status_code == 200
                data = response.json()

                # Verificar todos os filtros na query
                assert data['query']['tenant_id'] == 'tenant-abc'
                assert data['query']['decision'] == 'allow'
                assert data['query']['user_id'] == 'user-123'
                assert data['query']['limit'] == 50
