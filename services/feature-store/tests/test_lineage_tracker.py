"""
Testes para LineageTracker do Feature Store.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models.lineage import (
    FeatureLineage,
    LineageImpact,
    LineageIntegrityReport,
    LineageTree,
    SourceType,
    TransformationType,
)
from src.services.lineage_tracker import LineageTracker

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def mock_settings():
    """Mock das configurações."""
    settings = MagicMock()
    settings.mongodb_database = "test_db"
    settings.mongodb_lineage_collection = "test_lineage"
    return settings


@pytest.fixture()
def mock_mongodb_client():
    """Mock do cliente MongoDB."""
    client = MagicMock()
    database = MagicMock()
    collection = MagicMock()

    client.__getitem__ = MagicMock(return_value=database)
    database.__getitem__ = MagicMock(return_value=collection)
    database.__getitem__ = MagicMock(return_value=collection)

    # Mock collection methods
    collection.create_index = AsyncMock()
    collection.update_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find = MagicMock()
    collection.delete_one = AsyncMock()

    return client


@pytest.fixture()
def mock_neo4j_client():
    """Mock do cliente Neo4j."""
    client = MagicMock()
    client.create_relationship = AsyncMock()
    client.delete_node_relationships = AsyncMock()
    client.get_upstream = AsyncMock(return_value={})
    client.get_downstream = AsyncMock(return_value={})
    return client


@pytest.fixture()
def lineage_tracker(mock_settings, mock_mongodb_client):
    """Instância do LineageTracker para testes."""
    return LineageTracker(
        settings=mock_settings,
        mongodb_client=mock_mongodb_client,
        neo4j_client=None,
    )


@pytest.fixture()
def lineage_tracker_with_neo4j(mock_settings, mock_mongodb_client, mock_neo4j_client):
    """Instância do LineageTracker com Neo4j para testes."""
    return LineageTracker(
        settings=mock_settings,
        mongodb_client=mock_mongodb_client,
        neo4j_client=mock_neo4j_client,
    )


@pytest.fixture()
def sample_lineage():
    """Lineage de exemplo."""
    return FeatureLineage(
        feature_id="feature-123",
        plan_id="plan-123",
        source_type=SourceType.COGNITIVE_PLAN,
        transformation_type=TransformationType.COMPUTED,
        data_sources=["api", "database"],
        source_plan_ids=["plan-100"],
        feature_dependencies=["feature-100"],
        parent_lineage_ids=["lineage-100"],
        transformation_metadata={"model": "v1.0"},
        computation_version="v1.0.0",
        computation_hash="abc123def4567890",
    )


# =============================================================================
# Testes de Inicialização
# =============================================================================


class TestLineageTrackerInit:
    """Testes de inicialização do LineageTracker."""

    def test_init_with_mongodb_only(self, mock_settings, mock_mongodb_client):
        """Testa inicialização com MongoDB apenas."""
        tracker = LineageTracker(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            neo4j_client=None,
        )

        assert tracker.settings == mock_settings
        assert tracker.mongodb_client == mock_mongodb_client
        assert tracker.neo4j_client is None
        assert tracker.computation_version == "v1.0.0"

    def test_init_with_neo4j(self, mock_settings, mock_mongodb_client, mock_neo4j_client):
        """Testa inicialização com Neo4j."""
        tracker = LineageTracker(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            neo4j_client=mock_neo4j_client,
        )

        assert tracker.neo4j_client == mock_neo4j_client

    def test_init_without_clients(self, mock_settings):
        """Testa inicialização sem clientes."""
        tracker = LineageTracker(
            settings=mock_settings,
            mongodb_client=None,
            neo4j_client=None,
        )

        assert tracker.mongodb_client is None
        assert tracker.neo4j_client is None


# =============================================================================
# Testes de Criação de Índices
# =============================================================================


class TestCreateIndexes:
    """Testes de criação de índices."""

    @pytest.mark.asyncio()
    async def test_create_indexes_success(self, lineage_tracker):
        """Testa criação bem-sucedida de índices."""
        await lineage_tracker.create_indexes()

        # Verificar que create_index foi chamado para os índices esperados
        assert lineage_tracker.collection.create_index.call_count == 7

    @pytest.mark.asyncio()
    async def test_create_indexes_without_mongodb(self, mock_settings):
        """Testa criação de índices sem MongoDB (não deve dar erro)."""
        tracker = LineageTracker(
            settings=mock_settings,
            mongodb_client=None,
            neo4j_client=None,
        )

        await tracker.create_indexes()  # Não deve levantar exceção


# =============================================================================
# Testes de Track Feature
# =============================================================================


class TestTrackFeature:
    """Testes de rastreamento de features."""

    @pytest.mark.asyncio()
    async def test_track_feature_success(self, lineage_tracker):
        """Testa rastreamento bem-sucedido de feature."""
        result = await lineage_tracker.track_feature(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            data_sources=["api"],
            source_plan_ids=["plan-100"],
        )

        assert isinstance(result, FeatureLineage)
        assert result.feature_id == "feature-123"
        assert result.plan_id == "plan-123"
        assert result.source_type == SourceType.COGNITIVE_PLAN
        assert result.transformation_type == TransformationType.COMPUTED

    @pytest.mark.asyncio()
    async def test_track_feature_saves_to_mongodb(self, lineage_tracker):
        """Testa que track_feature salva no MongoDB."""
        await lineage_tracker.track_feature(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.DERIVED,
            transformation_type=TransformationType.MERGED,
        )

        lineage_tracker.collection.update_one.assert_called_once()

    @pytest.mark.asyncio()
    async def test_track_feature_with_neo4j(self, lineage_tracker_with_neo4j):
        """Testa que track_feature cria relacionamentos no Neo4j."""
        await lineage_tracker_with_neo4j.track_feature(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            source_plan_ids=["plan-100", "plan-200"],
            feature_dependencies=["feature-100"],
        )

        # Verificar que create_relationship foi chamado
        assert lineage_tracker_with_neo4j.neo4j_client.create_relationship.call_count == 3

    @pytest.mark.asyncio()
    async def test_track_feature_computes_hash(self, lineage_tracker):
        """Testa que track_feature computa hash de computação."""
        result = await lineage_tracker.track_feature(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
        )

        assert result.computation_hash is not None
        assert len(result.computation_hash) == 16  # SHA256[:16]
        assert result.computation_version == "v1.0.0"

    @pytest.mark.asyncio()
    async def test_track_feature_with_metadata(self, lineage_tracker):
        """Testa track_feature com metadados de transformação."""
        metadata = {
            "model": "v2.0",
            "parameters": {"learning_rate": 0.001},
            "execution_time_ms": 1500,
        }

        result = await lineage_tracker.track_feature(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.ENRICHED,
            transformation_type=TransformationType.TRANSFORMED,
            transformation_metadata=metadata,
        )

        assert result.transformation_metadata == metadata


# =============================================================================
# Testes de Get Lineage
# =============================================================================


class TestGetLineage:
    """Testes de recuperação de lineage."""

    @pytest.mark.asyncio()
    async def test_get_lineage_found(self, lineage_tracker, sample_lineage):
        """Testa recuperação de lineage existente."""
        # Mock find_one para retornar lineage
        document = sample_lineage.model_dump(mode="json")
        document["_id"] = "mongo-id-123"
        lineage_tracker.collection.find_one = AsyncMock(return_value=document)

        result = await lineage_tracker.get_lineage("feature-123")

        assert isinstance(result, FeatureLineage)
        assert result.feature_id == "feature-123"

    @pytest.mark.asyncio()
    async def test_get_lineage_not_found(self, lineage_tracker):
        """Testa recuperação de lineage inexistente."""
        lineage_tracker.collection.find_one = AsyncMock(return_value=None)

        result = await lineage_tracker.get_lineage("feature-999")

        assert result is None

    @pytest.mark.asyncio()
    async def test_get_lineage_by_plan(self, lineage_tracker, sample_lineage):
        """Testa recuperação de lineage por plan_id."""
        document = sample_lineage.model_dump(mode="json")
        document["_id"] = "mongo-id-123"
        lineage_tracker.collection.find_one = AsyncMock(return_value=document)

        result = await lineage_tracker.get_lineage_by_plan("plan-123")

        assert isinstance(result, FeatureLineage)
        assert result.plan_id == "plan-123"

    @pytest.mark.asyncio()
    async def test_get_lineage_without_mongodb(self, mock_settings):
        """Testa get_lineage sem MongoDB."""
        tracker = LineageTracker(
            settings=mock_settings,
            mongodb_client=None,
            neo4j_client=None,
        )

        result = await tracker.get_lineage("feature-123")

        assert result is None


# =============================================================================
# Testes de Get Lineage Tree
# =============================================================================


class TestGetLineageTree:
    """Testes de recuperação de árvore de lineage."""

    @pytest.mark.asyncio()
    async def test_get_lineage_tree_basic(self, lineage_tracker, sample_lineage):
        """Testa recuperação básica de árvore de lineage."""
        document = sample_lineage.model_dump(mode="json")
        document["_id"] = "mongo-id-123"
        lineage_tracker.collection.find_one = AsyncMock(return_value=document)

        result = await lineage_tracker.get_lineage_tree("feature-123")

        assert isinstance(result, LineageTree)
        assert result.feature_id == "feature-123"
        assert result.lineage is not None

    @pytest.mark.asyncio()
    async def test_get_lineage_tree_with_upstream(self, lineage_tracker):
        """Testa árvore de lineage com upstream."""
        # Mock para buscar lineage principal
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.DERIVED,
            transformation_type=TransformationType.MERGED,
            parent_lineage_ids=["parent-1", "parent-2"],
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        # Mock para buscar parents
        parent_lineage = FeatureLineage(
            feature_id="parent-1",
            plan_id="plan-100",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        async def mock_find_one(query):
            if query.get("feature_id") == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            elif query.get("feature_id") == "parent-1":
                doc = parent_lineage.model_dump(mode="json")
                doc["_id"] = "id-parent"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        result = await lineage_tracker.get_lineage_tree("feature-123")

        assert "depth_1" in result.upstream
        assert len(result.upstream["depth_1"]) == 2

    @pytest.mark.asyncio()
    async def test_get_lineage_tree_with_downstream(self, lineage_tracker):
        """Testa árvore de lineage com downstream."""
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        # Mock para filho direto
        child_document = {
            "feature_id": "child-1",
            "plan_id": "plan-200",
            "transformation_type": "derived",
            "_id": "id-child",
        }

        async def mock_find_one(query):
            if query.get("feature_id") == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        # Mock cursor para downstream
        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter([child_document]))
        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.get_lineage_tree("feature-123")

        assert "depth_1" in result.downstream

    @pytest.mark.asyncio()
    async def test_get_lineage_tree_max_depth(self, lineage_tracker):
        """Testa árvore de lineage com profundidade máxima."""
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.DERIVED,
            transformation_type=TransformationType.MERGED,
            parent_lineage_ids=["parent-1"],
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        parent_lineage = FeatureLineage(
            feature_id="parent-1",
            plan_id="plan-100",
            source_type=SourceType.DERIVED,
            transformation_type=TransformationType.MERGED,
            parent_lineage_ids=["grandparent-1"],
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        grandparent_lineage = FeatureLineage(
            feature_id="grandparent-1",
            plan_id="plan-50",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        async def mock_find_one(query):
            feature_id = query.get("feature_id")
            if feature_id == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            elif feature_id == "parent-1":
                doc = parent_lineage.model_dump(mode="json")
                doc["_id"] = "id-parent"
                return doc
            elif feature_id == "grandparent-1":
                doc = grandparent_lineage.model_dump(mode="json")
                doc["_id"] = "id-grandparent"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        result = await lineage_tracker.get_lineage_tree("feature-123", max_depth=2)

        # Deve ter depth_1 e depth_2
        assert "depth_1" in result.upstream
        assert "depth_2" in result.upstream
        # Não deve ter depth_3 (excede max_depth)
        assert "depth_3" not in result.upstream


# =============================================================================
# Testes de Impact Analysis
# =============================================================================


class TestImpactAnalysis:
    """Testes de análise de impacto."""

    @pytest.mark.asyncio()
    async def test_get_impact_analysis_basic(self, lineage_tracker):
        """Testa análise básica de impacto."""
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        child_document = {
            "feature_id": "child-1",
            "plan_id": "plan-200",
            "transformation_type": "derived",
            "_id": "id-child",
        }

        async def mock_find_one(query):
            if query.get("feature_id") == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter([child_document]))
        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.get_impact_analysis("feature-123")

        assert isinstance(result, LineageImpact)
        assert result.feature_id == "feature-123"
        assert result.direct_dependencies == 1
        assert result.total_downstream >= 1

    @pytest.mark.asyncio()
    async def test_get_impact_analysis_score_calculation(self, lineage_tracker):
        """Testa cálculo de score de impacto."""
        # Criar 10 filhos diretos
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        children = [
            {
                "feature_id": f"child-{i}",
                "plan_id": f"plan-{i}",
                "transformation_type": "derived",
                "_id": f"id-child-{i}",
            }
            for i in range(10)
        ]

        async def mock_find_one(query):
            if query.get("feature_id") == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter(children))
        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.get_impact_analysis("feature-123")

        # Score deve ser > 0 devido a dependências
        assert result.impact_score > 0
        assert result.direct_dependencies == 10


# =============================================================================
# Testes de Validate Integrity
# =============================================================================


class TestValidateIntegrity:
    """Testes de validação de integridade."""

    @pytest.mark.asyncio()
    async def test_validate_integrity_valid(self, lineage_tracker):
        """Testa validação de lineage válido."""
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            data_sources=["api"],  # Tem data sources
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        async def mock_find_one(query):
            if query.get("feature_id") == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter([]))
        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.validate_integrity("feature-123")

        assert isinstance(result, LineageIntegrityReport)
        assert result.feature_id == "feature-123"
        # Deve ser válido (sem ciclos, timestamps OK, etc.)
        assert result.valid is True

    @pytest.mark.asyncio()
    async def test_validate_integrity_no_datasources(self, lineage_tracker):
        """Testa validação detecta falta de datasources."""
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.COGNITIVE_PLAN,
            transformation_type=TransformationType.COMPUTED,
            data_sources=[],  # Vazio para COGNITIVE_PLAN é problema
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        async def mock_find_one(query):
            if query.get("feature_id") == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter([]))
        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.validate_integrity("feature-123")

        # Deve ter warning sobre datasources
        assert len(result.warnings) > 0
        assert "datasources" in str(result.warnings).lower()

    @pytest.mark.asyncio()
    async def test_validate_integrity_with_cycle(self, lineage_tracker):
        """Testa validação detecta ciclo (simulado)."""
        # Criar lineage que referencia a si mesmo
        main_lineage = FeatureLineage(
            feature_id="feature-123",
            plan_id="plan-123",
            source_type=SourceType.DERIVED,
            transformation_type=TransformationType.MERGED,
            feature_dependencies=["feature-123"],  # Ciclo!
            computation_version="v1.0.0",
            computation_hash="abc123def4567890",
        )

        async def mock_find_one(query):
            if query.get("feature_id") == "feature-123":
                doc = main_lineage.model_dump(mode="json")
                doc["_id"] = "id-123"
                return doc
            return None

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter([]))
        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.validate_integrity("feature-123")

        # Deve detectar ciclo
        assert result.has_cycle is True
        assert result.valid is False


# =============================================================================
# Testes de Update Lineage
# =============================================================================


class TestUpdateLineage:
    """Testes de atualização de lineage."""

    @pytest.mark.asyncio()
    async def test_update_lineage_success(self, lineage_tracker, sample_lineage):
        """Testa atualização bem-sucedida de lineage."""
        # Mock update_one para retornar modified_count=1
        lineage_tracker.collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        # Mock get_lineage para retornar lineage atualizado
        async def mock_find_one(query):
            doc = sample_lineage.model_dump(mode="json")
            doc["_id"] = "id-123"
            doc["custom_field"] = "updated"
            return doc

        lineage_tracker.collection.find_one = AsyncMock(side_effect=mock_find_one)

        result = await lineage_tracker.update_lineage(
            "feature-123", {"custom_field": "updated", "metadata": {"key": "value"}}
        )

        assert result is not None

    @pytest.mark.asyncio()
    async def test_update_lineage_not_found(self, lineage_tracker):
        """Testa atualização de lineage inexistente."""
        lineage_tracker.collection.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
        lineage_tracker.collection.find_one = AsyncMock(return_value=None)

        result = await lineage_tracker.update_lineage("feature-999", {"custom_field": "updated"})

        assert result is None

    @pytest.mark.asyncio()
    async def test_update_lineage_adds_modified_at(self, lineage_tracker):
        """Testa que update adiciona timestamp de modificação."""
        lineage_tracker.collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        lineage_tracker.collection.find_one = AsyncMock(return_value=None)

        await lineage_tracker.update_lineage("feature-123", {"field": "value"})

        # Verificar que modified_at foi adicionado
        call_args = lineage_tracker.collection.update_one.call_args
        updates = call_args[0][1]["$set"]
        assert "modified_at" in updates


# =============================================================================
# Testes de List Lineages
# =============================================================================


class TestListLineages:
    """Testes de listagem de lineages."""

    @pytest.mark.asyncio()
    async def test_list_lineages_basic(self, lineage_tracker, sample_lineage):
        """Testa listagem básica de lineages."""

        async def mock_find_iter(*args, **kwargs):
            doc = sample_lineage.model_dump(mode="json")
            doc["_id"] = "id-123"
            yield doc

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.__aiter__ = AsyncMock(side_effect=mock_find_iter)

        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.list_lineages()

        assert len(result) == 1
        assert isinstance(result[0], FeatureLineage)

    @pytest.mark.asyncio()
    async def test_list_lineages_with_source_type_filter(self, lineage_tracker):
        """Testa listagem com filtro por source_type."""

        async def mock_find_iter(*args, **kwargs):
            yield {
                "feature_id": "feature-1",
                "plan_id": "plan-1",
                "source_type": "cognitive_plan",
                "transformation_type": "computed",
                "data_sources": [],
                "source_plan_ids": [],
                "feature_dependencies": [],
                "parent_lineage_ids": [],
                "transformation_metadata": {},
                "computation_version": "v1.0.0",
                "computation_hash": "abc123",
                "created_at": datetime.now(UTC).isoformat(),
                "_id": "id-1",
            }

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.__aiter__ = AsyncMock(side_effect=mock_find_iter)

        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.list_lineages(source_type=SourceType.COGNITIVE_PLAN)

        # Verificar que filtro foi aplicado
        lineage_tracker.collection.find.assert_called_once()
        call_args = lineage_tracker.collection.find.call_args
        assert "source_type" in call_args[0][0]

    @pytest.mark.asyncio()
    async def test_list_lineages_with_pagination(self, lineage_tracker):
        """Testa listagem com paginação."""

        async def mock_find_iter(*args, **kwargs):
            for i in range(5):
                yield {
                    "feature_id": f"feature-{i}",
                    "plan_id": f"plan-{i}",
                    "source_type": "cognitive_plan",
                    "transformation_type": "computed",
                    "data_sources": [],
                    "source_plan_ids": [],
                    "feature_dependencies": [],
                    "parent_lineage_ids": [],
                    "transformation_metadata": {},
                    "computation_version": "v1.0.0",
                    "computation_hash": "abc123",
                    "created_at": datetime.now(UTC).isoformat(),
                    "_id": f"id-{i}",
                }

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.__aiter__ = AsyncMock(side_effect=mock_find_iter)

        lineage_tracker.collection.find = MagicMock(return_value=mock_cursor)

        result = await lineage_tracker.list_lineages(limit=5, skip=10)

        assert len(result) == 5
        mock_cursor.skip.assert_called_once_with(10)
        mock_cursor.limit.assert_called_once_with(5)


# =============================================================================
# Testes de Delete Lineage
# =============================================================================


class TestDeleteLineage:
    """Testes de deleção de lineage."""

    @pytest.mark.asyncio()
    async def test_delete_lineage_success(self, lineage_tracker):
        """Testa deleção bem-sucedida de lineage."""
        lineage_tracker.collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

        result = await lineage_tracker.delete_lineage("feature-123")

        assert result is True
        lineage_tracker.collection.delete_one.assert_called_once_with({"feature_id": "feature-123"})

    @pytest.mark.asyncio()
    async def test_delete_lineage_not_found(self, lineage_tracker):
        """Testa deleção de lineage inexistente."""
        lineage_tracker.collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

        result = await lineage_tracker.delete_lineage("feature-999")

        assert result is False

    @pytest.mark.asyncio()
    async def test_delete_lineage_with_neo4j(self, lineage_tracker_with_neo4j):
        """Testa que deleção remove relacionamentos do Neo4j."""
        lineage_tracker_with_neo4j.collection.delete_one = AsyncMock(
            return_value=MagicMock(deleted_count=1)
        )

        await lineage_tracker_with_neo4j.delete_lineage("feature-123")

        # Verificar que relacionamentos Neo4j foram removidos
        lineage_tracker_with_neo4j.neo4j_client.delete_node_relationships.assert_called_once_with(
            "feature-123"
        )


# =============================================================================
# Testes de Computation Hash
# =============================================================================


class TestComputationHash:
    """Testes de computação de hash."""

    def test_compute_computation_hash_format(self, lineage_tracker):
        """Testa formato do hash computado."""
        hash_value = lineage_tracker._compute_computation_hash()

        assert isinstance(hash_value, str)
        assert len(hash_value) == 16  # SHA256[:16]

    def test_compute_computation_hash_consistency(self, lineage_tracker):
        """Testa que hash é consistente para mesma versão."""
        hash1 = lineage_tracker._compute_computation_hash()
        hash2 = lineage_tracker._compute_computation_hash()

        # Hash deve ser o mesmo (mesma versão e data)
        assert hash1 == hash2
