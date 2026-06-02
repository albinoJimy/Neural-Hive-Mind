"""
Testes para TimeSeriesAnalyzer.
"""

from datetime import datetime, timezone, timedelta

import numpy as np
import pytest
from src.models.insight_extended import (
    AnomalyDetectionQuery,
)


@pytest.mark.asyncio()
async def test_analyze_trend_increasing(timeseries_analyzer):
    """Testar análise de tendência crescente."""
    base_time = datetime.now(timezone.utc)
    # Usar minutos para maior slope, não horas
    data = [(base_time + timedelta(minutes=i), 10.0 + i * 5) for i in range(15)]

    result = timeseries_analyzer.analyze_trend(data)

    assert result["trend"] == "increasing"
    assert result["slope"] > 0
    assert result["confidence"] > 0.5


@pytest.mark.asyncio()
async def test_analyze_trend_decreasing(timeseries_analyzer):
    """Testar análise de tendência decrescente."""
    base_time = datetime.now(timezone.utc)
    data = [(base_time + timedelta(hours=i), 100.0 - i * 5) for i in range(10)]

    result = timeseries_analyzer.analyze_trend(data)

    assert result["trend"] == "decreasing"
    assert result["slope"] < 0


@pytest.mark.asyncio()
async def test_analyze_trend_stable(timeseries_analyzer):
    """Testar análise de tendência estável."""
    base_time = datetime.now(timezone.utc)
    data = [(base_time + timedelta(hours=i), 50.0 + np.random.randn() * 0.1) for i in range(10)]

    result = timeseries_analyzer.analyze_trend(data)

    assert result["trend"] == "stable"
    assert abs(result["slope"]) < 1.0


@pytest.mark.asyncio()
async def test_detect_anomalies_zscore(timeseries_analyzer, sample_timeseries_with_anomalies):
    """Testar detecção de anomalias com Z-Score."""
    anomalies = timeseries_analyzer.detect_anomalies_zscore(
        sample_timeseries_with_anomalies, threshold=2.0
    )

    assert len(anomalies) >= 2  # Pelo menos as 2 anomalias inseridas
    assert all(a.score > 2.0 for a in anomalies)
    assert all(a.timestamp is not None for a in anomalies)


@pytest.mark.asyncio()
async def test_detect_anomalies_iqr(timeseries_analyzer):
    """Testar detecção de anomalias com IQR."""
    base_time = datetime.now(timezone.utc)
    # Dados com variância normal (45-55)
    np.random.seed(42)
    data = [(base_time + timedelta(minutes=i), 50.0 + np.random.randn() * 3) for i in range(20)]
    # Adicionar outliers extremos
    data[5] = (data[5][0], 95.0)
    data[15] = (data[15][0], 5.0)

    anomalies = timeseries_analyzer.detect_anomalies_iqr(data, multiplier=1.5)

    assert len(anomalies) >= 2
    assert all(a.severity in ["low", "medium", "high"] for a in anomalies)


@pytest.mark.asyncio()
async def test_detect_anomalies_moving_avg(timeseries_analyzer):
    """Testar detecção de anomalias com média móvel."""
    base_time = datetime.now(timezone.utc)
    # Dados com variância para permitir std > 0 na janela
    np.random.seed(42)
    data = [(base_time + timedelta(minutes=i), 50.0 + np.random.randn() * 2) for i in range(20)]
    # Adicionar outlier no meio
    data[10] = (data[10][0], 95.0)

    anomalies = timeseries_analyzer.detect_anomalies_moving_avg(data, window=5, std_multiplier=2.0)

    # Deve detectar o outlier
    assert len(anomalies) >= 1


@pytest.mark.asyncio()
async def test_detect_seasonality(timeseries_analyzer):
    """Testar detecção de sazonalidade."""
    base_time = datetime.now(timezone.utc)
    # Criar dados com padrão sazonal
    data = []
    for i in range(50):
        value = 50 + 10 * np.sin(2 * np.pi * i / 10)  # Período de 10 pontos
        data.append((base_time + timedelta(minutes=i), value))

    result = timeseries_analyzer.detect_seasonality(data)

    assert result is not None
    assert "has_seasonality" in result
    assert "period" in result
    assert "strength" in result


@pytest.mark.asyncio()
async def test_calculate_statistics(timeseries_analyzer):
    """Testar cálculo de estatísticas."""
    base_time = datetime.now(timezone.utc)
    data = [(base_time + timedelta(minutes=i), float(i)) for i in range(1, 11)]

    stats = timeseries_analyzer.calculate_statistics(data)

    assert stats["min"] == 1.0
    assert stats["max"] == 10.0
    assert stats["mean"] == 5.5
    assert stats["count"] == 10


@pytest.mark.asyncio()
async def test_calculate_statistics_empty(timeseries_analyzer):
    """Testar estatísticas com dados vazios."""
    stats = timeseries_analyzer.calculate_statistics([])

    assert stats["min"] == 0.0
    assert stats["max"] == 0.0
    assert stats["count"] == 0


@pytest.mark.asyncio()
async def test_generate_cache_key(timeseries_analyzer):
    """Testar geração de chave de cache."""
    start = datetime(2024, 1, 1, 0, 0)
    end = datetime(2024, 1, 2, 0, 0)

    cache_key = timeseries_analyzer.generate_cache_key("cpu_usage", start, end, "5m")

    assert "cpu_usage" in cache_key
    assert "2024-01-01" in cache_key
    assert "5m" in cache_key


@pytest.mark.asyncio()
async def test_analyze_timeseries(timeseries_analyzer, sample_timeseries_data):
    """Testar análise completa de série temporal."""
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    end = datetime.now(timezone.utc)

    response = await timeseries_analyzer.analyze_timeseries(
        metric_name="test_metric",
        data=sample_timeseries_data,
        start=start,
        end=end,
        resolution="5m",
    )

    assert response.metric_name == "test_metric"
    assert len(response.data) == len(sample_timeseries_data)
    assert response.statistics is not None
    assert response.statistics["count"] == 12


@pytest.mark.asyncio()
async def test_detect_anomalies_async_zscore(timeseries_analyzer):
    """Testar detecção assíncrona com Z-Score."""
    query = AnomalyDetectionQuery(
        metric_name="test_metric",
        start=datetime.now(timezone.utc) - timedelta(hours=1),
        end=datetime.now(timezone.utc),
        method="zscore",
        threshold=2.5,
    )

    data = [
        (datetime.now(timezone.utc) - timedelta(minutes=i), 50.0 + np.random.randn() * 2)
        for i in range(20)
    ]
    # Adicionar anomalia
    data[10] = (data[10][0], 95.0)

    response = await timeseries_analyzer.detect_anomalies_async(query, data)

    assert response.metric_name == "test_metric"
    assert response.method == "zscore"
    assert response.threshold == 2.5
    assert response.summary["total_anomalies"] >= 1


@pytest.mark.asyncio()
async def test_detect_anomalies_async_iqr(timeseries_analyzer):
    """Testar detecção assíncrona com IQR."""
    query = AnomalyDetectionQuery(
        metric_name="test_metric",
        start=datetime.now(timezone.utc) - timedelta(hours=1),
        end=datetime.now(timezone.utc),
        method="iqr",
        threshold=3.0,
    )

    # Dados com variância
    np.random.seed(42)
    data = [
        (datetime.now(timezone.utc) - timedelta(minutes=i), 50.0 + np.random.randn() * 3)
        for i in range(20)
    ]
    data[5] = (data[5][0], 100.0)

    response = await timeseries_analyzer.detect_anomalies_async(query, data)

    assert response.method == "iqr"
    assert response.summary["total_anomalies"] >= 1


@pytest.mark.asyncio()
async def test_detect_anomalies_async_moving_avg(timeseries_analyzer):
    """Testar detecção assíncrona com média móvel."""
    query = AnomalyDetectionQuery(
        metric_name="test_metric",
        start=datetime.now(timezone.utc) - timedelta(hours=1),
        end=datetime.now(timezone.utc),
        method="moving_avg",
        threshold=2.0,
    )

    # Dados com variância
    np.random.seed(42)
    data = [
        (datetime.now(timezone.utc) - timedelta(minutes=i), 50.0 + np.random.randn() * 2)
        for i in range(20)
    ]
    data[10] = (data[10][0], 95.0)

    response = await timeseries_analyzer.detect_anomalies_async(query, data)

    assert response.method == "moving_avg"
    assert response.summary["total_anomalies"] >= 1


@pytest.mark.asyncio()
async def test_anomaly_summary_severity(timeseries_analyzer):
    """Testar contagem de severidade de anomalias."""
    query = AnomalyDetectionQuery(
        metric_name="test_metric",
        start=datetime.now(timezone.utc) - timedelta(hours=1),
        end=datetime.now(timezone.utc),
        method="zscore",
        threshold=1.5,
    )

    # Criar dados com anomalias de diferentes severidades
    data = [(datetime.now(timezone.utc) - timedelta(minutes=i), 50.0) for i in range(30)]
    data[5] = (data[5][0], 95.0)  # High
    data[10] = (data[10][0], 80.0)  # Medium
    data[15] = (data[15][0], 70.0)  # Medium/Low
    data[20] = (data[20][0], 5.0)  # High

    response = await timeseries_analyzer.detect_anomalies_async(query, data)

    assert response.summary["total_anomalies"] >= 1
    assert "high_severity" in response.summary
    assert "medium_severity" in response.summary
    assert "low_severity" in response.summary


@pytest.mark.asyncio()
async def test_insufficient_data_points(timeseries_analyzer):
    """Testar comportamento com dados insuficientes."""
    data = [(datetime.now(timezone.utc), 50.0)]

    # Trend analysis deve retornar estável
    result = timeseries_analyzer.analyze_trend(data)
    assert result["trend"] == "stable"

    # Anomaly detection deve retornar vazio
    anomalies = timeseries_analyzer.detect_anomalies_zscore(data)
    assert len(anomalies) == 0
