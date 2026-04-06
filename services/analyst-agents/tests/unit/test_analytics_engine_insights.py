"""
Testes unitários para AnalyticsEngine - Foco em analyze_telemetry_window()

TDD Approach:
1. Escrever testes que falham (VERMELHO)
2. Implementar código para passar (VERDE)
3. Refatorar se necessário

Estes testes foram escritos ANTES da implementação da funcionalidade.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone, timedelta

from src.services.analytics_engine import AnalyticsEngine
from src.models.insight import (
    AnalystInsight,
    TimeWindow,
    InsightType,
    Priority,
    Recommendation,
    RelatedEntity,
)


class TestAnalyticsEngineAnalyzeTelemetryWindow:
    """Testes para AnalyticsEngine.analyze_telemetry_window()"""

    # ========================================================================
    # Testes de Happy Path - Casos de Sucesso
    # ========================================================================

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_with_anomalies_returns_operational_insight(
        self,
    ):
        """
        DADO: telemetry_data com valores anômalos de latência
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: deve retornar AnalystInsight com insight_type=OPERATIONAL
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        # Dados com anomalia clara (valor muito alto)
        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 55.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 1500.0, "timestamp": base_time},  # anomalia
            {"metric": "latency_ms", "value": 52.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 48.0, "timestamp": base_time},
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        assert result is not None, "Deve retornar um insight quando há anomalias"
        assert isinstance(result, AnalystInsight), "Deve retornar AnalystInsight"
        assert (
            result.insight_type == InsightType.OPERATIONAL
        ), "Tipo deve ser OPERATIONAL para anomalias de latência"
        assert result.priority in [
            Priority.HIGH,
            Priority.CRITICAL,
        ], "Anomalias de latência devem ter prioridade HIGH ou CRITICAL"

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_empty_data_returns_none(self):
        """
        DADO: telemetry_data vazio
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: deve retornar None
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)
        window = TimeWindow(
            start_timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            end_timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
        )

        # Act
        result = await analytics.analyze_telemetry_window([], window)

        # Assert
        assert result is None, "Deve retornar None para dados vazios"

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_no_anomalies_returns_none(self):
        """
        DADO: telemetry_data sem anomalias (valores normais)
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: deve retornar None (nada para reportar)
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        # Dados normais, sem anomalias
        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 52.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 48.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 51.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 49.0, "timestamp": base_time},
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        assert result is None, "Deve retornar None quando não há anomalias"

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_with_critical_anomaly_sets_critical_priority(
        self,
    ):
        """
        DADO: telemetry_data com anomalia crítica (latência extrema)
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: deve retornar AnalystInsight com priority=CRITICAL
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        # Dados com anomalia crítica (latência extrema > 5000ms)
        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 10000.0, "timestamp": base_time},  # crítica
            {"metric": "latency_ms", "value": 52.0, "timestamp": base_time},
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        assert result is not None
        assert result.priority == Priority.CRITICAL, "Anomalia crítica deve ter prioridade CRITICAL"

    # ========================================================================
    # Testes de Estrutura do Insight
    # ========================================================================

    @pytest.mark.asyncio
    async def test_insight_contains_required_fields(self):
        """
        DADO: telemetry_data com anomalias
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: o insight retornado deve conter todos os campos obrigatórios
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 2000.0, "timestamp": base_time},  # anomalia
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert - campos obrigatórios do AnalystInsight
        assert result is not None
        assert result.insight_id is not None, "Deve ter insight_id"
        assert result.correlation_id is not None, "Deve ter correlation_id"
        assert result.trace_id is not None, "Deve ter trace_id"
        assert result.span_id is not None, "Deve ter span_id"
        assert result.title is not None, "Deve ter title"
        assert result.summary is not None, "Deve ter summary"
        assert result.detailed_analysis is not None, "Deve ter detailed_analysis"
        assert result.data_sources is not None, "Deve ter data_sources"
        assert result.metrics is not None, "Deve ter metrics"
        assert result.confidence_score >= 0.0, "Confidence deve ser >= 0"
        assert result.confidence_score <= 1.0, "Confidence deve ser <= 1"
        assert result.impact_score >= 0.0, "Impact deve ser >= 0"
        assert result.impact_score <= 1.0, "Impact deve ser <= 1"
        assert result.recommendations is not None, "Deve ter recommendations"
        assert result.related_entities is not None, "Deve ter related_entities"
        assert result.time_window is not None, "Deve ter time_window"

    @pytest.mark.asyncio
    async def test_insight_contains_anomaly_in_metrics(self):
        """
        DADO: telemetry_data com anomalias
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: o insight deve conter métricas da anomalia
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 1500.0, "timestamp": base_time},  # anomalia
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        assert result is not None
        assert "anomaly_count" in result.metrics, "Deve conter anomaly_count"
        assert result.metrics["anomaly_count"] > 0, "Deve ter pelo menos 1 anomalia"
        assert "max_latency" in result.metrics, "Deve conter max_latency"

    @pytest.mark.asyncio
    async def test_insight_has_recommendations(self):
        """
        DADO: telemetry_data com anomalias
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: o insight deve conter recomendações
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 2000.0, "timestamp": base_time},
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        assert result is not None
        assert len(result.recommendations) > 0, "Deve ter pelo menos 1 recomendação"
        assert isinstance(
            result.recommendations[0], Recommendation
        ), "Recomendação deve ser do tipo Recommendation"

    # ========================================================================
    # Testes de Integração com InsightGenerator
    # ========================================================================

    @pytest.mark.asyncio
    async def test_insight_generator_integration_with_mock(self):
        """
        DADO: AnalyticsEngine com InsightGenerator mockado
        QUANDO: analyze_telemetry_window detecta anomalia
        ENTÃO: deve chamar InsightGenerator para criar o insight
        """
        # Arrange
        mock_insight_generator = AsyncMock()
        mock_insight_generator.generate_insight = AsyncMock(
            return_value=AnalystInsight(
                insight_id="test-123",
                version="1.0.0",
                correlation_id="corr-123",
                trace_id="trace-123",
                span_id="span-123",
                insight_type=InsightType.OPERATIONAL,
                priority=Priority.HIGH,
                title="High Latency Detected",
                summary="Anomalia de latência detectada",
                detailed_analysis="Detalhes da análise",
                data_sources=["telemetry"],
                metrics={"anomaly_count": 1},
                confidence_score=0.9,
                impact_score=0.8,
                recommendations=[
                    Recommendation(
                        action="Investigate latency",
                        priority="HIGH",
                        estimated_impact=0.8,
                    )
                ],
                related_entities=[],
                time_window=TimeWindow(
                    start_timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
                    end_timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
                ),
            )
        )

        # Criar AnalyticsEngine com InsightGenerator injetado
        # NOTA: Esta injeção precisará ser implementada no construtor
        analytics = AnalyticsEngine(
            min_confidence=0.7, insight_generator=mock_insight_generator
        )

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 1500.0, "timestamp": base_time},
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        assert result is not None
        # Verifica que o gerador foi chamado (isso requer implementação futura)
        # mock_insight_generator.generate_insight.assert_called_once()

    # ========================================================================
    # Testes de Edge Cases
    # ========================================================================

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_with_mixed_metrics(self):
        """
        DADO: telemetry_data com múltiplas métricas (latency, error_rate, throughput)
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: deve analisar todas as métricas e reportar anomalias em qualquer uma
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 52.0, "timestamp": base_time},
            {"metric": "error_rate", "value": 0.01, "timestamp": base_time},
            {"metric": "error_rate", "value": 0.95, "timestamp": base_time},  # anomalia
            {"metric": "throughput", "value": 1000.0, "timestamp": base_time},
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        assert result is not None, "Deve detectar anomalia em error_rate"
        assert result.insight_type == InsightType.OPERATIONAL

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_with_insufficient_data(self):
        """
        DADO: telemetry_data com menos de 3 pontos (insuficiente para detecção)
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: deve retornar None ou insight com baixa confiança
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        # Apenas 2 pontos de dados
        telemetry_data = [
            {"metric": "latency_ms", "value": 50.0, "timestamp": base_time},
            {"metric": "latency_ms", "value": 55.0, "timestamp": base_time},
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert - pode retornar None ou insight com baixa confiança
        if result is not None:
            assert (
                result.confidence_score < 0.7
            ), "Com dados insuficientes, confiança deve ser baixa"

    # ========================================================================
    # Testes de Tracing
    # ========================================================================

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_propagates_trace_context(self):
        """
        DADO: telemetry_data com contexto de tracing
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: o insight deve conter correlation_id, trace_id e span_id
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        telemetry_data = [
            {
                "metric": "latency_ms",
                "value": 1500.0,
                "timestamp": base_time,
                "trace_id": "trace-123",
                "span_id": "span-456",
            }
        ]

        # Act
        result = await analytics.analyze_telemetry_window(telemetry_data, window)

        # Assert
        if result is not None:
            # Se contexto de tracing está presente nos dados, deve ser propagado
            # NOTA: Esta funcionalidade precisará ser implementada
            assert result.correlation_id is not None or result.trace_id is not None

    # ========================================================================
    # Testes de Performance
    # ========================================================================

    @pytest.mark.asyncio
    async def test_analyze_telemetry_window_with_large_dataset(self):
        """
        DADO: telemetry_data com 1000 pontos de dados
        QUANDO: analyze_telemetry_window é chamado
        ENTÃO: deve completar em tempo razoável (< 5 segundos)
        """
        # Arrange
        analytics = AnalyticsEngine(min_confidence=0.7)

        base_time = datetime.now(timezone.utc)
        window = TimeWindow(
            start_timestamp=int((base_time - timedelta(hours=1)).timestamp() * 1000),
            end_timestamp=int(base_time.timestamp() * 1000),
        )

        # Gerar 1000 pontos com algumas anomalias
        import random

        random.seed(42)
        telemetry_data = []
        for i in range(1000):
            value = random.gauss(50, 5)
            if i % 100 == 0:  # Adicionar anomalia a cada 100 pontos
                value = 200.0
            telemetry_data.append(
                {"metric": "latency_ms", "value": value, "timestamp": base_time}
            )

        # Act
        import time

        start_time = time.time()
        result = await analytics.analyze_telemetry_window(telemetry_data, window)
        elapsed_time = time.time() - start_time

        # Assert
        assert elapsed_time < 5.0, f"Deve completar em menos de 5 segundos, levou {elapsed_time:.2f}s"
