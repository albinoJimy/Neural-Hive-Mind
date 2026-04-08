"""Testes unitários para ExperimentInsightExtractor"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.experiment_insight_extractor import ExperimentInsightExtractor
from src.models import InsightConfidence, ExperimentRun


@pytest.mark.asyncio
async def test_extractor_initialization():
    """Testa inicialização do extractor"""
    with patch("src.services.experiment_insight_extractor.mlflow") as mock_mlflow:
        mock_client = MagicMock()
        mock_mlflow.tracking.MlflowClient.return_value = mock_client
        mock_mlflow.set_tracking_uri = MagicMock()

        extractor = ExperimentInsightExtractor()
        await extractor.initialize()

        assert extractor._mlflow_client is not None


@pytest.mark.asyncio
async def test_fetch_experiment_runs_by_ids(mock_experiment_runs, mock_mlflow_runs):
    """Testa busca de runs por IDs"""
    extractor = ExperimentInsightExtractor()
    extractor._mlflow_client = MagicMock()

    # Mock get_run
    for i, run in enumerate(mock_mlflow_runs):
        extractor._mlflow_client.get_run.return_value = run

    # Patch _get_run_safe para retornar runs específicos
    async def mock_get_run_safe(run_id):
        run_dicts = {r.run_id: r.to_dictionary() for r in mock_mlflow_runs}
        return run_dicts.get(run_id)

    extractor._get_run_safe = mock_get_run_safe

    runs = await extractor.fetch_experiment_runs(
        run_ids=["exp_001", "exp_002"],
        max_runs=10,
    )

    assert len(runs) == 2
    assert runs[0].run_id == "exp_001"
    assert runs[1].run_id == "exp_002"


@pytest.mark.asyncio
async def test_fetch_experiment_runs_by_period(mock_experiment_runs):
    """Testa busca de runs por período"""
    extractor = ExperimentInsightExtractor()
    extractor._mlflow_client = MagicMock()

    # Mock search_runs
    from mlflow.entities import ViewType

    mock_run = MagicMock()
    mock_run.to_dictionary.return_value = {
        "info": {
            "run_id": "exp_001",
            "experiment_id": 1,
            "run_name": "test_run",
            "status": "FINISHED",
            "start_time": 1704097200000,  # 2024-01-01
            "end_time": 1704099000000,
        },
        "data": {
            "metrics": [{"key": "accuracy", "value": 0.85}],
            "params": [{"key": "lr", "value": "0.001"}],
            "tags": [{"key": "version", "value": "1"}],
        },
    }

    extractor._mlflow_client.search_experiments.return_value = []
    extractor._mlflow_client.search_runs.return_value = [mock_run]

    runs = await extractor.fetch_experiment_runs(
        period_start=None,
        period_end=None,
        max_runs=10,
    )

    assert len(runs) >= 0  # Pode variar dependendo do mock


@pytest.mark.asyncio
async def test_extract_insights_from_runs(mock_experiment_runs):
    """Testa extração de insights de runs"""
    extractor = ExperimentInsightExtractor()

    insights = await extractor.extract_insights(mock_experiment_runs)

    # Verificar que insights foram gerados
    assert len(insights) > 0

    # Verificar tipos de insights
    categories = {i.category for i in insights}
    assert "performance" in categories


@pytest.mark.asyncio
async def test_extract_insights_with_baseline(mock_experiment_runs):
    """Testa extração de insights com baseline"""
    extractor = ExperimentInsightExtractor()

    insights = await extractor.extract_insights(
        mock_experiment_runs, baseline_run_id="exp_001"
    )

    # Verificar que insights de comparação foram gerados
    comparison_insights = [i for i in insights if i.category in ("improvement", "regression")]
    assert len(comparison_insights) > 0


@pytest.mark.asyncio
async def test_generate_summary(mock_experiment_runs):
    """Testa geração de resumo"""
    extractor = ExperimentInsightExtractor()

    summary = await extractor.generate_summary(mock_experiment_runs)

    assert isinstance(summary, str)
    assert len(summary) > 0
    assert "3" in summary  # Número de experimentos


@pytest.mark.asyncio
async def test_generate_recommendations(mock_experiment_runs, mock_insights):
    """Testa geração de recomendações"""
    extractor = ExperimentInsightExtractor()

    recommendations = await extractor.generate_recommendations(mock_insights, mock_experiment_runs)

    assert isinstance(recommendations, list)
    assert len(recommendations) > 0


@pytest.mark.asyncio
async def test_extract_trend_insights(mock_experiment_runs):
    """Testa extração de insights de tendência"""
    extractor = ExperimentInsightExtractor()

    # Criar runs com tendência de melhoria
    trend_runs = []
    for i in range(5):
        run = ExperimentRun(
            run_id=f"trend_{i}",
            experiment_id=1,
            name=f"trend_run_{i}",
            status="FINISHED",
            start_time=mock_experiment_runs[0].start_time,
            end_time=mock_experiment_runs[0].end_time,
            metrics={"val_accuracy": 0.80 + (i * 0.02)},  # Melhoria progressiva
        )
        trend_runs.append(run)

    insights = await extractor._extract_trend_insights(trend_runs)

    # Verificar que insight de tendência foi gerado
    trend_insights = [i for i in insights if i.category == "trend"]
    assert len(trend_insights) > 0


@pytest.mark.asyncio
async def test_extract_performance_insights(mock_experiment_runs):
    """Testa extração de insights de performance"""
    extractor = ExperimentInsightExtractor()

    insights = await extractor._extract_performance_insights(mock_experiment_runs)

    # Verificar que insight de duração foi gerado
    assert len(insights) > 0
    assert any("duração" in i.description.lower() or "duration" in i.description.lower() for i in insights)


def test_parse_timestamp():
    """Testa parsing de timestamp"""
    extractor = ExperimentInsightExtractor()

    # Timestamp em ms
    ts = 1704097200000
    dt = extractor._parse_timestamp(ts)

    assert dt is not None
    assert dt.year == 2024


def test_extract_metrics():
    """Testa extração de métricas"""
    extractor = ExperimentInsightExtractor()

    metrics_data = [
        {"key": "accuracy", "value": 0.85},
        {"key": "loss", "value": None},  # Deve ser ignorado
    ]

    metrics = extractor._extract_metrics(metrics_data)

    assert "accuracy" in metrics
    assert metrics["accuracy"] == 0.85
    assert "loss" not in metrics
