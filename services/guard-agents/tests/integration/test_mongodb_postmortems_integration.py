"""
Testes de integracao para persistencia de post-mortems no MongoDB

Testa operacoes de insercao e consulta de post-mortems
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.clients.mongodb_client import MongoDBClient


@pytest.fixture
def mock_motor_client():
    """Mock do AsyncIOMotorClient"""
    return AsyncMock()


@pytest.fixture
def mock_db():
    """Mock do database"""
    return MagicMock()


@pytest.fixture
def mock_incidents_collection():
    """Mock da colecao de incidentes"""
    return AsyncMock()


@pytest.fixture
def mock_remediation_collection():
    """Mock da colecao de remediation"""
    return AsyncMock()


@pytest.fixture
def mock_postmortems_collection():
    """Mock da colecao de postmortems"""
    return AsyncMock()


@pytest.fixture
def mongodb_client(
    mock_motor_client,
    mock_db,
    mock_incidents_collection,
    mock_remediation_collection,
    mock_postmortems_collection
):
    """Fixture do MongoDBClient com mocks"""
    client = MongoDBClient(
        uri="mongodb://test:test@localhost:27017/test",
        database="test_db"
    )
    client.client = mock_motor_client
    client.db = mock_db
    client.incidents_collection = mock_incidents_collection
    client.remediation_collection = mock_remediation_collection
    client.postmortems_collection = mock_postmortems_collection
    return client


@pytest.fixture
def sample_postmortem():
    """Exemplo de post-mortem para testes"""
    return {
        "incident_id": "INC-TEST-001",
        "threat_type": "unauthorized_access",
        "severity": "high",
        "runbook_id": "RB-SEC-001-HIGH",
        "summary": "Incidente INC-TEST-001 detectado: unauthorized_access com severidade high.",
        "root_cause": "Threat type: unauthorized_access",
        "actions_taken": [
            "Enforcement: revoke_access",
            "Remediation: restart_pod"
        ],
        "sla_performance": {
            "met": True,
            "recovery_time_s": 45.5
        },
        "recommendations": [
            "Melhorar regras de deteccao"
        ],
        "documented_at": datetime.now(timezone.utc).isoformat()
    }


class TestMongoDBClientConnection:
    """Testes de conexao do MongoDB client"""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_motor_client, mock_db):
        """Testa conexao bem-sucedida com MongoDB"""
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.admin.command = AsyncMock(return_value={"ok": 1})
            mock_client_instance.__getitem__ = MagicMock(return_value=mock_db)
            MockClient.return_value = mock_client_instance

            mock_db.__getitem__ = MagicMock(return_value=AsyncMock())

            client = MongoDBClient(
                uri="mongodb://test:test@localhost:27017/test",
                database="test_db"
            )

            await client.connect()

            assert client.client is not None
            assert client.db is not None
            assert client.postmortems_collection is not None

    def test_is_healthy_true(self, mongodb_client):
        """Testa que cliente esta saudavel quando conectado"""
        assert mongodb_client.is_healthy() is True

    def test_is_healthy_false_no_client(self):
        """Testa que cliente nao esta saudavel sem conexao"""
        client = MongoDBClient(
            uri="mongodb://test:test@localhost:27017/test",
            database="test_db"
        )
        client.client = None
        client.db = MagicMock()

        assert client.is_healthy() is False


class TestPostmortemInsertion:
    """Testes de insercao de post-mortems"""

    @pytest.mark.asyncio
    async def test_insert_postmortem_success(
        self, mongodb_client, mock_postmortems_collection, sample_postmortem
    ):
        """Testa insercao bem-sucedida de post-mortem"""
        mock_postmortems_collection.insert_one = AsyncMock(return_value=MagicMock())

        result = await mongodb_client.insert_postmortem(sample_postmortem)

        assert result is True
        mock_postmortems_collection.insert_one.assert_called_once_with(sample_postmortem)

    @pytest.mark.asyncio
    async def test_insert_postmortem_failure(
        self, mongodb_client, mock_postmortems_collection, sample_postmortem
    ):
        """Testa falha na insercao de post-mortem"""
        mock_postmortems_collection.insert_one = AsyncMock(
            side_effect=Exception("MongoDB connection error")
        )

        result = await mongodb_client.insert_postmortem(sample_postmortem)

        assert result is False

    @pytest.mark.asyncio
    async def test_insert_postmortem_no_collection(self, sample_postmortem):
        """Testa insercao quando colecao nao esta inicializada"""
        client = MongoDBClient(
            uri="mongodb://test:test@localhost:27017/test",
            database="test_db"
        )
        client.postmortems_collection = None

        result = await client.insert_postmortem(sample_postmortem)

        assert result is False

    @pytest.mark.asyncio
    async def test_insert_postmortem_with_all_fields(
        self, mongodb_client, mock_postmortems_collection
    ):
        """Testa insercao de post-mortem com todos os campos"""
        full_postmortem = {
            "incident_id": "INC-FULL-001",
            "threat_type": "dos_attack",
            "severity": "critical",
            "runbook_id": "RB-AVAIL-001-CRITICAL",
            "summary": "Ataque DoS detectado e mitigado",
            "root_cause": "Ataque coordenado de multiplas fontes",
            "actions_taken": [
                "Enforcement: block_ip",
                "Enforcement: rate_limit",
                "Remediation: scale_deployment",
                "Remediation: apply_network_policy"
            ],
            "sla_performance": {
                "met": True,
                "recovery_time_s": 78.2
            },
            "recommendations": [
                "Aumentar capacidade de auto-scaling",
                "Implementar WAF",
                "Revisar thresholds de deteccao"
            ],
            "affected_resources": [
                "neural-hive/deployment/gateway-intencoes",
                "neural-hive/pod/gateway-intencoes-abc123"
            ],
            "documented_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "detection_time_s": 12.5,
                "total_blocked_ips": 15,
                "peak_requests_per_minute": 50000
            }
        }

        mock_postmortems_collection.insert_one = AsyncMock(return_value=MagicMock())

        result = await mongodb_client.insert_postmortem(full_postmortem)

        assert result is True
        mock_postmortems_collection.insert_one.assert_called_once()


class TestPostmortemQuery:
    """Testes de consulta de post-mortems"""

    @pytest.mark.asyncio
    async def test_get_postmortem_success(
        self, mongodb_client, mock_postmortems_collection, sample_postmortem
    ):
        """Testa consulta bem-sucedida de post-mortem por incident_id"""
        mock_postmortems_collection.find_one = AsyncMock(return_value=sample_postmortem)

        result = await mongodb_client.get_postmortem("INC-TEST-001")

        assert result is not None
        assert result["incident_id"] == "INC-TEST-001"
        assert result["threat_type"] == "unauthorized_access"
        mock_postmortems_collection.find_one.assert_called_once_with(
            {"incident_id": "INC-TEST-001"}
        )

    @pytest.mark.asyncio
    async def test_get_postmortem_not_found(
        self, mongodb_client, mock_postmortems_collection
    ):
        """Testa consulta de post-mortem nao existente"""
        mock_postmortems_collection.find_one = AsyncMock(return_value=None)

        result = await mongodb_client.get_postmortem("INC-NONEXISTENT")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_postmortem_error(
        self, mongodb_client, mock_postmortems_collection
    ):
        """Testa falha na consulta de post-mortem"""
        mock_postmortems_collection.find_one = AsyncMock(
            side_effect=Exception("Query error")
        )

        result = await mongodb_client.get_postmortem("INC-TEST-001")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_postmortem_no_collection(self):
        """Testa consulta quando colecao nao esta inicializada"""
        client = MongoDBClient(
            uri="mongodb://test:test@localhost:27017/test",
            database="test_db"
        )
        client.postmortems_collection = None

        result = await client.get_postmortem("INC-TEST-001")

        assert result is None


class TestIndexCreation:
    """Testes de criacao de indices"""

    @pytest.mark.asyncio
    async def test_create_indexes_postmortems(
        self, mongodb_client, mock_postmortems_collection
    ):
        """Testa criacao de indices para postmortems"""
        mock_postmortems_collection.create_index = AsyncMock()

        await mongodb_client._create_indexes()

        # Verificar que os indices foram criados
        calls = mock_postmortems_collection.create_index.call_args_list

        # Deve criar 4 indices para postmortems
        assert len(calls) >= 4

        # Verificar indices especificos
        index_calls = [str(call) for call in calls]
        assert any("incident_id" in str(call) for call in calls)
        assert any("documented_at" in str(call) for call in calls)
        assert any("severity" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_create_indexes_failure_does_not_raise(
        self, mongodb_client, mock_postmortems_collection
    ):
        """Testa que falha na criacao de indice nao lanca excecao"""
        mock_postmortems_collection.create_index = AsyncMock(
            side_effect=Exception("Index creation error")
        )

        # Nao deve lancar excecao
        await mongodb_client._create_indexes()


class TestPostmortemSchema:
    """Testes de validacao de schema de post-mortems"""

    @pytest.mark.asyncio
    async def test_postmortem_required_fields(
        self, mongodb_client, mock_postmortems_collection
    ):
        """Testa insercao com campos obrigatorios"""
        minimal_postmortem = {
            "incident_id": "INC-MIN-001",
            "threat_type": "unknown",
            "severity": "low",
            "documented_at": datetime.now(timezone.utc).isoformat()
        }

        mock_postmortems_collection.insert_one = AsyncMock(return_value=MagicMock())

        result = await mongodb_client.insert_postmortem(minimal_postmortem)

        assert result is True

    @pytest.mark.asyncio
    async def test_postmortem_with_nested_data(
        self, mongodb_client, mock_postmortems_collection
    ):
        """Testa insercao de post-mortem com dados aninhados"""
        nested_postmortem = {
            "incident_id": "INC-NESTED-001",
            "threat_type": "data_exfiltration",
            "severity": "critical",
            "anomaly_details": {
                "data_transferred_mb": 500,
                "destination_ips": ["1.2.3.4", "5.6.7.8"],
                "protocols": ["HTTPS", "DNS"]
            },
            "enforcement_details": {
                "actions": [
                    {
                        "type": "block_ip",
                        "target": "1.2.3.4",
                        "success": True
                    },
                    {
                        "type": "quarantine",
                        "target": "compromised-pod",
                        "success": True
                    }
                ]
            },
            "documented_at": datetime.now(timezone.utc).isoformat()
        }

        mock_postmortems_collection.insert_one = AsyncMock(return_value=MagicMock())

        result = await mongodb_client.insert_postmortem(nested_postmortem)

        assert result is True


class TestConnectionClose:
    """Testes de fechamento de conexao"""

    @pytest.mark.asyncio
    async def test_close_connection(self, mongodb_client, mock_motor_client):
        """Testa fechamento de conexao"""
        mock_motor_client.close = MagicMock()

        await mongodb_client.close()

        mock_motor_client.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
