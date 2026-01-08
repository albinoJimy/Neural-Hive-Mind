"""
Testes de Validação de Lineage

Testes para o módulo LineageTracker com foco em:
- Validação de integridade de lineage
- Verificação de consistência de timestamps
- Detecção de ciclos
- Métricas Prometheus
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.services.lineage_tracker import LineageTracker


class MockSettings:
    """Mock de configurações para testes"""
    def __init__(self):
        self.mongodb_lineage_collection = 'data_lineage'
        self.mongodb_context_collection = 'operational_context'


@pytest.fixture
def settings():
    """Fixture de configurações"""
    return MockSettings()


@pytest.fixture
def mock_mongodb():
    """Mock do cliente MongoDB"""
    mongodb = AsyncMock()
    mongodb.find_one = AsyncMock(return_value=None)
    mongodb.find = AsyncMock(return_value=[])
    mongodb.insert_one = AsyncMock(return_value='test-id')
    return mongodb


@pytest.fixture
def mock_neo4j():
    """Mock do cliente Neo4j"""
    neo4j = AsyncMock()
    neo4j.run_query = AsyncMock(return_value=[{'cycle_count': 0}])
    return neo4j


class TestValidateLineageIntegrity:
    """Testes de validação de integridade de lineage"""

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_timestamp_valid(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa validação com timestamps corretos"""
        now = datetime.utcnow()
        source_timestamp = now - timedelta(hours=2)
        entity_timestamp = now - timedelta(hours=1)

        call_count = [0]
        def mock_find_one(collection, filter):
            call_count[0] += 1
            if call_count[0] == 1:
                # Entidade principal
                return {
                    'entity_id': 'entity-1',
                    'source_ids': ['source-1'],
                    'timestamp': entity_timestamp
                }
            elif call_count[0] == 2:
                # Verifica existência da source
                return {
                    'entity_id': 'source-1',
                    'timestamp': source_timestamp
                }
            else:
                # Busca timestamp da source
                return {
                    'entity_id': 'source-1',
                    'timestamp': source_timestamp
                }

        mock_mongodb.find_one = AsyncMock(side_effect=mock_find_one)
        mock_neo4j.run_query = AsyncMock(return_value=[{'cycle_count': 0}])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('entity-1')

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_timestamp_invalid(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa detecção de violação de timestamp"""
        now = datetime.utcnow()
        # Source criada DEPOIS da entidade (violação)
        source_timestamp = now - timedelta(hours=1)
        entity_timestamp = now - timedelta(hours=2)

        call_count = [0]
        def mock_find_one(collection, filter):
            call_count[0] += 1
            if call_count[0] == 1:
                # Entidade principal
                return {
                    'entity_id': 'entity-1',
                    'source_ids': ['source-1'],
                    'timestamp': entity_timestamp
                }
            elif call_count[0] == 2:
                # Verifica existência da source
                return {
                    'entity_id': 'source-1',
                    'timestamp': source_timestamp
                }
            else:
                # Busca timestamp da source
                return {
                    'entity_id': 'source-1',
                    'timestamp': source_timestamp
                }

        mock_mongodb.find_one = AsyncMock(side_effect=mock_find_one)
        mock_neo4j.run_query = AsyncMock(return_value=[{'cycle_count': 0}])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('entity-1')

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_missing_entity(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa que entidade inexistente retorna False"""
        mock_mongodb.find_one = AsyncMock(return_value=None)

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('non-existent')

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_missing_source(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa que source inexistente retorna False"""
        call_count = [0]
        def mock_find_one(collection, filter):
            call_count[0] += 1
            if call_count[0] == 1:
                # Entidade principal existe
                return {
                    'entity_id': 'entity-1',
                    'source_ids': ['source-1'],
                    'timestamp': datetime.utcnow()
                }
            else:
                # Source não existe
                return None

        mock_mongodb.find_one = AsyncMock(side_effect=mock_find_one)

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('entity-1')

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_cycle_detected(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa detecção de ciclos no grafo"""
        mock_mongodb.find_one = AsyncMock(return_value={
            'entity_id': 'entity-1',
            'source_ids': ['source-1'],
            'timestamp': datetime.utcnow()
        })

        # Simula ciclo detectado
        mock_neo4j.run_query = AsyncMock(return_value=[{'cycle_count': 1}])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('entity-1')

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_timestamp_string_format(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa validação com timestamps em formato string ISO"""
        now = datetime.utcnow()
        source_timestamp = (now - timedelta(hours=2)).isoformat()
        entity_timestamp = (now - timedelta(hours=1)).isoformat()

        call_count = [0]
        def mock_find_one(collection, filter):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'entity_id': 'entity-1',
                    'source_ids': ['source-1'],
                    'timestamp': entity_timestamp
                }
            elif call_count[0] == 2:
                return {
                    'entity_id': 'source-1',
                    'timestamp': source_timestamp
                }
            else:
                return {
                    'entity_id': 'source-1',
                    'timestamp': source_timestamp
                }

        mock_mongodb.find_one = AsyncMock(side_effect=mock_find_one)
        mock_neo4j.run_query = AsyncMock(return_value=[{'cycle_count': 0}])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('entity-1')

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_no_sources(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa validação de entidade sem sources (raiz do lineage)"""
        mock_mongodb.find_one = AsyncMock(return_value={
            'entity_id': 'root-entity',
            'source_ids': [],
            'timestamp': datetime.utcnow()
        })
        mock_neo4j.run_query = AsyncMock(return_value=[{'cycle_count': 0}])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('root-entity')

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_lineage_integrity_missing_timestamp(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa que entidade sem timestamp retorna False"""
        mock_mongodb.find_one = AsyncMock(return_value={
            'entity_id': 'entity-1',
            'source_ids': [],
            # Sem timestamp
        })
        mock_neo4j.run_query = AsyncMock(return_value=[{'cycle_count': 0}])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.validate_lineage_integrity('entity-1')

        assert result is False


class TestTrackLineage:
    """Testes de rastreamento de lineage"""

    @pytest.mark.asyncio
    async def test_track_lineage_creates_mongodb_document(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa que lineage é persistido no MongoDB"""
        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        lineage_id = await tracker.track_lineage(
            entity_id='entity-1',
            entity_type='plan',
            source_ids=['source-1', 'source-2'],
            transformation_type='derived',
            metadata={'key': 'value'}
        )

        assert lineage_id is not None
        mock_mongodb.insert_one.assert_called_once()

        # Verifica estrutura do documento
        call_args = mock_mongodb.insert_one.call_args
        document = call_args[1]['document']
        assert document['entity_id'] == 'entity-1'
        assert document['entity_type'] == 'plan'
        assert document['source_ids'] == ['source-1', 'source-2']
        assert document['transformation_type'] == 'derived'

    @pytest.mark.asyncio
    async def test_track_lineage_creates_neo4j_relationships(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa que relacionamentos são criados no Neo4j"""
        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        await tracker.track_lineage(
            entity_id='entity-1',
            entity_type='plan',
            source_ids=['source-1', 'source-2'],
            transformation_type='derived',
            metadata={}
        )

        # Deve criar um relacionamento para cada source
        assert mock_neo4j.run_query.call_count == 2


class TestGetLineageTree:
    """Testes de obtenção de árvore de lineage"""

    @pytest.mark.asyncio
    async def test_get_lineage_tree_upstream(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa obtenção de árvore upstream"""
        mock_mongodb.find_one = AsyncMock(return_value={
            'entity_id': 'entity-1',
            'source_ids': ['source-1']
        })
        mock_neo4j.run_query = AsyncMock(return_value=[
            {'source': {'id': 'source-1'}, 'path': []}
        ])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.get_lineage_tree('entity-1', direction='upstream')

        assert result['entity_id'] == 'entity-1'
        assert result['direction'] == 'upstream'

    @pytest.mark.asyncio
    async def test_get_lineage_tree_not_found(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa obtenção quando entidade não existe"""
        mock_mongodb.find_one = AsyncMock(return_value=None)
        mock_neo4j.run_query = AsyncMock(return_value=[])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.get_lineage_tree('non-existent')

        assert result['entity_id'] == 'non-existent'
        assert result['metadata'] == {}


class TestGetLineagePath:
    """Testes de obtenção de caminho de lineage"""

    @pytest.mark.asyncio
    async def test_get_lineage_path_found(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa obtenção de caminho entre duas entidades"""
        mock_neo4j.run_query = AsyncMock(return_value=[{
            'transformations': [
                {'type': 'DERIVED_FROM', 'transformation_type': 'enriched', 'lineage_id': 'lid-1'},
                {'type': 'DERIVED_FROM', 'transformation_type': 'derived', 'lineage_id': 'lid-2'}
            ]
        }])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.get_lineage_path('source-1', 'target-1')

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_lineage_path_not_found(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa quando não há caminho entre entidades"""
        mock_neo4j.run_query = AsyncMock(return_value=[])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.get_lineage_path('source-1', 'target-1')

        assert result == []


class TestGetImpactAnalysis:
    """Testes de análise de impacto"""

    @pytest.mark.asyncio
    async def test_get_impact_analysis_returns_counts(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa que análise de impacto retorna contagens"""
        mock_neo4j.run_query = AsyncMock(return_value=[{
            'total_impacted': 5,
            'impacted_ids': ['e1', 'e2', 'e3', 'e4', 'e5']
        }])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.get_impact_analysis('entity-1')

        assert result['entity_id'] == 'entity-1'
        assert result['total_impacted'] == 5
        assert len(result['impacted_entities']) == 5

    @pytest.mark.asyncio
    async def test_get_impact_analysis_no_impact(
        self,
        settings,
        mock_mongodb,
        mock_neo4j
    ):
        """Testa quando não há entidades impactadas"""
        mock_neo4j.run_query = AsyncMock(return_value=[])

        tracker = LineageTracker(mock_mongodb, mock_neo4j, settings)

        result = await tracker.get_impact_analysis('leaf-entity')

        assert result['total_impacted'] == 0
        assert result['impacted_entities'] == []
