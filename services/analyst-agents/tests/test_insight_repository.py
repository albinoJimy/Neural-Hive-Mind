"""
Testes para InsightRepository.
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.repositories.insight_repository import InsightRepository
from src.models.insight_extended import (
    InsightCreate,
    InsightResponse,
    AnalysisType,
    InsightSource,
    InsightStatus,
    InsightMetadata,
)


@pytest.mark.asyncio
async def test_create_insight(insight_repository, sample_insight_create):
    """Testar criar insight."""
    result = await insight_repository.create(sample_insight_create)

    assert isinstance(result, InsightResponse)
    assert result.insight_id is not None
    assert result.analysis_type == AnalysisType.TIMESERIES
    assert result.title == "Test Insight"
    assert result.status == InsightStatus.PENDING
    assert result.created_at is not None
    assert result.expires_at is not None


@pytest.mark.asyncio
async def test_get_by_id(insight_repository, sample_insight_create):
    """Testar obter insight por ID."""
    created = await insight_repository.create(sample_insight_create)
    result = await insight_repository.get_by_id(created.insight_id)

    assert result is not None
    assert result.insight_id == created.insight_id
    assert result.title == "Test Insight"


@pytest.mark.asyncio
async def test_get_by_id_not_found(insight_repository):
    """Testar obter insight inexistente."""
    result = await insight_repository.get_by_id("non-existent-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_all(insight_repository):
    """Testar listar todos os insights."""
    # Criar alguns insights
    for i in range(3):
        insight = InsightCreate(
            analysis_type=AnalysisType.TIMESERIES,
            title=f"Insight {i}",
            description=f"Description {i}",
            data={"index": i},
            metadata=InsightMetadata(source=InsightSource.API),
            tags=[f"tag{i}"],
        )
        await insight_repository.create(insight)

    items, total = await insight_repository.list(limit=10, offset=0)

    assert total >= 3
    assert len(items) >= 3


@pytest.mark.asyncio
async def test_list_by_analysis_type(insight_repository):
    """Testar listar por tipo de análise."""
    # Criar insights de tipos diferentes
    await insight_repository.create(
        InsightCreate(
            analysis_type=AnalysisType.TIMESERIES,
            title="TS Insight",
            description="",
            data={},
            metadata=InsightMetadata(source=InsightSource.API),
            tags=["ts"],
        )
    )

    await insight_repository.create(
        InsightCreate(
            analysis_type=AnalysisType.ANOMALY_DETECTION,
            title="Anomaly Insight",
            description="",
            data={},
            metadata=InsightMetadata(source=InsightSource.API),
            tags=["anomaly"],
        )
    )

    items, total = await insight_repository.list(analysis_type=AnalysisType.TIMESERIES)

    assert total >= 1
    assert all(i.analysis_type == AnalysisType.TIMESERIES for i in items)


@pytest.mark.asyncio
async def test_list_by_source(insight_repository):
    """Testar listar por fonte."""
    await insight_repository.create(
        InsightCreate(
            analysis_type=AnalysisType.TIMESERIES,
            title="Kafka Insight",
            description="",
            data={},
            metadata=InsightMetadata(source=InsightSource.KAFKA),
            tags=["kafka"],
        )
    )

    items, total = await insight_repository.list(source=InsightSource.KAFKA)

    assert total >= 1
    assert all(i.metadata.source == InsightSource.KAFKA for i in items)


@pytest.mark.asyncio
async def test_list_by_tags(insight_repository):
    """Testar listar por tags."""
    await insight_repository.create(
        InsightCreate(
            analysis_type=AnalysisType.TIMESERIES,
            title="Tagged Insight",
            description="",
            data={},
            metadata=InsightMetadata(source=InsightSource.API),
            tags=["important", "production"],
        )
    )

    items, total = await insight_repository.list(tags=["important"])

    assert total >= 1
    assert all("important" in i.tags for i in items)


@pytest.mark.asyncio
async def test_list_pagination(insight_repository):
    """Testar paginação."""
    # Criar 5 insights
    for i in range(5):
        await insight_repository.create(
            InsightCreate(
                analysis_type=AnalysisType.TIMESERIES,
                title=f"Page Insight {i}",
                description="",
                data={"index": i},
                metadata=InsightMetadata(source=InsightSource.API),
                tags=[],
            )
        )

    items1, total1 = await insight_repository.list(limit=2, offset=0)
    items2, total2 = await insight_repository.list(limit=2, offset=2)

    assert total1 >= 5
    assert len(items1) == 2
    assert len(items2) == 2
    assert items1[0].title != items2[0].title


@pytest.mark.asyncio
async def test_update_status(insight_repository, sample_insight_create):
    """Testar atualizar status."""
    created = await insight_repository.create(sample_insight_create)

    result = await insight_repository.update_status(
        created.insight_id, InsightStatus.COMPLETED, {"result": "success"}
    )

    assert result is not None
    assert result.status == InsightStatus.COMPLETED
    assert result.data.get("result") == "success"


@pytest.mark.asyncio
async def test_update_status_not_found(insight_repository):
    """Testar atualizar status de insight inexistente."""
    result = await insight_repository.update_status("non-existent-id", InsightStatus.COMPLETED)
    assert result is None


@pytest.mark.asyncio
async def test_delete(insight_repository, sample_insight_create):
    """Testar deletar insight."""
    created = await insight_repository.create(sample_insight_create)

    deleted = await insight_repository.delete(created.insight_id)
    assert deleted is True

    # Verificar que foi deletado
    result = await insight_repository.get_by_id(created.insight_id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_not_found(insight_repository):
    """Testar deletar insight inexistente."""
    deleted = await insight_repository.delete("non-existent-id")
    assert deleted is False


@pytest.mark.asyncio
async def test_cache_set_get(insight_repository):
    """Testar cache de série temporal."""
    cache_key = "test_metric:2024-01-01T00:00:00:2024-01-02T00:00:00:5m"
    data = [{"timestamp": "2024-01-01T00:00:00", "value": 50.0}]
    statistics = {"min": 50.0, "max": 50.0, "mean": 50.0, "std": 0.0}

    cached = await insight_repository.cache_set(cache_key, "test_metric", data, statistics)

    assert cached.cache_key == cache_key
    assert cached.metric_name == "test_metric"

    # Get from cache
    retrieved = await insight_repository.cache_get(cache_key)
    assert retrieved is not None
    assert retrieved.cache_key == cache_key
    assert retrieved.metric_name == "test_metric"


@pytest.mark.asyncio
async def test_cache_miss(insight_repository):
    """Testar cache miss."""
    result = await insight_repository.cache_get("non-existent-key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_delete(insight_repository):
    """Testar deletar do cache."""
    cache_key = "test_key_to_delete"
    await insight_repository.cache_set(cache_key, "metric", [], {})

    deleted = await insight_repository.cache_delete(cache_key)
    assert deleted is True

    # Verify deleted
    result = await insight_repository.cache_get(cache_key)
    assert result is None


@pytest.mark.asyncio
async def test_get_analytics_summary(insight_repository):
    """Testar obter resumo analítico."""
    # Criar alguns insights com métricas
    now = datetime.now(timezone.utc)
    for i in range(3):
        insight = InsightCreate(
            analysis_type=AnalysisType.TIMESERIES,
            title=f"Summary Insight {i}",
            description="",
            data={},
            metadata=InsightMetadata(source=InsightSource.API),
            tags=["summary"],
        )
        created = await insight_repository.create(insight)
        # Atualizar com métricas
        await insight_repository.update_status(created.insight_id, InsightStatus.COMPLETED)
        await insight_repository.update_metrics(
            created.insight_id,
            {
                "processing_time_ms": 100 + i * 50,
                "confidence_score": 0.8 + i * 0.05,
                "data_points": 100,
            },
        )

    summary = await insight_repository.get_analytics_summary(time_range_hours=24)

    assert summary is not None
    assert "insights_by_type" in summary
    assert "avg_processing_time_ms" in summary
    assert "confidence_distribution" in summary
    assert "top_sources" in summary
